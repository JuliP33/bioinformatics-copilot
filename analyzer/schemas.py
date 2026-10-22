from typing import List, Optional
from pydantic import BaseModel, Field

class LogFinding(BaseModel):
    severity: str = Field(..., description="Severity level: ERROR, WARNING, INFO")
    message: str = Field(..., description="Extracted error or warning message")
    line_number: Optional[int] = Field(None, description="Line number in the log if available")
    source_evidence: str = Field(..., description="Exact line extracted from the original log")

class AnalysisReport(BaseModel):
    run_id: str
    status: str
    findings: List[LogFinding] = []
    summary: Optional[str] = None
