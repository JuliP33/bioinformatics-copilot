import stat
import difflib
from datetime import datetime
import os
import sys
import json
import urllib.request
from pathlib import Path

ALLOWED_EXTENSIONS = {".py", ".md", ".txt", ".json", ".sh"}

EXCLUDED_DIRS = {
    "data",
    "outputs",
    "outputs_audit",
    "my_custom_outputs",
    "mis_reportes_avanzados",
    "bioinfo_copilot",
    ".git",
    "__pycache__",
    ".vscode",
    ".pytest_cache",
    ".copilot_backups",
}

EXCLUDED_FILES = {".copilot_history.json"}
HISTORY_FILE = Path(".copilot_history.json")
OLLAMA_URL = "http://localhost:11434/api/chat"
RUBRIC_FILE = Path("config/copilot_rubric.md")
MAX_HISTORY_MESSAGES = 12

def gather_project_code() -> str:
    project_root = Path(".")
    code_bundle = []
    for path in project_root.rglob("*"):
        if path == RUBRIC_FILE:
            continue
        if any(exc in path.parts for exc in EXCLUDED_DIRS):
            continue
        if path.name in EXCLUDED_FILES:
            continue
        if path.is_file() and path.suffix in ALLOWED_EXTENSIONS:
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
                code_bundle.append(f"--- START OF FILE: {path} ---\n{content}\n--- END OF FILE ---\n")
            except Exception as e:
                print(f"Could not read {path}: {e}")
    return "\n".join(code_bundle)
def load_project_index():
    """Load the AST index without depending on the current working directory."""
    import importlib.util

    index_path = Path(__file__).resolve().parent / "project_index.py"
    spec = importlib.util.spec_from_file_location(
        "project_index", index_path
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load project index: {index_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.index_python_files("."), module.format_index


def select_relevant_files(query, index_records, max_files=4):
    """Select files using query terms, paths, symbols, and source content."""
    import re

    root = Path(".").resolve()

    stop_words = {
        "the", "and", "for", "with", "from", "that", "this",
        "what", "how", "does", "can", "you", "are", "all",
        "about", "into", "have", "has", "its", "please",
        "que", "como", "para", "por", "una", "uno", "los",
        "las", "del", "con", "está", "esta", "son", "hay",
        "proyecto", "project", "explain", "work",
    }

    def tokens(text):
        # Split camelCase and PascalCase: LLMClient -> LLM Client
        text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", text)
        text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)

        # Split snake_case and paths: llm_client.py -> llm client py
        text = text.replace("_", " ")
        parts = re.findall(r"[A-Za-z0-9]+", text)

        return {
            token.casefold()
            for token in parts
            if len(token) >= 3 and token.casefold() not in stop_words
        }
    query_tokens = tokens(query)
    if not query_tokens:
        return []

    # Index real symbols by file path.
    symbols_by_path = {}
    for record in index_records:
        symbols_by_path.setdefault(record["path"], []).append(
            record["qualified_name"]
        )

    candidates = []

    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        if path.suffix not in ALLOWED_EXTENSIONS:
            continue
        if path.name in EXCLUDED_FILES:
            continue

        relative = path.relative_to(root)

        if any(part in EXCLUDED_DIRS for part in relative.parts):
            continue
        if relative.as_posix() == RUBRIC_FILE.as_posix():
            continue

        relative_name = relative.as_posix()
        path_tokens = tokens(relative_name)
        symbol_names = symbols_by_path.get(relative_name, [])
        symbol_tokens = tokens(" ".join(symbol_names))

        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        content_tokens = tokens(content)

        # Prioritize paths and identifiers over general content matches.
        path_matches = query_tokens & path_tokens
        symbol_matches = query_tokens & symbol_tokens
        content_matches = query_tokens & content_tokens

        score = (
            8 * len(path_matches)
            + 10 * len(symbol_matches)
            + len(content_matches)
        )

        # Exact identifier/path phrase matches are strong evidence.
        normalized_query = query.casefold().replace("_", " ")
        normalized_path = relative_name.casefold().replace("_", " ")

        if normalized_path in normalized_query:
            score += 20

        for symbol in symbol_names:
            normalized_symbol = symbol.casefold().replace("_", " ")
            if normalized_symbol in normalized_query:
                score += 20

        if score > 0:
            candidates.append((score, relative_name, content))

    candidates.sort(key=lambda item: (-item[0], item[1]))

    query_lower = query.casefold()
    architecture_terms = {
        "architecture", "pipeline", "workflow",
        "arquitectura", "flujo", "estructura",
    }

    # Add known entry points for broad architecture questions.
    if any(term in query_lower for term in architecture_terms):
        preferred = [
            "scripts/run_pipeline.py",
            "analyzer/run_audit.py",
        ]

        by_path = {item[1]: item for item in candidates}
        selected = [
            by_path[name]
            for name in preferred
            if name in by_path
        ]

        selected_paths = {item[1] for item in selected}

        for item in candidates:
            if item[1] not in selected_paths:
                selected.append(item)
                selected_paths.add(item[1])

            if len(selected) >= max_files:
                break

        return selected[:max_files]

    return candidates[:max_files]


def build_relevant_context(query, index_records, format_index, max_chars=18000):
    """Build a bounded source context for one user question."""
    selected = select_relevant_files(query, index_records)

    sections = [
        "VERIFIABLE PROJECT SYMBOL INDEX:",
        format_index(index_records),
        "",
        "SOURCE FILES SELECTED FOR THIS QUESTION:",
    ]

    remaining = max_chars

    for _, relative_path, content in selected:
        header = f"\n--- START OF FILE: {relative_path} ---\n"
        footer = f"\n--- END OF FILE: {relative_path} ---\n"
        available = remaining - len(header) - len(footer)

        if available <= 0:
            break

        if len(content) > available:
            content = content[:available] + "\n[File excerpt truncated.]"

        section = header + content + footer
        sections.append(section)
        remaining -= len(section)

    if not selected:
        sections.append(
            "No source files matched this question. "
            "Do not guess file paths or implementation details."
        )

    return "\n".join(sections)
def load_history() -> list:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []

def save_history(history: list):
    try:
        HISTORY_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"Error saving history: {e}")


