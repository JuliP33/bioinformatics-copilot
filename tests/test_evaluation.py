import pytest
import os
from analyzer.log_parser import LogParser
from analyzer.schemas import LogFinding, AnalysisReport
from analyzer.report import ReportGenerator

def test_parser_with_clean_log(tmp_path):
    clean_log = tmp_path / "clean.log"
    clean_log.write_text("2026-10-20 10:00:00 - INFO - Pipeline started successfully.\n2026-10-20 10:00:05 - INFO - Step completed.")

    parser = LogParser()
    findings = parser.parse_file(str(clean_log))
    assert len(findings) == 0

def test_report_generation(tmp_path):
    db_file = tmp_path / "test_audit.db"
    out_dir = tmp_path / "test_outputs"

    generator = ReportGenerator(db_path=str(db_file), output_dir=str(out_dir))

    findings = [
        LogFinding(
            severity="ERROR",
            line_number=10,
            message="Test error message",
            source_evidence="Test error message"
        )
    ]

    run_output = generator.save_run(
        run_id="run_test_123",
        status="SUCCESS",
        model_name="qwen2.5:3b",
        findings=findings,
        duration=1.23,
        explanation="This is a test explanation."
    )

    assert os.path.exists(os.path.join(run_output, "result.json"))
    assert os.path.exists(os.path.join(run_output, "report.md"))

    # Verificar que se guardó en SQLite
    import sqlite3
    with sqlite3.connect(str(db_file)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT findings_count, status FROM audit_runs WHERE run_id = 'run_test_123'")
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == 1
        assert row[1] == "SUCCESS"
