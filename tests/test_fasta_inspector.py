from analyzer.fasta_inspector import FastaInspector

def test_fasta_inspector_dna():
    inspector = FastaInspector()
    metrics = inspector.inspect("examples/sample_genes.fasta")

    assert metrics["molecule_type"] == "DNA"
    assert metrics["unit_label"] == "bp"
    assert metrics["total_sequences"] == 3
    assert "gc_content_pct" in metrics

def test_fasta_inspector_protein():
    inspector = FastaInspector()
    metrics = inspector.inspect("examples/sample_proteins.fasta")

    assert metrics["molecule_type"] == "PROTEIN"
    assert metrics["unit_label"] == "aa"
    assert metrics["total_sequences"] == 3
    assert metrics["min_length"] == 13
    assert len(metrics["findings"]) == 1  # Detecta la 'X' en la 3er proteína
    assert "gc_content_pct" not in metrics  # No aplica %GC para proteínas
