"""Guard the product rule that FatCat-authored interface text is English-only."""

from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).parents[2]
USER_FACING_SOURCES = (
    ROOT / "src" / "fatcat" / "adapters" / "cli",
    ROOT / "src" / "fatcat" / "adapters" / "llm" / "errors.py",
)

# Whole-word signals chosen to avoid false positives in ordinary English/code.
GERMAN_UI_WORDS = {
    "abbrechen",
    "auswählen",
    "bearbeiten",
    "bestätigen",
    "bitte",
    "eingeben",
    "fehler",
    "frage",
    "gefunden",
    "geltungsbereich",
    "löschen",
    "nichts",
    "projekt",
    "speichern",
    "später",
    "sitzung",
    "verwerfen",
    "weiter",
    "wichtigkeit",
    "zurück",
    "zusammenführen",
}


def _string_literals(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.lineno, node.value


def test_fatcat_authored_ui_strings_are_english_only():
    violations: list[str] = []
    source_files = [
        path
        for source in USER_FACING_SOURCES
        for path in ([source] if source.is_file() else source.rglob("*.py"))
    ]

    for path in source_files:
        for line, text in _string_literals(path):
            lowered_words = set(re.findall(r"\b[^\W\d_]+\b", text.lower()))
            german_words = sorted(lowered_words & GERMAN_UI_WORDS)
            has_german_characters = bool(re.search(r"[äöüÄÖÜß]", text))
            if german_words or has_german_characters:
                signals = ", ".join(german_words) or "German characters"
                violations.append(f"{path.relative_to(ROOT)}:{line}: {signals}")

    assert not violations, "FatCat UI must be English-only:\n" + "\n".join(violations)
