import requests
import json
from typing import List
from analyzer.schemas import LogFinding

class LLMClient:
    def __init__(self, model_name: str = "qwen2.5:3b", base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.base_url = base_url

    def explain_findings(self, findings: List[LogFinding]) -> str:
        if not findings:
            return "No errors or warnings found in the log."

        findings_text = "\n".join(
            [f"- [{f.severity}] Line {f.line_number}: {f.message} (Evidence: {f.source_evidence})" for f in findings]
        )

        prompt = f"""You are a bioinformatics copilot assistant. Analyze the following log findings extracted from a pipeline execution.
Provide a concise explanation of what went wrong, strictly based on the provided evidence, and suggest a polite troubleshooting step. Do not invent errors.

Findings:
{findings_text}

Explanation and Recommendation:"""

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False
        }

        try:
            # Aumentamos el timeout a 120 segundos para la carga inicial del modelo
            response = requests.post(f"{self.base_url}/api/generate", json=payload, timeout=120)
            if response.status_code == 200:
                return response.json().get("response", "No response generated.")
            else:
                return f"Error connecting to Ollama: HTTP {response.status_code}"
        except Exception as e:
            return f"Connection error to Ollama: {str(e)}"
