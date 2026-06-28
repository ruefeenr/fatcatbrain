from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).parents[2] / "src" / "fatcat"


def _absolute_imports(folder: Path) -> list[tuple[Path, str]]:
    imports: list[tuple[Path, str]] = []
    for path in folder.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(
                    (path, alias.name)
                    for alias in node.names
                    if alias.name.startswith("fatcat.")
                )
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("fatcat."):
                    imports.append((path, node.module))
    return imports


def test_domain_does_not_depend_on_outer_hexagons():
    forbidden = ("fatcat.application", "fatcat.adapters", "fatcat.config")

    violations = [
        (path, module)
        for path, module in _absolute_imports(SRC / "domain")
        if module.startswith(forbidden)
    ]

    assert violations == []


def test_application_does_not_depend_on_adapters_or_composition():
    forbidden = ("fatcat.adapters", "fatcat.composition", "fatcat.config")

    violations = [
        (path, module)
        for path, module in _absolute_imports(SRC / "application")
        if module.startswith(forbidden)
    ]

    assert violations == []
