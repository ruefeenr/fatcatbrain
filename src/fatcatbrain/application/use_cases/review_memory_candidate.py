"""Use case: review a single inbox candidate (save / edit / project_only / discard).

This is the central product loop: only confirmed candidates become memory items.
"""

from __future__ import annotations

from dataclasses import dataclass

from fatcatbrain.application.ports import InboxRepository, MemoryRepository
from fatcatbrain.domain.models import MemoryCandidate, MemoryItem
from fatcatbrain.domain.policies import candidate_to_memory_item, scope_for_project_only
from fatcatbrain.domain.value_objects import ReviewDecision


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
    ) -> ReviewResult:
        candidate = self._inbox_repo.get(candidate_id)
        if candidate is None:
            raise KeyError(f"No pending candidate with id {candidate_id!r}.")

        memory_item: MemoryItem | None = None

        if decision == "discard":
            self._inbox_repo.mark_reviewed(candidate_id)
            return ReviewResult(
                decision=decision,
                candidate=candidate,
                memory_item=None,
                created=False,
            )

        if decision == "project_only":
            if not candidate.project_id:
                raise ValueError(
                    "Cannot save 'project only': candidate has no project."
                )
            memory_item = candidate_to_memory_item(
                candidate,
                scope=scope_for_project_only(candidate.project_id),
                project_id=candidate.project_id,
                content=edited_content,
            )
        elif decision in ("save", "edit"):
            memory_item = candidate_to_memory_item(
                candidate,
                content=edited_content,
            )
        else:  # pragma: no cover - guarded by Literal typing
            raise ValueError(f"Unknown review decision: {decision!r}")

        existing = self._memory_repo.find_duplicate(
            memory_item.content, memory_item.project_id
        )
        if existing is not None:
            self._inbox_repo.mark_reviewed(candidate_id)
            return ReviewResult(
                decision=decision,
                candidate=candidate,
                memory_item=existing,
                created=False,
            )

        self._memory_repo.save(memory_item)
        self._inbox_repo.mark_reviewed(candidate_id)
        return ReviewResult(
            decision=decision,
            candidate=candidate,
            memory_item=memory_item,
            created=True,
        )
