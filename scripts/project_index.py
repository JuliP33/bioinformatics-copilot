"""Build a verifiable index of Python files, classes, and functions."""

import ast
from pathlib import Path

EXCLUDED_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "venv",
    "bioinfo_copilot",
    ".copilot_backups",
    "data",
    "outputs",
    "outputs_audit",
    "my_custom_outputs",
    "mis_reportes_avanzados",
}


class DefinitionVisitor(ast.NodeVisitor):
    """Collect definitions while preserving their lexical scope."""

    def __init__(self, relative_path):
        self.relative_path = relative_path
        self.records = []
        self.scope = []

    def _visit_definition(self, node, kind):
        qualified_name = ".".join(self.scope + [node.name])

        self.records.append(
            {
                "path": self.relative_path,
                "kind": kind,
                "name": node.name,
                "qualified_name": qualified_name,
                "scope": ".".join(self.scope) or None,
                "line": node.lineno,
                "end_line": getattr(node, "end_lineno", node.lineno),
            }
        )

        self.scope.append(node.name)
        for child in node.body:
            self.visit(child)
        self.scope.pop()

    def visit_ClassDef(self, node):
        self._visit_definition(node, "class")

    def visit_FunctionDef(self, node):
        self._visit_definition(node, "function")

    def visit_AsyncFunctionDef(self, node):
        self._visit_definition(node, "function")


def index_python_files(root="."):
    """Return definitions parsed from Python files under root."""
    root = Path(root).resolve()
    records = []

    for path in sorted(root.rglob("*.py")):
        if any(part in EXCLUDED_DIRS for part in path.relative_to(root).parts):
            continue

        if path.is_symlink() or not path.is_file():
            continue

        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (OSError, UnicodeError, SyntaxError):
            continue

        relative_path = path.relative_to(root).as_posix()
        visitor = DefinitionVisitor(relative_path)
        visitor.visit(tree)
        records.extend(visitor.records)

    return records


def format_index(records):
    """Format indexed definitions as compact, readable text."""
    lines = []

    for item in records:
        scope = f" [{item['scope']}]" if item["scope"] else ""
        lines.append(
            f"{item['path']}:{item['line']} "
            f"{item['kind']} {item['qualified_name']}{scope}"
        )

    return "\n".join(lines)


if __name__ == "__main__":
    index = index_python_files()
    print(f"Indexed {len(index)} Python definitions.\n")
    print(format_index(index))
