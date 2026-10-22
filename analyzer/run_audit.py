import sys
import os
import time
import uuid
import argparse
from analyzer.log_parser import LogParser
from analyzer.fasta_inspector import FastaInspector
from analyzer.blast_inspector import BlastInspector
from analyzer.msa_inspector import MsaInspector
from analyzer.annotation_inspector import AnnotationInspector
from analyzer.assembly_inspector import AssemblyInspector
from analyzer.audit_memory import AuditMemory
from analyzer.llm_client import LLMClient
from analyzer.report import ReportGenerator

def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bioinformatics Copilot: Advanced Local AI Assistant for Pipelines, FASTA, BLAST, MSA, and Genome Assemblies."
    )
    parser.add_argument(
        "-i", "--input",
        type=str,
        default="examples/sample.log",
        help="Path to the main file to inspect/audit (.log, .fasta, .tsv/.blast, .aln, or target list). Default: examples/sample.log"
    )
    parser.add_argument(
        "-a", "--annotations",
        type=str,
        default=None,
        help="Path to a local genome annotation file (e.g., .gff3, .gtf) to cross-check missing features."
    )
    parser.add_argument(
        "-g", "--genome-assembly",
        type=str,
        default=None,
        help="Path to a local target genome assembly FASTA file (.fasta, .fna) to search for query features."
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=str,
        default="outputs",
        help="Directory where output reports will be saved. Default: outputs"
    )
    parser.add_argument(
        "-m", "--model",
        type=str,
        default="qwen2.5:3b",
        help="Ollama model name to use for reasoning. Default: qwen2.5:3b"
    )
    return parser

