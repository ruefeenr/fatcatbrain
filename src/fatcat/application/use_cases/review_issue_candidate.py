"""Use case for explicit user curation of issue candidates."""

from __future__ import annotations

from dataclasses import dataclass

from fatcat.application.ports import (
    IssueCandidateRepository,
    IssueRepository,
    MemoryRepository,
)
from fatcat.domain.models import Issue, IssueCandidate, Scope
from fatcat.domain.policies import (
    confirm_issue,
    merge_issue_candidate,
    transition_issue_candidate,
)
from fatcat.domain.value_objects import (
    Importance,
    IssueReviewDecision,
)


@dataclass(frozen=True)
class IssueReviewResult:
    """Outcome of one issue curation decision."""

    decision: IssueReviewDecision
    candidate: IssueCandidate
    issue: Issue | None
    created: bool = False


class ReviewIssueCandidate:
    """Confirm, edit, merge, reject or defer an issue proposal."""

    def __init__(
        self,
        candidate_repo: IssueCandidateRepository,
        issue_repo: IssueRepository,
        memory_repo: MemoryRepository | None = None,
    ) -> None:
        self._candidate_repo = candidate_repo
        self._issue_repo = issue_repo
        self._memory_repo = memory_repo

    def _linked_memory_ids(self, candidate: IssueCandidate) -> list[str]:
        if self._memory_repo is None:
            return []
        linked: list[str] = []
        for candidate_id in candidate.linked_memory_candidate_ids:
            item = self._memory_repo.find_by_source_candidate_id(candidate_id)
            if item is not None:
                linked.append(item.id)
        return list(dict.fromkeys(linked))

    def execute(
        self,
        candidate_id: str,
        decision: IssueReviewDecision,
        *,
        scope: Scope | None = None,
        importance: Importance | None = None,
        edited_title: str | None = None,
        edited_description: str | None = None,
        merge_target_id: str | None = None,
    ) -> IssueReviewResult:
        candidate = self._candidate_repo.get(candidate_id)
        if candidate is None:
            raise KeyError(f"No issue candidate with id {candidate_id!r}.")

        if decision == "reject":
            transition_issue_candidate(candidate, "rejected")
            self._candidate_repo.set_status(candidate.id, "rejected")
            return IssueReviewResult(decision, candidate, None)

        if decision == "defer":
            transition_issue_candidate(candidate, "deferred")
            self._candidate_repo.set_status(candidate.id, "deferred")
            return IssueReviewResult(decision, candidate, None)

        linked_memory_ids = self._linked_memory_ids(candidate)

        if decision == "merge":
            if not merge_target_id:
                raise ValueError("Merge requires a target issue id.")
            target = self._issue_repo.get(merge_target_id)
            if target is None:
                raise KeyError(f"No confirmed issue with id {merge_target_id!r}.")
            transition_issue_candidate(candidate, "merged")
            issue = merge_issue_candidate(
                candidate,
                target,
                linked_memory_ids=linked_memory_ids,
            )
            self._issue_repo.save(issue)
            self._candidate_repo.set_status(candidate.id, "merged")
            return IssueReviewResult(decision, candidate, issue)

        if decision not in ("confirm", "edit"):
            raise ValueError(f"Unknown issue review decision: {decision!r}.")
        if scope is None or importance is None:
            raise ValueError("Confirming an issue requires scope and importance.")

        resolution = "edited" if decision == "edit" else "confirmed"
        transition_issue_candidate(candidate, resolution)
        issue = confirm_issue(
            candidate,
            scope=scope,
            importance=importance,
            linked_memory_ids=linked_memory_ids,
            title=edited_title,
            description=edited_description,
        )
        self._issue_repo.save(issue)
        self._candidate_repo.set_status(candidate.id, resolution)
        return IssueReviewResult(decision, candidate, issue, created=True)
