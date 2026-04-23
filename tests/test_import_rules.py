"""Structural test: physics/ must not import from ui/ or tests/.

Enforces the one-directional import rule from ARCHITECTURE.md §2.
Trivially passes when physics/ is empty (Phase 1 scaffold state)."""

import ast
from pathlib import Path

PHYSICS_DIR = Path(__file__).resolve().parent.parent / "physics"
FORBIDDEN_ROOTS = {"ui", "tests"}


def _forbidden_imports(source_path: Path) -> list[str]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in FORBIDDEN_ROOTS:
                    violations.append(f"{source_path.name}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root = node.module.split(".", 1)[0]
                if root in FORBIDDEN_ROOTS:
                    violations.append(f"{source_path.name}: from {node.module} import ...")
    return violations


def test_physics_has_no_ui_or_tests_imports():
    all_violations = []
    for py_file in PHYSICS_DIR.rglob("*.py"):
        all_violations.extend(_forbidden_imports(py_file))
    assert not all_violations, (
        "physics/ must not import from ui/ or tests/ per ARCHITECTURE.md §2. "
        f"Violations: {all_violations}"
    )
