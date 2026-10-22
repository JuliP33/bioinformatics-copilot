import os
from typing import Dict, Any, List
from Bio import SeqIO
from analyzer.schemas import LogFinding

class FastaInspector:
    DNA_CHARS = set("ATGCN-")
    PROTEIN_CHARS = set("ACDEFGHIKLMNPQRSTVWY*-")

    def _detect_type(self, sequences: List[str]) -> str:
        """Determina si las secuencias son de Proteína o DNA/RNA."""
        sample_text = "".join(sequences[:10]).upper()
        # Caracteres exclusivos o muy comunes en aminoácidos que no están en DNA
        protein_specific = set("EFILPQZ")
        if any(c in sample_text for c in protein_specific):
            return "PROTEIN"
        return "DNA"

    def inspect(self, file_path: str) -> Dict[str, Any]:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        records = list(SeqIO.parse(file_path, "fasta"))
        total_sequences = len(records)
        total_units = 0
        lengths: List[int] = []
        gc_count = 0
        findings: List[LogFinding] = []

        if total_sequences == 0:
            return {
                "file_path": file_path,
                "molecule_type": "UNKNOWN",
                "total_sequences": 0,
                "total_units": 0,
                "findings": [
                    LogFinding(
                        severity="WARNING",
                        line_number=0,
                        message="FASTA file is empty or contains no valid headers.",
                        source_evidence=file_path
                    )
                ]
            }

        # Detectar si es Proteína o DNA
        raw_seqs = [str(r.seq) for r in records]
        seq_type = self._detect_type(raw_seqs)
        valid_alphabet = self.PROTEIN_CHARS if seq_type == "PROTEIN" else self.DNA_CHARS

        for idx, record in enumerate(records, 1):
            seq_str = str(record.seq).upper()
            seq_len = len(seq_str)
            lengths.append(seq_len)
            total_units += seq_len

            if seq_type == "DNA":
                gc_count += seq_str.count('G') + seq_str.count('C')

            # Detección de secuencias vacías
            if seq_len == 0:
                findings.append(
                    LogFinding(
                        severity="WARNING",
                        line_number=idx,
                        message=f"Sequence ID '{record.id}' is empty (0 len).",
                        source_evidence=f">{record.id}"
                    )
                )

            # Validar caracteres extraños segun el tipo de molécula
            invalid_chars = set(seq_str) - valid_alphabet
            if invalid_chars:
                findings.append(
                    LogFinding(
                        severity="WARNING",
                        line_number=idx,
                        message=f"Sequence ID '{record.id}' ({seq_type}) contains non-standard characters: {list(invalid_chars)}",
                        source_evidence=f">{record.id}"
                    )
                )

        min_len = min(lengths) if lengths else 0
        max_len = max(lengths) if lengths else 0
        avg_len = round(total_units / total_sequences, 2) if total_sequences > 0 else 0

        metrics = {
            "file_path": file_path,
            "molecule_type": seq_type,
            "total_sequences": total_sequences,
            "total_units": total_units,
            "unit_label": "aa" if seq_type == "PROTEIN" else "bp",
            "min_length": min_len,
            "max_length": max_len,
            "avg_length": avg_len,
            "findings": findings
        }

        if seq_type == "DNA":
            metrics["gc_content_pct"] = round((gc_count / total_units) * 100, 2) if total_units > 0 else 0

        return metrics
