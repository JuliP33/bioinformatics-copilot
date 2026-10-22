import importlib.util
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "project_index.py"
)

spec = importlib.util.spec_from_file_location("project_index", SCRIPT)
project_index = importlib.util.module_from_spec(spec)
spec.loader.exec_module(project_index)


def test_indexes_real_classes_and_methods(tmp_path):
    source = tmp_path / "example.py"
    source.write_text(
        "class Example:\n"
        "    def run(self):\n"
        "        def nested():\n"
        "            pass\n"
        "        return nested()\n",
        encoding="utf-8",
    )

    records = project_index.index_python_files(tmp_path)

    actual = {
        (item["kind"], item["qualified_name"])
        for item in records
    }

    assert ("class", "Example") in actual
    assert ("function", "Example.run") in actual
    assert ("function", "Example.run.nested") in actual


def test_records_relative_paths_and_line_numbers(tmp_path):
    folder = tmp_path / "analyzer"
    folder.mkdir()
    source = folder / "example.py"
    source.write_text(
        "\nclass Example:\n    pass\n",
        encoding="utf-8",
    )

    records = project_index.index_python_files(tmp_path)

    record = next(item for item in records if item["name"] == "Example")

    assert record["path"] == "analyzer/example.py"
    assert record["line"] == 2


def test_skips_syntax_errors_and_excluded_directories(tmp_path):
    (tmp_path / "broken.py").write_text(
        "def broken(:\n",
        encoding="utf-8",
    )

    excluded = tmp_path / "outputs"
    excluded.mkdir()
    (excluded / "ignored.py").write_text(
        "def ignored(): pass\n",
        encoding="utf-8",
    )

    records = project_index.index_python_files(tmp_path)

    assert records == []


def test_formats_qualified_names():
    text = project_index.format_index(
        [
            {
                "path": "example.py",
                "kind": "function",
                "name": "run",
                "qualified_name": "Example.run",
                "scope": "Example",
                "line": 3,
                "end_line": 5,
            }
        ]
    )

    assert text == "example.py:3 function Example.run [Example]"