def main():
    cli_parser = build_cli_parser()
    args = cli_parser.parse_args()

    file_path = args.input
    if not os.path.exists(file_path):
        print(f"Error: File not found at '{file_path}'")
        sys.exit(1)

    run_id = f"run_{uuid.uuid4().hex[:8]}"
    start_time = time.time()

    print(f"--- Starting Advanced Audit Run: {run_id} ---")
    print(f"Target File: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()
    findings = []
    extra_summary = ""

    if args.genome_assembly and args.annotations:
        print(f"\n--- Running 3-Tier Genomic Quality Inspector (Query vs GFF3 vs tblastn Assembly) ---")
        inspector = AssemblyInspector()
        metrics = inspector.inspect_pipeline(file_path, args.annotations, args.genome_assembly)
        findings = metrics["findings"]
        extra_summary = (
            f"3-Tier Genomic Audit Summary:\n"
            f"- Query Protein File: {metrics['protein_fasta']}\n"
            f"- GFF3 Annotation File: {metrics['gff3_file']}\n"
            f"- Assembly FASTA File: {metrics['assembly_fasta']}\n"
            f"- Consistent Genes (Annotated & Found): {metrics['consistent_count']}\n"
            f"- Annotation Gaps (Found via tblastn, Missing in GFF3): {metrics['annotation_gap_count']}\n"
            f"- Assembly Gaps (Missing in GFF3 AND Missing in Assembly): {metrics['assembly_gap_count']}\n"
        )
    elif args.genome_assembly:
        if not os.path.exists(args.genome_assembly):
            print(f"Error: Genome assembly file not found at '{args.genome_assembly}'")
            sys.exit(1)

        print(f"\n--- Running Assembly Inspector (Query vs Assembly: {args.genome_assembly}) ---")
        inspector = AssemblyInspector()
        metrics = inspector.inspect_pipeline(file_path, None, args.genome_assembly)
        findings = metrics["findings"]
        extra_summary = (
            f"Genome Assembly Search Summary:\n"
            f"- Query FASTA: {metrics['protein_fasta']}\n"
            f"- Assembly Target: {metrics['assembly_fasta']}\n"
            f"- Total Query Features Checked: {metrics['total_queries']}\n"
            f"- Annotation Gaps / Found: {metrics['annotation_gap_count']}\n"
            f"- Assembly Gaps / Missing: {metrics['assembly_gap_count']}\n"
        )
    elif args.annotations:
        if not os.path.exists(args.annotations):
            print(f"Error: Annotation file not found at '{args.annotations}'")
            sys.exit(1)

        print(f"\n--- Running Genome Annotation Inspector vs {args.annotations} ---")
        inspector = AnnotationInspector()
        metrics = inspector.check_missing_annotations(file_path, args.annotations)
        findings = metrics["findings"]
        extra_summary = (
            f"Genome Annotation Cross-Check:\n"
            f"- Target List File: {metrics['target_list_file']}\n"
            f"- Annotation DB File: {metrics['annotation_db_file']}\n"
            f"- Total Targets Checked: {metrics['total_targets_checked']}\n"
            f"- Missing Features Detected: {metrics['missing_count']}\n"
        )
    elif ext in [".fasta", ".fa", ".faa", ".fna"]:
        print("\n--- Running Scientific FASTA Inspector ---")
        inspector = FastaInspector()
        metrics = inspector.inspect(file_path)
        findings = metrics["findings"]
        unit = metrics.get("unit_label", "units")
        mol_type = metrics.get("molecule_type", "UNKNOWN")
        gc_info = f", GC Content: {metrics['gc_content_pct']}%" if "gc_content_pct" in metrics else ""
        extra_summary = (
            f"FASTA File Inspection ({mol_type}):\n"
            f"- Total Sequences: {metrics['total_sequences']}\n"
            f"- Length Range: {metrics['min_length']} - {metrics['max_length']} {unit} (Avg: {metrics['avg_length']} {unit}){gc_info}\n"
        )
    elif ext in [".blast", ".tsv", ".txt"] and "blast" in file_path.lower():
        print("\n--- Running BLAST Results Inspector ---")
        inspector = BlastInspector()
        metrics = inspector.inspect(file_path)
        findings = metrics["findings"]
        extra_summary = (
            f"BLAST Results Inspection:\n"
            f"- Total HSP Hits: {metrics['total_hits']}\n"
        )
    elif ext in [".aln", ".clustal"]:
        print("\n--- Running MSA Quality Inspector ---")
        inspector = MsaInspector()
        metrics = inspector.inspect(file_path)
        findings = metrics["findings"]
        extra_summary = (
            f"Multiple Sequence Alignment (MSA) Inspection:\n"
            f"- Sequences: {metrics['num_sequences']}\n"
            f"- Alignment Length: {metrics['alignment_length']} columns\n"
            f"- Global Gap Percentage: {metrics['global_gap_pct']}%\n"
        )
    else:
        print("\n--- Running Deterministic Log Parser ---")
        parser = LogParser()
        findings = parser.parse_file(file_path)

    print(f"Found {len(findings)} issues/warnings.")
    for f in findings:
        print(f"  [{f.severity}] Line {f.line_number}: {f.message}")

    print("\n--- Fetching Cross-Audit Memory from SQLite ---")
    memory = AuditMemory()
    memory_context = memory.format_memory_context()
    print(memory_context.strip())

    print(f"\n--- Querying Local LLM (Ollama / {args.model}) ---")
    client = LLMClient(model_name=args.model)

    raw_explanation = client.explain_findings(findings)
    final_ai_report = f"{extra_summary}\n{memory_context}\n### AI Assessment & Recommendations\n{raw_explanation}"

    print("\n--- LLM Explanation & Recommendation ---")
    print(final_ai_report)

    duration = round(time.time() - start_time, 2)
    status = "SUCCESS" if findings else "CLEAN"

    print("\n--- Saving Outputs & SQLite Audit Record ---")
    generator = ReportGenerator(output_dir=args.output_dir)
    out_dir = generator.save_run(
        run_id=run_id,
        status=status,
        model_name=args.model,
        findings=findings,
        duration=duration,
        explanation=final_ai_report
    )

    print(f"Audit completed in {duration}s!")
    print(f"Outputs saved to: {out_dir}/")

if __name__ == "__main__":
    main()
