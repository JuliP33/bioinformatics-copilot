import os
import re
import shutil
import tempfile
import subprocess
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List
from Bio import SeqIO
from analyzer.log_parser import LogFinding

try:
    import duckdb
    USE_DUCKDB = True
except ImportError:
    USE_DUCKDB = False


class AssemblyInspector:
    def __init__(self, db_path: str = "outputs_audit/audit_cache.duckdb", max_workers: int = 6):
        self.db_path = db_path
        self.max_workers = max_workers
        self.db_lock = threading.Lock()

        if USE_DUCKDB:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            with self.db_lock:
                conn = duckdb.connect(self.db_path)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS tblastn_cache (
                        protein_id VARCHAR PRIMARY KEY,
                        assembly_path VARCHAR,
                        hit_found BOOLEAN,
                        hit_details VARCHAR
                    )
                """)
                conn.close()

    def _get_cached_hit(self, protein_id: str, assembly_path: str):
        if not USE_DUCKDB or not os.path.exists(self.db_path):
            return None
        try:
            with self.db_lock:
                conn = duckdb.connect(self.db_path)
                res = conn.execute(
                    "SELECT hit_found, hit_details FROM tblastn_cache WHERE protein_id = ? AND assembly_path = ?",
                    [protein_id, assembly_path]
                ).fetchone()
                conn.close()
            if res is not None:
                return {"hit_found": bool(res[0]), "hit_details": res[1]}
        except Exception as e:
            logging.debug(f"DuckDB cache read error: {e}")
        return None

    def _save_cached_hit(self, protein_id: str, assembly_path: str, hit_found: bool, hit_details: str):
        if not USE_DUCKDB:
            return
        try:
            with self.db_lock:
                conn = duckdb.connect(self.db_path)
                conn.execute(
                    "INSERT OR REPLACE INTO tblastn_cache VALUES (?, ?, ?, ?)",
                    [protein_id, assembly_path, hit_found, hit_details]
                )
                conn.close()
        except Exception as e:
            logging.debug(f"DuckDB cache write error: {e}")

    def _clean_id(self, raw_id: str) -> str:
        cleaned = re.sub(r"^(gene:|transcript:|protein:|cds:)", "", raw_id.strip(), flags=re.IGNORECASE)
        return cleaned

    def _evaluate_protein(self, p_id: str, p_seq: str, assembly_path: str, tblastn_bin: str) -> tuple:
        """Evaluates a single protein via cache or tblastn execution."""
        cached = self._get_cached_hit(p_id, assembly_path)
        if cached is not None:
            return p_id, cached["hit_found"], cached["hit_details"], True

        hit_found = False
        hit_details = ""

        if tblastn_bin:
            with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".fasta") as tmp_q:
                tmp_q.write(f">{p_id}\n{p_seq}\n")
                tmp_q_path = tmp_q.name

            cmd = [
                tblastn_bin,
                "-query", tmp_q_path,
                "-subject", assembly_path,
                "-outfmt", "6 sseqid pident evalue bitscore",
                "-max_target_seqs", "1",
                "-num_threads", "1"  # Forzamos 1 hilo por subtarea para controlar la carga global
            ]
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
                if res.returncode == 0 and res.stdout.strip():
                    top_hit = res.stdout.strip().split("\n")[0].split("\t")
                    if len(top_hit) >= 4 and float(top_hit[2]) < 1e-5:
                        hit_found = True
                        hit_details = f"scaffold: {top_hit[0]}, identity: {top_hit[1]}%, evalue: {top_hit[2]}"
            except Exception:
                pass
            if os.path.exists(tmp_q_path):
                os.remove(tmp_q_path)
        else:
            with open(assembly_path, "r", encoding="utf-8", errors="ignore") as af:
                if p_id in af.read():
                    hit_found = True
                    hit_details = "Header/string match"

        self._save_cached_hit(p_id, assembly_path, hit_found, hit_details)
        return p_id, hit_found, hit_details, False

    def inspect_pipeline(self, protein_fasta: str, gff3_file: str, assembly_fasta: str) -> Dict[str, Any]:
        if not os.path.exists(protein_fasta):
            raise FileNotFoundError(f"Protein file not found: {protein_fasta}")
        if assembly_fasta and not os.path.exists(assembly_fasta):
            raise FileNotFoundError(f"Assembly FASTA not found: {assembly_fasta}")

        findings: List[LogFinding] = []

        # 1. Parse Query Proteins
        logging.info(f"Parsing query protein FASTA: {protein_fasta}...")
        query_proteins = {}
        for rec in SeqIO.parse(protein_fasta, "fasta"):
            clean_pid = self._clean_id(rec.id)
            query_proteins[clean_pid] = str(rec.seq)

        # 2. Parse GFF3 with Normalized Attribute Extraction
        gff_annotated_ids = set()
        if gff3_file and os.path.exists(gff3_file):
            logging.info(f"Parsing GFF3 annotation file: {gff3_file}...")
            with open(gff3_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.startswith("#") or not line.strip():
                        continue
                    parts = line.split("\t")
                    if len(parts) >= 9:
                        attrs = parts[8].split(";")
                        for attr in attrs:
                            if "=" in attr:
                                key, val = attr.split("=", 1)
                                key = key.strip()
                                val = val.strip()
                                if key in ["ID", "Name", "Parent", "protein_id", "transcript_id", "gene_id"]:
                                    cleaned_val = self._clean_id(val)
                                    gff_annotated_ids.add(cleaned_val)
                                    if "," in cleaned_val:
                                        for sub_val in cleaned_val.split(","):
                                            gff_annotated_ids.add(self._clean_id(sub_val))

        consistent_genes = []
        annotation_gaps = []
        assembly_gaps = []

        missing_in_gff = [p_id for p_id in query_proteins.keys() if p_id not in gff_annotated_ids] if gff3_file else list(query_proteins.keys())
        if gff3_file:
            consistent_genes = [p_id for p_id in query_proteins.keys() if p_id in gff_annotated_ids]

        logging.info(f"Summary after normalized matching: {len(consistent_genes)} consistent features, {len(missing_in_gff)} missing in GFF3 to evaluate via tblastn.")

        if not assembly_fasta:
            for p_id in missing_in_gff:
                findings.append(
                    LogFinding(
                        severity="WARNING",
                        line_number=0,
                        message=f"Target gene/feature '{p_id}' is ABSENT from local GFF3 annotation.",
                        source_evidence=gff3_file or protein_fasta
                    )
                )
            return {
                "protein_fasta": protein_fasta,
                "gff3_file": gff3_file,
                "assembly_fasta": None,
                "total_queries": len(query_proteins),
                "consistent_count": len(consistent_genes),
                "annotation_gap_count": len(missing_in_gff),
                "assembly_gap_count": 0,
                "findings": findings
            }

        tblastn_bin = shutil.which("tblastn")

        # 3. Parallelized Granular Evaluation
        total_to_scan = len(missing_in_gff)
        completed_count = 0
        cached_count = 0

        logging.info(f"Launching parallel QC scan using {self.max_workers} worker threads...")

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._evaluate_protein, p_id, query_proteins[p_id], assembly_fasta, tblastn_bin): p_id
                for p_id in missing_in_gff
            }

            for future in as_completed(futures):
                p_id, hit_found, hit_details, was_cached = future.result()
                completed_count += 1
                if was_cached:
                    cached_count += 1

                if completed_count % 200 == 0 or completed_count == total_to_scan:
                    logging.info(f"QC Progress: Evaluated {completed_count}/{total_to_scan} (Cached hits: {cached_count})")

                if hit_found:
                    annotation_gaps.append(p_id)
                    findings.append(
                        LogFinding(
                            severity="WARNING",
                            line_number=0,
                            message=f"ANNOTATION GAP: Protein '{p_id}' is missing from GFF3, but WAS FOUND in assembly via tblastn ({hit_details}).",
                            source_evidence=assembly_fasta
                        )
                    )
                else:
                    assembly_gaps.append(p_id)
                    findings.append(
                        LogFinding(
                            severity="ERROR",
                            line_number=0,
                            message=f"ASSEMBLY GAP: Protein '{p_id}' is missing from GFF3 AND NOT FOUND in assembly.",
                            source_evidence=assembly_fasta
                        )
                    )

        return {
            "protein_fasta": protein_fasta,
            "gff3_file": gff3_file,
            "assembly_fasta": assembly_fasta,
            "total_queries": len(query_proteins),
            "consistent_count": len(consistent_genes),
            "annotation_gap_count": len(annotation_gaps),
            "assembly_gap_count": len(assembly_gaps),
            "findings": findings
        }
