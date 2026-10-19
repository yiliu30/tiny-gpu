"""Documentation checks for the learning-oriented Python model."""

from __future__ import annotations

import ast
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "tiny_gpu"


def _missing_docstrings(tree: ast.AST) -> list[str]:
    missing: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            if ast.get_docstring(node) is None:
                missing.append(f"class {node.name}")
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not child.name.startswith("_") or child.name == "__init__":
                        if ast.get_docstring(child) is None:
                            missing.append(f"{node.name}.{child.name}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.col_offset == 0:
                if ast.get_docstring(node) is None:
                    missing.append(f"function {node.name}")

    return missing


def test_model_classes_and_public_functions_have_docstrings() -> None:
    missing: list[str] = []
    for path in sorted(PACKAGE_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        missing.extend(f"{path.name}: {name}" for name in _missing_docstrings(tree))

    assert not missing, "Missing concise docstrings:\n" + "\n".join(missing)
