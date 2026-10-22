# Bioinformatics Copilot

**A local-first prototype for AI-assisted bioinformatics workflow auditing.**

Bioinformatics Copilot combines Python-based file inspection and quality checks with a locally running large language model (LLM). It helps inspect bioinformatics inputs and pipeline outputs, flag potential inconsistencies, and generate structured reports.

The project also includes an automated genomic resource workflow that uses an LLM to help choose a data source, retrieves genomic files, and compares protein queries with genome annotations and assemblies.

## Features

- **Pipeline log inspection:** identify potential errors and warnings.
- **Sequence-file inspection:** inspect DNA and protein FASTA files.
- **BLAST output inspection:** review tabular BLAST results.
- **Alignment inspection:** inspect multiple sequence alignments.
- **Annotation inspection:** compare target gene lists with GFF3 annotations.
- **Assembly inspection:** compare protein queries with annotations and, when available, search genome assemblies with `tblastn`.
- **Reports and audit history:** generate Markdown and JSON reports and maintain local audit history.
- **Local LLM integration:** use Ollama with Qwen2.5:3b to assist with source selection and interpretation.

## Architecture

| Component | Responsibility |
| --- | --- |
| `analyzer/` | File inspectors, log parsing, LLM integration, audit history, and report generation |
| `scripts/run_pipeline.py` | Automated genomic resource retrieval and assembly/annotation inspection |
| `scripts/project_copilot.py` | Project-level copilot functionality |
| `scripts/project_index.py` | Project indexing functionality |
| `config/` | Copilot evaluation rubric |
| `examples/` | Example input files |
| `tests/` | Automated tests |

The design separates deterministic parsing and checks from LLM-generated explanations. LLM outputs are suggestions for interpretation, not independent biological validation.

## Requirements

- Python 3.10 or later
- [Ollama](https://ollama.com/) and the `qwen2.5:3b` model for LLM features
- BLAST+ with `tblastn` available on `PATH` for assembly searches
- NCBI Datasets CLI if the workflow uses NCBI resources
- Network access for remote genomic resource retrieval

The automated pipeline may download large files and consume substantial disk space and bandwidth.

## Installation

Clone the repository and install its Python dependencies:

```bash
git clone https://github.com/JuliP33/bioinformatics-copilot.git
cd bioinformatics-copilot
micromamba create -f environment.yml
micromamba activate bioinfo_copilot
python -m pip install -r analyzer/requirements.txt
ollama pull qwen2.5:3b
```

If Ollama is not already running as a service, start it in a separate terminal:
ollama serve
```

## Usage

Display the local auditor's help:

```bash
PYTHONPATH=. python analyzer/run_audit.py --help
```

Example commands:

```bash
# Inspect a pipeline log
PYTHONPATH=. python analyzer/run_audit.py -i examples/sample.log

# Inspect protein sequences
PYTHONPATH=. python analyzer/run_audit.py -i examples/sample_proteins.fasta

# Inspect tabular BLAST output
PYTHONPATH=. python analyzer/run_audit.py -i examples/sample_blast.tsv

```

## Automated genomic workflow

Run the automated genomic workflow:

```bash
PYTHONPATH=. python scripts/run_pipeline.py --species "Arabidopsis thaliana"
```

Available resources depend on the target species and source databases. Check the command's --help output for supported options.

## Tests

Run the test suite from the repository root:

```bash
PYTHONPATH=. pytest -q
```

Passing tests in the development environment does not guarantee that every remote download, species, annotation format, or biological interpretation will work correctly.

## Limitations
- This is a prototype, not a production-ready or independently validated bioinformatics platform.
- LLM-generated explanations may be incomplete or incorrect and should be reviewed.
- Choosing a data source does not guarantee that the assembly, annotation, and protein sequences are version-matched.
- Annotation-to-sequence matching depends on the identifiers and formats in the input files.
- `tblastn` results provide evidence of sequence similarity, not proof of gene identity or biological function.
- Results depend on input quality, external resource availability, and local hardware.

## Future Work

Potential improvements include stronger assembly and annotation provenance tracking, more robust identifier normalization, expanded tests using known biological cases, and clearer reporting of data-source versions and validation status.
## License

No license has been specified yet. All rights and reuse permissions remain with the respective copyright holders until a license is added.