def _open_parent_dir(root_fd, parts, create=False):
    """Open a project-relative parent directory without following symlinks."""
    current_fd = os.dup(root_fd)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW

    try:
        for part in parts:
            if create:
                try:
                    os.mkdir(part, dir_fd=current_fd)
                except FileExistsError:
                    pass

            next_fd = os.open(part, flags, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd

        return current_fd
    except Exception:
        os.close(current_fd)
        raise


def _read_project_file(root_fd, parts):
    """Read a regular file and return its contents and inode identity."""
    try:
        parent_fd = _open_parent_dir(root_fd, parts[:-1])
    except FileNotFoundError:
        return "", None

    try:
        try:
            fd = os.open(
                parts[-1],
                os.O_RDONLY | os.O_NOFOLLOW,
                dir_fd=parent_fd,
            )
        except FileNotFoundError:
            return "", None

        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise OSError("Destination is not a regular file")

            with os.fdopen(fd, "rb") as handle:
                fd = -1
                content = handle.read()

            return content.decode("utf-8"), (info.st_dev, info.st_ino)
        finally:
            if fd >= 0:
                os.close(fd)
    finally:
        os.close(parent_fd)


def _write_project_file(root_fd, parts, content, original_identity):
    """Back up and write through anchored directory descriptors."""
    parent_fd = _open_parent_dir(root_fd, parts[:-1], create=True)

    try:
        name = parts[-1]

        if original_identity is not None:
            fd = os.open(
                name,
                os.O_WRONLY | os.O_NOFOLLOW,
                dir_fd=parent_fd,
            )
            info = os.fstat(fd)

            if (
                not stat.S_ISREG(info.st_mode)
                or (info.st_dev, info.st_ino) != original_identity
            ):
                os.close(fd)
                raise OSError(
                    "Destination changed after validation; refusing to write"
                )

            # Read the original through a separate safe descriptor for backup.
            read_fd = os.open(
                name,
                os.O_RDONLY | os.O_NOFOLLOW,
                dir_fd=parent_fd,
            )
            try:
                read_info = os.fstat(read_fd)
                if (read_info.st_dev, read_info.st_ino) != original_identity:
                    os.close(fd)
                    raise OSError(
                        "Destination changed before backup; refusing to write"
                    )
                with os.fdopen(read_fd, "rb") as handle:
                    read_fd = -1
                    original_bytes = handle.read()
            finally:
                if read_fd >= 0:
                    os.close(read_fd)

            # Preserve the existing backup behavior.
            backup_fd = _open_parent_dir(
                root_fd, (".copilot_backups",), create=True
            )
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                backup_name = (
                    f"{'__'.join(parts)}.{timestamp}.bak"
                )
                backup_file_fd = os.open(
                    backup_name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=backup_fd,
                )
                with os.fdopen(backup_file_fd, "wb") as handle:
                    handle.write(original_bytes)
            finally:
                os.close(backup_fd)

            print(f"Backup saved: .copilot_backups/{backup_name}")

        else:
            # Do not overwrite a file that appeared after the initial check.
            fd = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o666,
                dir_fd=parent_fd,
            )

        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise OSError("Destination is not a regular file")

            with os.fdopen(fd, "wb") as handle:
                fd = -1
                handle.write(content.encode("utf-8"))
        finally:
            if fd >= 0:
                os.close(fd)
    finally:
        os.close(parent_fd)


