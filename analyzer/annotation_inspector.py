import os
from typing import Dict, Any, List
from analyzer.schemas import LogFinding

class AnnotationInspector:
    def check_missing_annotations(self, target_list_file: str, annotation_db_file: str) -> Dict[str, Any]:
        """
        Compara una lista de genes/targets de interés contra un archivo de anotación genómica local (GFF3 o TSV).
        """
        if not os.path.exists(target_list_file) or not os.path.exists(annotation_db_file):
            raise FileNotFoundError("Target list file or annotation database file not found.")

        # 1. Leer los targets que buscamos (ej: los genes de interés)
        target_genes = set()
        with open(target_list_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    target_genes.add(line.split()[0]) # Tomar el primer token como ID del gen

        # 2. Leer las anotaciones presentes en el archivo local del genoma
        annotated_genes = set()
        with open(annotation_db_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith("#"):
                    continue
                # Soporte básico para GFF3 / GTF o tablas TSV
                parts = line.split("\t")
                if len(parts) >= 3:
                    # Guardar texto relevante de la línea para buscar coincidencias
                    annotated_genes.add(line)

        # 3. Cruzar datos: Detectar cuáles targets brillan por su ausencia
        findings: List[LogFinding] = []
        missing_targets = []

        for gene in target_genes:
            # Buscar si el ID del gen aparece en alguna línea del archivo de anotación
            found = any(gene in ann_line for ann_line in annotated_genes)
            if not found:
                missing_targets.append(gene)
                findings.append(
                    LogFinding(
                        severity="WARNING",
                        line_number=0,
                        message=f"Target gene/feature '{gene}' is completely ABSENT from the local genome annotation file ({annotation_db_file}).",
                        source_evidence=target_list_file
                    )
                )

        return {
            "target_list_file": target_list_file,
            "annotation_db_file": annotation_db_file,
            "total_targets_checked": len(target_genes),
            "missing_count": len(missing_targets),
            "missing_targets": missing_targets,
            "findings": findings
        }
