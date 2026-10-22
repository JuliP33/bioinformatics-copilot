import importlib.util
import os
from pathlib import Path
from unittest.mock import patch

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "project_copilot.py"
)

spec = importlib.util.spec_from_file_location(
    "project_copilot", SCRIPT
)
copilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(copilot)


@pytest.fixture
def project_dir(tmp_path, monkeypatch):
    """Run each test inside an isolated temporary directory."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def make_response(filename, content, language="python"):
    """Build a response in the format expected by the copilot."""
    return (
        f"FILE: {filename}\n"
        f"```{language}\n"
        f"{content}\n"
        "```\n"
    )


def test_rejects_path_outside_project(project_dir):
    response = make_response(
        "../outside.py",
        "print('unsafe')",
    )

    with patch("builtins.input", return_value="yes"):
        copilot.parse_and_apply_changes(response)

    assert not (project_dir.parent / "outside.py").exists()


def test_applies_approved_change(project_dir):
    target = project_dir / "example.py"
    target.write_text("print('original')\n", encoding="utf-8")

    response = make_response(
        "example.py",
        "print('modified')",
    )

    with patch("builtins.input", return_value="yes"):
        copilot.parse_and_apply_changes(response)

    assert target.read_text(encoding="utf-8") == "print('modified')\n"


def test_creates_backup_before_overwriting(project_dir):
    target = project_dir / "example.py"
    target.write_text("print('original')\n", encoding="utf-8")

    response = make_response(
        "example.py",
        "print('modified')",
    )

    with patch("builtins.input", return_value="yes"):
        copilot.parse_and_apply_changes(response)

    backups = list((project_dir / ".copilot_backups").glob("*.bak"))

    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "print('original')\n"


def test_rejected_change_leaves_file_untouched(project_dir):
    target = project_dir / "example.py"
    original = "print('original')\n"
    target.write_text(original, encoding="utf-8")

    response = make_response(
        "example.py",
        "print('modified')",
    )

    with patch("builtins.input", return_value="no"):
        copilot.parse_and_apply_changes(response)

    assert target.read_text(encoding="utf-8") == original
    assert not (project_dir / ".copilot_backups").exists()


def test_rejects_disallowed_extension(project_dir):
    target = project_dir / "audit.db"
    original = "DO NOT MODIFY"
    target.write_text(original, encoding="utf-8")

    response = make_response(
        "audit.db",
        "MODIFIED CONTENT",
        language="text",
    )

    with patch("builtins.input", return_value="yes"):
        copilot.parse_and_apply_changes(response)

    assert target.read_text(encoding="utf-8") == original
    assert not (project_dir / ".copilot_backups").exists()

def test_rejects_unclosed_code_block(project_dir):
    target = project_dir / "example.py"
    original = "print('original')\n"
    target.write_text(original, encoding="utf-8")

    response = (
        "FILE: example.py\n"
        "```python\n"
        "print('modified')\n"
    )

    with patch("builtins.input", return_value="yes"):
        copilot.parse_and_apply_changes(response)

    assert target.read_text(encoding="utf-8") == original
def test_rejects_symlink_pointing_outside_project(project_dir, tmp_path):
    outside_dir = tmp_path.parent / f"{tmp_path.name}_outside"
    outside_dir.mkdir()

    outside_file = outside_dir / "protected.py"
    original = "print('protected')\n"
    outside_file.write_text(original, encoding="utf-8")

    link = project_dir / "alias.py"

    try:
        link.symlink_to(outside_file)
    except OSError as exc:
        pytest.skip(f"Cannot create symlink in this environment: {exc}")

    response = make_response(
        "alias.py",
        "print('modified')",
    )

    with patch("builtins.input", return_value="yes"):
        copilot.parse_and_apply_changes(response)

    assert outside_file.read_text(encoding="utf-8") == original

def test_rejects_symlinked_parent_directory(project_dir, tmp_path):
    outside_dir = tmp_path.parent / f"{tmp_path.name}_outside_dir"
    outside_dir.mkdir()

    outside_file = outside_dir / "protected.py"
    original = "print('protected')\n"
    outside_file.write_text(original, encoding="utf-8")

    link_dir = project_dir / "safe_dir"

    try:
        link_dir.symlink_to(outside_dir, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Cannot create symlink in this environment: {exc}")

    response = make_response(
        "safe_dir/protected.py",
        "print('modified')",
    )

    with patch("builtins.input", return_value="yes"):
        copilot.parse_and_apply_changes(response)

    assert outside_file.read_text(encoding="utf-8") == original



def test_rejects_parent_symlink_swapped_before_write(project_dir, tmp_path):
    safe_dir = project_dir / "safe_dir"
    safe_dir.mkdir()
    (safe_dir / "protected.py").write_text(
        "print('original')\n", encoding="utf-8"
    )

    outside_dir = tmp_path.parent / f"{tmp_path.name}_race_outside"
    outside_dir.mkdir()
    outside_file = outside_dir / "protected.py"
    outside_file.write_text("print('outside')\n", encoding="utf-8")

    response = make_response("safe_dir/protected.py", "print('modified')")

    def swap_then_confirm(_prompt):
        safe_dir.rename(project_dir / "safe_dir_moved")
        safe_dir.symlink_to(outside_dir, target_is_directory=True)
        return "yes"

    with patch("builtins.input", side_effect=swap_then_confirm):
        copilot.parse_and_apply_changes(response)

    assert outside_file.read_text(encoding="utf-8") == "print('outside')\n"
    assert (
        (project_dir / "safe_dir_moved" / "protected.py").read_text(
            encoding="utf-8"
        )
        == "print('original')\n"
    )


def test_read_only_mode_does_not_apply_file_changes(project_dir):
    target = project_dir / "should_not_exist.py"
    response = make_response(
        "should_not_exist.py",
        "print('this must not be written')",
    )

    copilot.process_assistant_response(response)

    assert not target.exists()
    assert not (project_dir / ".copilot_backups").exists()


def test_edit_mode_processes_approved_file_changes(project_dir):
    target = project_dir / "approved.py"
    response = make_response(
        "approved.py",
        "print('approved')",
    )

    with patch("builtins.input", return_value="yes"):
        copilot.process_assistant_response(response, editing_enabled=True)

    assert target.read_text(encoding="utf-8") == "print('approved')\n"