def parse_and_apply_changes(response_text: str):
    """Review proposed changes and safely apply explicitly approved files."""
    project_root = Path.cwd().resolve()
    root_fd = os.open(
        project_root,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
    )

    try:
        lines = response_text.splitlines()
        i = 0

        while i < len(lines):
            line = lines[i].strip()

            if not line.startswith("FILE:"):
                i += 1
                continue

            target_file = line.removeprefix("FILE:").strip()
            i += 1

            while i < len(lines) and not lines[i].strip().startswith("```"):
                i += 1

            if i >= len(lines):
                print(f"Rejected {target_file!r}: missing code block.")
                break

            i += 1
            code_lines = []

            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1

            if i >= len(lines):
                print(f"Rejected {target_file!r}: unclosed code block.")
                break

            i += 1
            new_content = "\n".join(code_lines) + "\n"
            relative_path = Path(target_file)

            if (
                not target_file
                or relative_path.is_absolute()
                or any(part in {".", ".."} for part in relative_path.parts)
                or not relative_path.parts
            ):
                print(f"Rejected unsafe path: {target_file!r}")
                continue

            parts = relative_path.parts

            if relative_path.suffix not in ALLOWED_EXTENSIONS:
                print(f"Rejected file extension: {relative_path.suffix!r}")
                continue

            if any(part in EXCLUDED_DIRS for part in parts):
                print(f"Rejected protected directory: {target_file!r}")
                continue

            try:
                old_content, original_identity = _read_project_file(
                    root_fd, parts
                )
            except (OSError, UnicodeError) as exc:
                print(f"Could not safely read {target_file!r}: {exc}")
                continue

            if old_content == new_content:
                print(f"No changes needed for {target_file}.")
                continue

            diff = difflib.unified_diff(
                old_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=f"a/{relative_path}",
                tofile=f"b/{relative_path}",
            )

            print(f"\nProposed changes for: {relative_path}")
            print("".join(diff))

            choice = input(
                "Apply these changes? Type 'yes' to confirm: "
            ).strip()

            if choice != "yes":
                print(f"Skipped {target_file}.")
                continue

            try:
                _write_project_file(
                    root_fd, parts, new_content, original_identity
                )
                print(f"Successfully updated {relative_path}.")
            except OSError as exc:
                print(f"Could not safely write {target_file!r}: {exc}")
    finally:
        os.close(root_fd)

def process_assistant_response(response_text: str, editing_enabled: bool = False):
    """Only process file changes when the user explicitly enables edit mode."""
    if not editing_enabled:
        if "FILE:" in response_text:
            print(
                "File changes were not processed: "
                "the copilot is in read-only audit mode. "
                "Use /edit to enable editing."
            )
        return

    parse_and_apply_changes(response_text)

