import re
from typing import List
from analyzer.schemas import LogFinding

class LogParser:
    def __init__(self):
        # Patrón para detectar líneas de log con formato: [SEVERIDAD] timestamp - mensaje
        self.pattern = re.compile(r'\[(ERROR|WARNING|INFO)\]\s+(.*)')

    def parse_content(self, content: str) -> List[LogFinding]:
        findings = []
        for line_num, line in enumerate(content.splitlines(), start=1):
            match = self.pattern.search(line)
            if match:
                severity, message = match.groups()
                # Solo guardamos errores y advertencias para el reporte principal
                if severity in ["ERROR", "WARNING"]:
                    findings.append(
                        LogFinding(
                            severity=severity,
                            message=message.strip(),
                            line_number=line_num,
                            source_evidence=line.strip()
                        )
                    )
        return findings

    def parse_file(self, file_path: str) -> List[LogFinding]:
        with open(file_path, 'r', encoding='utf-8') as f:
            return self.parse_content(f.read())
