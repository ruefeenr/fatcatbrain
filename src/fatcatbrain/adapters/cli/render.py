"""Rich-based rendering helpers for the CLI."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from fatcatbrain.domain.models import MemoryCandidate, MemoryItem

console = Console()


def _confidence_style(confidence: float) -> str:
    if confidence >= 0.8:
        return "green"
    if confidence >= 0.6:
        return "yellow"
    return "red"


def render_candidate(index: int, candidate: MemoryCandidate) -> Panel:
    """Render one candidate as a panel for interactive review."""

    body = Text()
    body.append(candidate.content + "\n\n", style="bold")
    body.append("Type: ", style="dim")
    body.append(f"{candidate.memory_type}\n")
    body.append("Scope: ", style="dim")
    body.append(f"{candidate.suggested_scope}\n")
    body.append("Confidence: ", style="dim")
    body.append(
        f"{candidate.confidence:.2f}\n", style=_confidence_style(candidate.confidence)
    )
    body.append("Sensitivity: ", style="dim")
    body.append(f"{candidate.sensitivity}")
    if candidate.reason:
        body.append("\nReason: ", style="dim")
        body.append(candidate.reason, style="italic dim")

    return Panel(
        body,
        title=f"[bold]Candidate {index}[/bold]",
        subtitle="(s)ave  (e)dit  (p)roject only  (d)iscard  (q)uit",
        border_style=_confidence_style(candidate.confidence),
    )


def render_memory_table(items: list[MemoryItem]) -> Table:
    """Render confirmed memory items as a compact table."""

    table = Table(title="Memory Items", show_lines=False)
    table.add_column("Type", style="cyan", no_wrap=True)
    table.add_column("Scope", style="magenta", no_wrap=True)
    table.add_column("Content")
    for item in items:
        table.add_row(item.memory_type, item.scope, item.content)
    return table
