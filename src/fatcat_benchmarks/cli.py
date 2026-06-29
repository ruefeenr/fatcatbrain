"""Developer CLI for reproducible extraction benchmarks."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

import typer

from fatcat.adapters.llm.ollama_adapter import OllamaAdapter
from fatcat_benchmarks.adapters import (
    JsonlBenchmarkSource,
    LongMemEvalSource,
    download_longmemeval,
    write_cases,
)
from fatcat_benchmarks.application.runner import BenchmarkRunner
from fatcat_benchmarks.domain.models import (
    BenchmarkCaseResult,
    BenchmarkCheckpoint,
    BenchmarkReport,
)

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
    help="Run persistence-free, evidence-based FatCat extraction benchmarks.",
)


class LongMemEvalVariant(str, Enum):
    oracle = "oracle"
    s = "s"
    m = "m"


@app.command("download-longmemeval")
def download_longmemeval_command(
    variant: LongMemEvalVariant = typer.Option(
        LongMemEvalVariant.oracle,
        help="oracle is 15 MB; s is 277 MB; m is 2.74 GB.",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Official JSON destination; defaults to benchmarks/data/.",
    ),
) -> None:
    """Download a revision-pinned official LongMemEval file."""

    filename = {
        "oracle": "longmemeval_oracle.json",
        "s": "longmemeval_s_cleaned.json",
        "m": "longmemeval_m_cleaned.json",
    }[variant.value]
    destination = output or Path("benchmarks/data") / filename
    last_percent = -1

    def progress(downloaded: int, total: int | None) -> None:
        nonlocal last_percent
        if not total:
            return
        percent = int(downloaded * 100 / total)
        if percent >= last_percent + 10 or percent == 100:
            typer.echo(f"Downloading: {percent}%")
            last_percent = percent

    manifest = download_longmemeval(
        variant.value, destination, on_progress=progress
    )
    typer.echo(
        f"Downloaded {manifest['bytes'] / (1024 * 1024):.1f} MB to "
        f"{destination}."
    )
    typer.echo(f"Pinned dataset revision: {manifest['revision']}")


@app.command("prepare-longmemeval")
def prepare_longmemeval(
    input_path: Path = typer.Option(
        Path("benchmarks/data/longmemeval_oracle.json"),
        "--input",
        "-i",
        exists=True,
        readable=True,
        help="Official LongMemEval JSON file.",
    ),
    output: Path = typer.Option(
        Path("benchmarks/data/longmemeval-preferences.jsonl"),
        "--output",
        "-o",
        help="Converted FatCat benchmark JSONL.",
    ),
    question_type: list[str] = typer.Option(
        ["single-session-preference"],
        help="Question type to include; repeat for multiple types.",
    ),
    limit: int | None = typer.Option(None, min=1, help="Optional case limit."),
) -> None:
    """Convert official LongMemEval instances into extraction cases."""

    source = LongMemEvalSource(
        input_path,
        question_types=set(question_type),
        limit=limit,
    )
    written = write_cases(output, source.cases())
    typer.echo(f"Wrote {written} LongMemEval cases to {output}.")


@app.command("run")
def run_benchmark(
    inputs: list[Path] = typer.Option(
        ...,
        "--input",
        "-i",
        exists=True,
        readable=True,
        help="Benchmark JSONL; repeat to combine suites.",
    ),
    output: Path = typer.Option(
        Path("benchmarks/reports/latest.json"),
        "--output",
        "-o",
        help="Machine-readable report path.",
    ),
    model: str = typer.Option("qwen3:8b", help="Installed Ollama model."),
    host: str | None = typer.Option(None, help="Optional Ollama host."),
    include_assistant_context: bool = typer.Option(
        False,
        "--include-assistant-context",
        help="Test role attribution with assistant turns present.",
    ),
    resume: bool = typer.Option(
        True,
        "--resume/--no-resume",
        help="Resume compatible per-conversation checkpoint data.",
    ),
) -> None:
    """Run FatCat's current extractor without saving raw input or candidates."""

    source = JsonlBenchmarkSource(inputs)
    cases = list(source.cases())
    case_ids = [case.id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise typer.BadParameter("Input suites contain duplicate case ids.")

    checkpoint_path = output.with_name(output.name + ".partial.json")
    checkpoint = _load_checkpoint(
        checkpoint_path,
        model=model,
        include_assistant_context=include_assistant_context,
        case_ids=case_ids,
    ) if resume else None
    existing = checkpoint.results if checkpoint is not None else []
    completed_ids = {result.case_id for result in existing}
    pending = [case for case in cases if case.id not in completed_ids]
    if existing:
        typer.echo(
            f"Resuming {len(existing)}/{len(cases)} completed conversations "
            f"from {checkpoint_path}."
        )

    runner = BenchmarkRunner(
        OllamaAdapter(model=model, host=host),
        model_name=model,
        include_assistant_context=include_assistant_context,
    )

    checkpoint = BenchmarkCheckpoint(
        model=model,
        include_assistant_context=include_assistant_context,
        case_ids=case_ids,
        results=list(existing),
    )

    def save_progress(
        completed: int,
        total: int,
        result: BenchmarkCaseResult,
    ) -> None:
        checkpoint.results.append(result)
        _write_checkpoint(checkpoint_path, checkpoint)
        status = "failed" if result.error else f"{len(result.candidates)} candidate(s)"
        typer.echo(
            f"[{completed}/{total}] {result.case_id}: {status}, "
            f"{result.elapsed_ms / 1000:.1f}s"
        )

    report = runner.run_resumable(
        pending,
        existing_results=existing,
        on_result=save_progress,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    checkpoint_path.unlink(missing_ok=True)
    typer.echo(_summary(report))
    typer.echo(f"Report written to {output}.")
    if report.metrics.failed_case_count:
        raise typer.Exit(code=1)


def _summary(report: BenchmarkReport) -> str:
    metrics = report.metrics
    assertion_rate = (
        f"{metrics.assertion_pass_rate:.1%}"
        if metrics.assertion_pass_rate is not None
        else "n/a"
    )
    return "\n".join(
        [
            f"Cases: {metrics.case_count} ({metrics.failed_case_count} failed)",
            f"Candidates: {metrics.memory_candidate_count} memories, "
            f"{metrics.issue_candidate_count} issues",
            f"Candidates / 100 user turns: "
            f"{metrics.candidates_per_100_user_turns:.2f}",
            f"Unsupported evidence: {metrics.unsupported_evidence_count}",
            f"Assistant-only evidence: {metrics.assistant_evidence_count}",
            f"Challenge/gold assertion pass rate: {assertion_rate}",
        ]
    )


def _load_checkpoint(
    path: Path,
    *,
    model: str,
    include_assistant_context: bool,
    case_ids: list[str],
) -> BenchmarkCheckpoint | None:
    if not path.exists():
        return None
    try:
        checkpoint = BenchmarkCheckpoint.model_validate_json(
            path.read_text(encoding="utf-8")
        )
    except Exception as exc:  # noqa: BLE001 - explain damaged local state
        raise typer.BadParameter(f"Invalid checkpoint {path}: {exc}") from exc
    if (
        checkpoint.model != model
        or checkpoint.include_assistant_context != include_assistant_context
        or checkpoint.case_ids != case_ids
    ):
        raise typer.BadParameter(
            f"Checkpoint {path} belongs to a different benchmark configuration. "
            "Use --no-resume to replace it or choose another output path."
        )
    return checkpoint


def _write_checkpoint(path: Path, checkpoint: BenchmarkCheckpoint) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(checkpoint.model_dump_json(indent=2), encoding="utf-8")
    temporary.replace(path)


def run() -> None:
    app()


if __name__ == "__main__":
    run()
