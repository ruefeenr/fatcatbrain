from __future__ import annotations

from fatcat.adapters.llm.prompts import SYSTEM_PROMPT, build_user_prompt
from fatcat.domain.models import Issue, MemoryItem, Project, RawInput, Scope


def test_system_prompt_preserves_user_agency_and_never_confirms_issues():
    assert "corrections and rejections" in SYSTEM_PROMPT
    assert (
        "Do not discard a statement merely because it concerns the project"
        in SYSTEM_PROMPT
    )
    assert "Never emit a confirmed issue" in SYSTEM_PROMPT
    assert "exact, verbatim excerpts" in SYSTEM_PROMPT
    assert "NOT a FatCat issue" in SYSTEM_PROMPT
    assert "must be phrased about the user" in SYSTEM_PROMPT
    assert "current project is merely where the question was observed" in SYSTEM_PROMPT
    assert "every FatCat-authored field in English" in SYSTEM_PROMPT
    assert "never invent, translate, or paraphrase evidence" in SYSTEM_PROMPT


def test_user_prompt_includes_session_and_known_context():
    raw = RawInput(
        content="I am unsure whether I prefer immediate or batch review.",
        source="transcript",
        session_id="session_1",
    )
    memory = MemoryItem(
        content="The user confirms issue candidates.",
        memory_type="principle",
        scope="project:fatcat",
        project_id="fatcat",
    )
    issue = Issue(
        question="Does the user prefer immediate or batch review?",
        learning_goal="Learn when review should interrupt the user.",
        target_memory_types=["preference"],
        answer_signals=["The user explicitly chooses a review moment."],
        scope=Scope(level="project", reference_id="fatcat"),
        importance="high",
        project_id="fatcat",
    )

    prompt = build_user_prompt(
        raw,
        project=Project(id="fatcat", name="FatCat"),
        known_context=[memory],
        known_issues=[issue],
    )

    assert "CURRENT SESSION ID: session_1" in prompt
    assert memory.content in prompt
    assert issue.title in prompt
    assert raw.content in prompt