def chat_loop():
    editing_enabled = False

    previous_history = load_history()
    conversation = [
        message
        for message in previous_history
        if message.get("role") in {"user", "assistant"}
    ]

    try:
        rubric = RUBRIC_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        rubric = (
            "Use verifiable evidence from the supplied source code. "
            "Never invent files, functions, classes, parameters, or behavior."
        )
        print(f"Warning: rubric not found at {RUBRIC_FILE}")

    print("Building project symbol index...")

    try:
        index_records, format_index = load_project_index()
        print(f"Indexed {len(index_records)} Python definitions.")
    except Exception as exc:
        print(f"Could not build project index: {exc}")
        print("The copilot cannot start without a valid project index.")
        return

    base_system_prompt = (
        "You are a software architect and bioinformatics assistant "
        "analyzing the CURRENT version of this project.\n\n"

        "PERSISTENT QUALITY RUBRIC:\n"
        f"{rubric}\n\n"

        "STRICT SOURCE-GROUNDED ANSWERING RULES:\n"
        "1. Treat the source excerpts supplied for the current question "
        "as the primary evidence for project implementation details.\n"
        "2. Never invent or assume file paths, classes, functions, methods, "
        "parameters, libraries, endpoints, configuration values, or behavior.\n"
        "3. Mention a project symbol only if it appears in the supplied "
        "symbol index or source excerpts. For implementation details, "
        "prefer direct evidence from the source excerpts.\n"
        "4. Cite the exact source path for every substantive claim about "
        "the implementation. Use only paths explicitly shown in the "
        "supplied context.\n"
        "5. If the relevant implementation is absent, incomplete, or "
        "truncated, explicitly state that it cannot be verified from "
        "the available evidence.\n"
        "6. Never fill gaps with typical programming patterns, assumptions "
        "about libraries, or knowledge of how similar projects work.\n"
        "7. Clearly separate verified facts from suggestions. Label "
        "suggestions as proposals, not existing implementation.\n"
        "8. Previous conversation messages are not evidence that a "
        "project detail is true. If they conflict with current source "
        "evidence, follow the source evidence.\n"
        "9. Do not claim to have executed code, run tests, or modified "
        "files unless that action was actually confirmed.\n"
        "10. When proposing file changes, use FILE: path/to/file.py "
        "followed by a fenced code block.\n"
    )

    history = conversation[:]

    print(
        "\n🤖 Interactive Qwen Copilot started! "
        "Type your questions or instructions (type 'exit' or 'quit' to stop).\n"
    )

    while True:
        try:
            user_input = input("You: ").strip()

            if not user_input:
                continue

            if user_input.lower() in {"exit", "quit"}:
                print("Goodbye!")
                save_history(history)
                break

            if user_input.lower() == "/audit":
                editing_enabled = False
                print(
                    "Read-only audit mode enabled. "
                    "No proposed file changes will be applied."
                )
                continue

            if user_input.lower() == "/edit":
                editing_enabled = True
                print(
                    "Edit mode enabled. Proposed changes will be shown for "
                    "review and require explicit confirmation."
                )
                continue

            # Keep the user's original question in saved history.
            history.append({"role": "user", "content": user_input})

            relevant_context = build_relevant_context(
                user_input,
                index_records,
                format_index,
            )

            current_system_prompt = (
                base_system_prompt
                + "\n\nCURRENT QUESTION'S PROJECT EVIDENCE:\n"
                + relevant_context
            )

            request_history = [
                {"role": "system", "content": current_system_prompt},
                {"role": "user", "content": user_input},
            ]

            data = {
                "model": "qwen2.5:3b",
                "messages": request_history,
                "stream": False,
            }

            req = urllib.request.Request(
                OLLAMA_URL,
                data=json.dumps(data).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )

            print("🤖 Thinking...")

            with urllib.request.urlopen(req, timeout=500) as response:
                res_json = json.loads(response.read().decode("utf-8"))
                assistant_message = (
                    res_json.get("message", {}).get("content", "")
                ).strip()

            print(f"\nQwen:\n{assistant_message}\n")

            history.append(
                {"role": "assistant", "content": assistant_message}
            )
            save_history(history)

            process_assistant_response(
                assistant_message,
                editing_enabled,
            )

        except KeyboardInterrupt:
            print("\nSession interrupted. Saving history...")
            save_history(history)
            break
        except Exception as exc:
            print(f"\nError while processing the request: {exc}")


if __name__ == "__main__":
    chat_loop()
