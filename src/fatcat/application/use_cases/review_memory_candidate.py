"""Use case: review a single inbox candidate (save / edit / project_only / discard).

This is the central product loop: only confirmed candidates become memory items.
"""

from __future__ import annotations

from dataclasses import dataclass

from fatcat.application.ports import InboxRepository, MemoryRepository
from fatcat.domain.models import MemoryCandidate, MemoryItem
from fatcat.domain.policies import candidate_to_memory_item, scope_for_project_only
from fatcat.domain.value_objects import ReviewDecision


@dataclass(frozen=True)
class ReviewResult:
    """Outcome of reviewing one candidate.

    ``created`` is ``False`` when the decision matched an existing memory, so the
    candidate left the inbox but no new memory item was written.
    """

    decision: ReviewDecision
    candidate: MemoryCandidate
    memory_item: MemoryItem | None
    created: bool = True


class ReviewMemoryCandidate:
    """Apply a user's review decision to a candidate."""

    def __init__(
        self,
        inbox_repo: InboxRepository,
        memory_repo: MemoryRepository,
    ) -> None:
        self._inbox_repo = inbox_repo
        self._memory_repo = memory_repo

    def execute(
        self,
        candidate_id: str,
        decision: ReviewDecision,
        *,
        edited_content: str | None = None,
        project_id: str | None = None,
        scope: str | None = None,
    ) -> ReviewResult:
        candidate = self._inbox_repo.get(candidate_id)
        if candidate is None:
            raise KeyError(f"No pending candidate with id {candidate_id!r}.")

        memory_item: MemoryItem | None = None

        if decision == "discard":
            self._inbox_repo.mark_reviewed(candidate_id, status="rejected")
            return ReviewResult(
                decision=decision,
                candidate=candidate,
                memory_item=None,
                created=False,
            )

        if decision == "project_only":
            # Prefer the explicitly targeted project (the active one), so a globally
            # captured candidate can still be filed under the current project.
            target_project = project_id or candidate.project_id
            if not target_project:
                raise ValueError(
                    "Cannot save 'project only': no target project."
                )
            memory_item = candidate_to_memory_item(
                candidate,
                scope=scope_for_project_only(target_project),
                project_id=target_project,
                content=edited_content,
            )
        elif decision in ("save", "edit"):
            effective_scope = scope or candidate.suggested_scope
            if effective_scope.startswith("project:"):
                target_project = effective_scope.split(":", 1)[1]
            elif effective_scope.startswith("session:"):
                target_project = candidate.project_id
            else:
                # Global and domain knowledge should not be trapped in the
                # project where it happened to be observed.
                target_project = None
            memory_item = candidate_to_memory_item(
                candidate,
                scope=effective_scope,
                project_id=target_project,
                content=edited_content,
            )
        else:  # pragma: no cover - guarded by Literal typing
            raise ValueError(f"Unknown review decision: {decision!r}")

        existing = self._memory_repo.find_duplicate(
            memory_item.content, memory_item.project_id
        )
        if existing is not None:
            self._inbox_repo.mark_reviewed(candidate_id, status="merged")
            return ReviewResult(
                decision=decision,
                candidate=candidate,
                memory_item=existing,
                created=False,
            )

        self._memory_repo.save(memory_item)
        resolution = "edited" if decision == "edit" else "confirmed"
        self._inbox_repo.mark_reviewed(candidate_id, status=resolution)
        return ReviewResult(
            decision=decision,
            candidate=candidate,
            memory_item=memory_item,
            created=True,
        )
