import os
import sys
import shutil
import subprocess
import zipfile
import logging
import argparse
import urllib.request
import json
from pathlib import Path

logging.basicConfig(
    filename="workflow_audit.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
console = logging.StreamHandler(sys.stdout)
console.setLevel(logging.INFO)
logging.getLogger("").addHandler(console)

def query_local_qwen(prompt: str) -> str:
    url = "http://localhost:11434/api/generate"
    data = {
        "model": "qwen2.5:3b",
        "prompt": prompt,
        "stream": False
    }
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=60) as response:
            res_json = json.loads(response.read().decode('utf-8'))
            return res_json.get("response", "").strip()
    except Exception as e:
        logging.warning(f"Could not connect to local Qwen ({e}). Falling back.")
        return ""

def parse_args():
    parser = argparse.ArgumentParser(description="Genomic Pipeline Orchestrated by Qwen with Per-Species DuckDB Cache File")
    parser.add_argument("-s", "--species", type=str, required=True, help="Scientific name of target species")
    parser.add_argument("-o", "--output-dir", type=str, default="outputs_audit", help="Output directory for reports")
    parser.add_argument("--force-redownload", action="store_true", help="Force redownloading sequence files")
    return parser.parse_args()

def check_matching_local_files(species_dir: Path, target_db: str):
    """
    Checks if local files exist in data/<species>/ and match Qwen's chosen database source.
    """
    fna, gff, faa = None, None, None
    sanitized_name = species_dir.name
    if target_db == "ENSEMBL":
        fna_candidate = species_dir / f"{sanitized_name}_ensembl.fna"
        gff_candidate = species_dir / f"{sanitized_name}_ensembl.gff3"
        faa_candidate = species_dir / f"{sanitized_name}_ensembl.faa"
        if fna_candidate.exists() and fna_candidate.stat().st_size > 0: fna = str(fna_candidate)
        if gff_candidate.exists() and gff_candidate.stat().st_size > 0: gff = str(gff_candidate)
        if faa_candidate.exists() and faa_candidate.stat().st_size > 0: faa = str(faa_candidate)
    else:  # NCBI check
        data_root = species_dir / "ncbi_dataset" / "data"
        if data_root.exists():
            for path in data_root.rglob("*"):
                if path.suffix == ".fna" and not fna: fna = str(path)
                elif path.suffix == ".gff" and not gff: gff = str(path)
                elif path.name.endswith("protein.faa") and not faa: faa = str(path)

    return fna, gff, faa

def download_ensembl_data(species_name: str, species_dir: Path):
    sanitized_species = species_name.lower().replace(" ", "_")
    logging.info(f"Downloading from Ensembl Plants FTP for: {species_name}...")
    base_url = "https://ftp.ensemblgenomes.ebi.ac.uk/pub/plants/current"
    dna_url = f"{base_url}/fasta/{sanitized_species}/dna/"
    gff_url = f"{base_url}/gff3/{sanitized_species}/"
    pep_url = f"{base_url}/fasta/{sanitized_species}/pep/"

    dna_path = species_dir / f"{sanitized_species}_ensembl.fna"
    gff3_path = species_dir / f"{sanitized_species}_ensembl.gff3"
    protein_path = species_dir / f"{sanitized_species}_ensembl.faa"

    def fetch_first_match(target_url: str, dest_path: Path, ext_match: str):
        try:
            req = urllib.request.Request(target_url, headers={'User-Agent': 'Mozilla/5.0'})
            html = urllib.request.urlopen(req).read().decode('utf-8')
            for line in html.split('\n'):
                if ext_match in line and 'href=' in line:
                    filename = line.split('href="')[1].split('"')[0]
                    download_url = target_url + filename
                    logging.info(f"Downloading {filename}...")
                    gz_dest = Path(str(dest_path) + ".gz")
                    urllib.request.urlretrieve(download_url, gz_dest)
                    import gzip
                    with gzip.open(gz_dest, 'rb') as f_in:
                        with open(dest_path, 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)
                    os.remove(gz_dest)
                    return str(dest_path)
        except Exception as e:
            logging.warning(f"Fetch failed for {ext_match} from {target_url}: {e}")
        return None

    assembly_file = fetch_first_match(dna_url, dna_path, ".dna.toplevel.fa.gz") or fetch_first_match(dna_url, dna_path, ".dna.primary_assembly.fa.gz")
    gff3_file = fetch_first_match(gff_url, gff3_path, ".gff3.gz")
    protein_file = fetch_first_match(pep_url, protein_path, ".pep.all.fa.gz")
    return assembly_file, gff3_file, protein_file

def download_ncbi_data(species_name: str, species_dir: Path):
    datasets_bin = shutil.which("datasets")
    if not datasets_bin:
        logging.error("NCBI Datasets CLI ('datasets') not found.")
        return None, None, None

    zip_path = species_dir / "ncbi_dataset.zip"
    logging.info(f"Downloading from NCBI Datasets for: {species_name}...")
    cmd = [
        datasets_bin, "download", "genome", "taxon", species_name,
        "--include", "genome,gff3,protein",
        "--filename", str(zip_path)
    ]
    assembly_file, gff3_file, protein_file = None, None, None
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(species_dir)
        if zip_path.exists():
            os.remove(zip_path)

        data_root = species_dir / "ncbi_dataset" / "data"
        if data_root.exists():
            for path in data_root.rglob("*"):
                if path.suffix == ".fna" and not assembly_file:
                    assembly_file = str(path)
                elif path.suffix == ".gff" and not gff3_file:
                    gff3_file = str(path)
                elif path.name.endswith("protein.faa") and not protein_file:
                    protein_file = str(path)
    except Exception as e:
        logging.warning(f"NCBI download issue: {e}")

    return assembly_file, gff3_file, protein_file

