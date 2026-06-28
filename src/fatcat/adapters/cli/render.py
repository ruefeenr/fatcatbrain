"""Rich-based rendering helpers for the CLI."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from fatcat.domain.models import (
    Issue,
    IssueCandidate,
    MemoryCandidate,
    MemoryItem,
    Session,
)

console = Console()


def _confidence_style(confidence: float) -> str:
    if confidence >= 0.8:
        return "green"
    if confidence >= 0.6:
        return "yellow"
    return "red"


def render_candidate(index: int, candidate: MemoryCandidate) -> Panel:
    """Render one memory proposal without exposing internal taxonomy."""

    body = Text()
    body.append(candidate.content, style="bold")
    if candidate.reason:
        body.append("\n\nWhy I noticed it: ", style="dim")
        body.append(candidate.reason, style="italic dim")

    return Panel(
        body,
        title=f"[bold]What I learned {index}[/bold]",
        subtitle="(Enter) Keep  (e) Edit  (n) No  (d) Details  (q) Finish later",
        border_style=_confidence_style(candidate.confidence),
    )


def render_issue_candidate(index: int, candidate: IssueCandidate) -> Panel:
    """Render an uncertainty in language focused on the user."""

    body = Text()
    body.append(candidate.question + "\n\n", style="bold")
    body.append("Learning goal: ", style="dim")
    body.append(candidate.learning_goal + "\n")
    if candidate.evidence:
        body.append("\nWhat made me wonder:\n", style="dim")
        for evidence in candidate.evidence:
            body.append(f'  “{evidence.text}”\n', style="italic")
    if candidate.reason:
        body.append("Reason: ", style="dim")
        body.append(candidate.reason, style="italic dim")

    return Panel(
        body,
        title=f"[bold]What I am still unsure about {index}[/bold]",
        subtitle="(Enter) Watch  (e) Edit  (n) No  (l) Later  (d) Details  (q) Finish later",
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


def render_issue_table(items: list[Issue], *, numbered: bool = False) -> Table:
    """Render confirmed learning issues for listing or merge selection."""

    table = Table(title="Learning Issues", show_lines=False)
    if numbered:
        table.add_column("#", style="dim", no_wrap=True)
    table.add_column("Importance", style="yellow", no_wrap=True)
    table.add_column("Status", style="cyan", no_wrap=True)
    table.add_column("Scope", style="magenta", no_wrap=True)
    table.add_column("Question")
    for index, item in enumerate(items, start=1):
        row = [item.importance, item.status, item.scope.to_legacy(), item.question]
        if numbered:
            row.insert(0, str(index))
        table.add_row(*row)
    return table


def render_session_table(items: list[Session]) -> Table:
    """Render capture sessions and their review status."""

    table = Table(title="Capture Sessions", show_lines=False)
    table.add_column("Status", style="cyan", no_wrap=True)
    table.add_column("Source", style="magenta", no_wrap=True)
    table.add_column("Title")
    table.add_column("Session ID", style="dim")
    for session in items:
        table.add_row(
            session.status,
            session.source,
            session.title or "(untitled)",
            session.id,
        )
    return table
