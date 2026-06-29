# FatCat extraction benchmarks

These benchmarks measure whether FatCat extracts durable knowledge about the user
without flooding review with transient conversation details. They call the
existing `LLMPort` directly and never write to FatCat's production repositories.

## Suites

- `natural`: unannotated prevalence samples. Use these for extraction rate,
  abstention, evidence provenance, latency, and review burden. They do not provide
  precision or recall.
- `challenge`: controlled cases with known semantic assertions.
- `gold`: manually annotated natural conversations. This suite can grow gradually;
  `single_annotated` and `adjudicated` make annotation maturity explicit.

## Run the controlled baseline

```bash
uv run fcat-benchmark run \
  --input benchmarks/challenges/core.jsonl \
  --output benchmarks/reports/challenge-baseline.json
```

Add `--include-assistant-context` to test whether assistant statements are ever
misattributed to the user.

The Ollama adapter requests the exact Pydantic JSON schema and disables model
thinking by default. This makes structured extraction faster and prevents a
single invented enum value from invalidating an otherwise useful response.

## Prepare LongMemEval preferences

```bash
uv run fcat-benchmark download-longmemeval --variant oracle

uv run fcat-benchmark prepare-longmemeval \
  --input benchmarks/data/longmemeval_oracle.json \
  --output benchmarks/data/longmemeval-preferences.jsonl

uv run fcat-benchmark run \
  --input benchmarks/data/longmemeval-preferences.jsonl \
  --output benchmarks/reports/longmemeval-preferences-baseline.json \
  --model qwen3:8b \
  --include-assistant-context
```

The default Oracle download is about 15 MB and contains only evidence sessions.
The downloader pins the current Hugging Face revision and writes a SHA-256
provenance manifest next to the local file. The converted preference suite uses
LongMemEval's `has_answer` turns as evidence sources. It measures whether FatCat
extracts a preference from the correct user-authored turn; it does not yet judge
whether arbitrary paraphrases contain the complete gold answer.

The larger `s` (277 MB) and `m` (2.74 GB) variants are intentionally opt-in. They
are useful later for retrieval and distractor-resistance tests, not for the first
extraction baseline. Downloaded data and reports are gitignored.

Benchmark runs print progress after every conversation and maintain a compatible
`*.partial.json` checkpoint next to the final report. Re-running the same command
resumes completed cases. Use `--no-resume` only when intentionally replacing an
incomplete run.

LongMemEval is an MIT-licensed ICLR 2025 benchmark:
https://github.com/xiaowu0162/LongMemEval

## Annotation workflow

1. Copy selected natural cases into a separate gold JSONL file.
2. Set `suite` to `gold` and `annotation_status` to `single_annotated`.
3. Add only conversation-level durable outcomes, exact evidence, scope, and
   candidate-type constraints to `expectation`.
4. Have a second reviewer inspect disagreements before changing the status to
   `adjudicated`.
5. Never tune prompts against the final held-out gold split.

The benchmark deliberately scores stable semantic properties rather than exact
LLM wording.
