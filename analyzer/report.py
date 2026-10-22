import json
import sqlite3
import os
from datetime import datetime
from typing import List
from analyzer.schemas import LogFinding, AnalysisReport

class ReportGenerator:
    def __init__(self, db_path: str = "audit.db", output_dir: str = "outputs"):
        self.db_path = db_path
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_runs (
                    run_id TEXT PRIMARY KEY,
                    timestamp TEXT,
                    status TEXT,
                    model_name TEXT,
                    findings_count INTEGER,
                    duration_seconds REAL
                )
            """)
            conn.commit()

    def save_run(self, run_id: str, status: str, model_name: str, findings: List[LogFinding], duration: float, explanation: str):
        timestamp = datetime.utcnow().isoformat()

        # 1. Crear objeto de reporte estructurado
        report = AnalysisReport(
            run_id=run_id,
            status=status,
            findings=findings,
            summary=explanation
        )

        # 2. Guardar JSON y Markdown en la carpeta de outputs
        run_output_dir = os.path.join(self.output_dir, run_id)
        os.makedirs(run_output_dir, exist_ok=True)

        json_path = os.path.join(run_output_dir, "result.json")
        with open(json_path, "w", encoding="utf-8") as f:
            f.write(report.model_dump_json(indent=2))

        md_path = os.path.join(run_output_dir, "report.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# Bioinformatics Copilot Audit Report\n\n")
            f.write(f"- **Run ID:** {run_id}\n")
            f.write(f"- **Timestamp:** {timestamp}\n")
            f.write(f"- **Status:** {status}\n")
            f.write(f"- **Model:** {model_name}\n\n")
            f.write(f"## Executive Summary & Explanation\n\n{explanation}\n\n")
            f.write(f"## Findings ({len(findings)})\n\n")
            for finding in findings:
                f.write(f"- **[{finding.severity}]** Line {finding.line_number}: {finding.message}\n")
                f.write(f"  - *Evidence:* `{finding.source_evidence}`\n")

        # 3. Registrar metadatos en SQLite
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO audit_runs (run_id, timestamp, status, model_name, findings_count, duration_seconds)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (run_id, timestamp, status, model_name, len(findings), duration))
            conn.commit()

        return run_output_dir
