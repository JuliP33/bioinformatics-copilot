import os
from typing import Dict, Any, List
from Bio import AlignIO
from analyzer.schemas import LogFinding

class MsaInspector:
    def inspect(self, file_path: str, format: str = "fasta") -> Dict[str, Any]:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        findings: List[LogFinding] = []

        try:
            alignment = AlignIO.read(file_path, format)
        except Exception as e:
            try:
                alignment = AlignIO.read(file_path, "clustal")
            except Exception as e2:
                return {
                    "file_path": file_path,
                    "findings": [
                        LogFinding(
                            severity="ERROR",
                            line_number=0,
                            message=f"Failed to parse MSA file ({str(e)} / {str(e2)})",
                            source_evidence=file_path
                        )
                    ]
                }

        num_seqs = len(alignment)
        aln_length = alignment.get_alignment_length()

        total_chars = num_seqs * aln_length
        total_gaps = 0

        for record in alignment:
            seq_str = str(record.seq)
            total_gaps += seq_str.count("-")

            seq_gap_pct = (seq_str.count("-") / aln_length) * 100
            if seq_gap_pct > 50.0:
                findings.append(
                    LogFinding(
                        severity="WARNING",
                        line_number=0,
                        message=f"Sequence '{record.id}' has high gap percentage ({round(seq_gap_pct, 2)}%).",
                        source_evidence=record.id
                    )
                )

        global_gap_pct = round((total_gaps / total_chars) * 100, 2) if total_chars > 0 else 0

        if global_gap_pct > 30.0:
            warning_msg = f"Global alignment gap percentage is high ({global_gap_pct}%). Consider re-evaluating alignment parameters."
            findings.append(
                LogFinding(
                    severity="WARNING",
                    line_number=0,
                    message=warning_msg,
                    source_evidence=file_path
                )
            )

        return {
            "file_path": file_path,
            "num_sequences": num_seqs,
            "alignment_length": aln_length,
            "global_gap_pct": global_gap_pct,
            "findings": findings
        }
