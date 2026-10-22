import pytest
from analyzer.log_parser import LogParser

def test_log_parser():
    parser = LogParser()
    sample_log = (
        "[INFO] 2026-10-20 10:00:00 - Starting execution...\n"
        "[WARNING] 2026-10-20 10:00:05 - Low quality score detected.\n"
        "[ERROR] 2026-10-20 10:01:10 - Tool failed with code 1.\n"
    )
    findings = parser.parse_content(sample_log)

    assert len(findings) == 2
    assert findings[0].severity == "WARNING"
    assert findings[0].line_number == 2
    assert findings[1].severity == "ERROR"
    assert findings[1].line_number == 3
    assert "Tool failed" in findings[1].message
