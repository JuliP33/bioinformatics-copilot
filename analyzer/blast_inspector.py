import os
from typing import Dict, Any, List
from analyzer.schemas import LogFinding

class BlastInspector:
    def inspect(self, file_path: str, evalue_threshold: float = 1e-3, pident_threshold: float = 30.0) -> Dict[str, Any]:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        total_hits = 0
        findings: List[LogFinding] = []
        hits_summary = []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_idx, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue

                    parts = line.split("\t")
                    if len(parts) < 12:
                        continue # No es formato outfmt 6 estándar completo

                    total_hits += 1
                    qseqid, sseqid, pident, length, mismatch, gapopen, qstart, qend, sstart, send, evalue, bitscore = parts[:12]

                    pident_val = float(pident)
                    evalue_val = float(evalue)

                    hit_info = {
                        "query": qseqid,
                        "subject": sseqid,
                        "pident": pident_val,
                        "evalue": evalue_val,
                        "bitscore": float(bitscore)
                    }
                    hits_summary.append(hit_info)

                    # Advertencias de calidad biológica
                    if evalue_val > evalue_threshold:
                        findings.append(
                            LogFinding(
                                severity="WARNING",
                                line_number=line_idx,
                                message=f"High E-value ({evalue_val}) for query '{qseqid}' vs '{sseqid}' (possible false positive).",
                                source_evidence=line
                            )
                        )

                    if pident_val < pident_threshold:
                        findings.append(
                            LogFinding(
                                severity="WARNING",
                                line_number=line_idx,
                                message=f"Low identity ({pident_val}%) for query '{qseqid}' vs '{sseqid}'.",
                                source_evidence=line
                            )
                        )

        except Exception as e:
            findings.append(
                LogFinding(
                    severity="ERROR",
                    line_number=0,
                    message=f"Failed to parse BLAST table: {str(e)}",
                    source_evidence=file_path
                )
            )

        return {
            "file_path": file_path,
            "total_hits": total_hits,
            "findings": findings,
            "top_hits": hits_summary[:5] # Guardar los primeros 5 para resumen
        }
