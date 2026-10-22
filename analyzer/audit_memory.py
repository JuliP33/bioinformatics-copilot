import sqlite3
import os
from typing import List, Dict, Any

class AuditMemory:
    def __init__(self, db_path: str = "audit.db"):
        self.db_path = db_path

    def get_past_runs(self, limit: int = 5) -> List[Dict[str, Any]]:
        if not os.path.exists(self.db_path):
            return []

        runs = []
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT run_id, timestamp, status, model_name, findings_count, duration_seconds
                    FROM audit_runs
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (limit,))
                for row in cursor.fetchall():
                    runs.append(dict(row))
        except Exception:
            pass

        return runs

    def format_memory_context(self) -> str:
        past_runs = self.get_past_runs(limit=3)
        if not past_runs:
            return "No previous audit history available in database."

        context = "Recent Pipeline Audit History (Cross-Audit Memory):\n"
        for run in past_runs:
            context += f"- Run ID: {run['run_id']} | Date: {run['timestamp']} | Status: {run['status']} | Issues Found: {run['findings_count']}\n"

        return context