def run_pipeline():
    args = parse_args()
    species_name = args.species
    sanitized_species = species_name.lower().replace(" ", "_")
    species_data_dir = Path("data") / sanitized_species
    species_data_dir.mkdir(parents=True, exist_ok=True)

    logging.info(f"=== Starting Qwen-Orchestrated Genomic Pipeline for: {species_name} ===")

    # 1. Consult local Qwen agent FIRST on taxonomic strategy & source selection
    logging.info("Consulting local Qwen agent on taxonomic strategy and primary database source...")
    strategy_prompt = (
        f"You are an expert bioinformatician. For species '{species_name}', "
        f"choose between NCBI Datasets or Ensembl Plants to ensure assembly and GFF3 version consistency.\n"
        f"Reply ONLY in JSON format: {{\"database\": \"NCBI\"|\"ENSEMBL\", \"reason\": \"explanation\"}}"
    )
    qwen_raw_response = query_local_qwen(strategy_prompt)
    chosen_db = "NCBI"
    qwen_reason = qwen_raw_response

    try:
        start_idx = qwen_raw_response.find('{')
        end_idx = qwen_raw_response.rfind('}') + 1
        if start_idx != -1 and end_idx != 0:
            parsed = json.loads(qwen_raw_response[start_idx:end_idx])
            chosen_db = parsed.get("database", "NCBI").upper()
            qwen_reason = parsed.get("reason", qwen_raw_response)
    except Exception:
        pass

    logging.info(f"Qwen Selected Source: {chosen_db}")
    logging.info(f"Qwen Reason: {qwen_reason}")

    # 2. Check if matching version files for Qwen's chosen database already exist locally
    assembly_file, gff3_file, protein_file = None, None, None
    if not args.force_redownload:
        assembly_file, gff3_file, protein_file = check_matching_local_files(species_data_dir, chosen_db)

    if assembly_file and gff3_file and protein_file:
        logging.info(f"--> Valid local dataset matching Qwen's choice ({chosen_db}) detected! Skipping re-download.")
    else:
        logging.info(f"--> Local files missing or mismatched with {chosen_db}. Executing fetch...")
        if chosen_db == "ENSEMBL":
            assembly_file, gff3_file, protein_file = download_ensembl_data(species_name, species_data_dir)
            if not assembly_file or not gff3_file or not protein_file:
                logging.warning("Ensembl fetch incomplete. Falling back to NCBI Datasets...")
                ncbi_a, ncbi_g, ncbi_p = download_ncbi_data(species_name, species_data_dir)
                assembly_file = assembly_file or ncbi_a
                gff3_file = gff3_file or ncbi_g
                protein_file = protein_file or ncbi_p
        else:
            assembly_file, gff3_file, protein_file = download_ncbi_data(species_name, species_data_dir)
            if not gff3_file or not protein_file:
                logging.warning("NCBI fetch incomplete. Falling back to Ensembl Plants...")
                ens_a, env_g, ens_p = download_ensembl_data(species_name, species_data_dir)
                assembly_file = assembly_file or ens_a
                gff3_file = gff3_file or env_g
                protein_file = protein_file or ens_p

    logging.info(f"Final Assembly File: {assembly_file}")
    logging.info(f"Final GFF3 File: {gff3_file}")
    logging.info(f"Final Protein File: {protein_file}")

    if not assembly_file:
        logging.error("No valid genome assembly available.")
        sys.exit(1)

    # 3. Path for the isolated per-species DuckDB cache file
    species_cache_db = str(species_data_dir / "audit_cache.duckdb")

    run_id = f"run_{sanitized_species}"

    # 4. Perform 3-Tier Genomic QC Inspection
    try:
        from analyzer.assembly_inspector import AssemblyInspector
        from analyzer.report import ReportGenerator
    except ImportError as e:
        logging.error(f"Failed to import local modules: {e}")
        sys.exit(1)

    logging.info(f"Executing 3-tier genomic QC inspection with species-specific DuckDB cache ({species_cache_db})...")
    inspector = AssemblyInspector(db_path=species_cache_db)
    metrics = inspector.inspect_pipeline(protein_file or assembly_file, gff3_file or assembly_file, assembly_file)

    metrics_summary = (
        f"Audit Evaluation Metrics:\n"
        f"- Total Queries Evaluated: {metrics['total_queries']}\n"
        f"- Consistent Features: {metrics['consistent_count']}\n"
        f"- Annotation Gaps: {metrics['annotation_gap_count']}\n"
        f"- Assembly Gaps: {metrics['assembly_gap_count']}"
    )

    logging.info("Generating biological analysis report with Qwen...")
    analysis_prompt = f"Analyze these genomic QC metrics for '{species_name}' (Source: {chosen_db}):\n\n{metrics_summary}"
    qwen_report_analysis = query_local_qwen(analysis_prompt)

    detailed_explanation = (
        f"=== Qwen Agent Orchestration & Audit Summary ===\n"
        f"Database Source: {chosen_db}\n"
        f"Reasoning:\n{qwen_reason}\n\n"
        f"{metrics_summary}\n\n"
        f"Biological Analysis:\n{qwen_report_analysis}"
    )

    generator = ReportGenerator(output_dir=args.output_dir)
    out_dir = generator.save_run(
        run_id=run_id,
        status="SUCCESS",
        model_name="qwen2.5:3b",
        findings=metrics["findings"],
        duration=10.0,
        explanation=detailed_explanation
    )
    logging.info(f"Pipeline completed successfully. Reports saved in {out_dir}/")

if __name__ == "__main__":
    try:
        run_pipeline()
    except Exception as e:
        logging.exception(f"Pipeline error: {e}")
        sys.exit(1)
