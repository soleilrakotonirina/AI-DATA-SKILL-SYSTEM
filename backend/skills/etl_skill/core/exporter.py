"""
backend/skills/etl_skill/core/exporter.py
Sauvegarde du dataset propre, rapport Markdown et script ETL reproductible.

Fonctions principales :
    save_dataset              : Sauvegarde en CSV, Parquet ou Excel
    generate_markdown_report  : Rapport comparatif avant/apres (retourne str + path)
    generate_etl_script       : Script Python autonome reproduisant le pipeline
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def save_dataset(
    df: pd.DataFrame,
    output_dir: str | Path,
    filename: str,
    format: str = "csv",
) -> Path:
    """
    Sauvegarde un DataFrame en CSV, Parquet ou Excel.

    Args:
        df        : DataFrame a sauvegarder.
        output_dir: Dossier de destination (cree s'il n'existe pas).
        filename  : Nom du fichier de sortie.
        format    : 'csv', 'parquet', ou 'excel'.

    Returns:
        Path vers le fichier sauvegarde.

    Raises:
        ValueError: Si format invalide.
    """
    valid_formats = {"csv", "parquet", "excel"}
    if format not in valid_formats:
        raise ValueError(
            f"Format invalide '{format}'. Choisir parmi : {valid_formats}"
        )

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = Path(filename).stem
    ext_map = {"csv": ".csv", "parquet": ".parquet", "excel": ".xlsx"}
    output_path = out_dir / (stem + ext_map[format])

    if format == "csv":
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
    elif format == "parquet":
        df.to_parquet(output_path, index=False)
    elif format == "excel":
        df.to_excel(output_path, index=False, engine="openpyxl")

    logger.info(
        "Dataset sauvegarde : %s (%d lignes × %d colonnes)",
        output_path,
        *df.shape,
    )
    return output_path


def generate_markdown_report(
    quality_before: dict[str, Any],
    quality_after: dict[str, Any],
    transformation_log: list[dict[str, Any]],
    output_path: str | Path,
) -> tuple[str, Path]:
    """
    Genere un rapport Markdown comparatif avant/apres nettoyage.

    Contient :
    - Tableau comparatif : lignes, colonnes, nullite, doublons
    - Liste des transformations appliquees
    - Statistiques apres nettoyage

    Args:
        quality_before    : Rapport qualite initial (de validator.py).
        quality_after     : Rapport qualite final (de validator.py).
        transformation_log: Journal des transformations effectuees.
        output_path       : Chemin du fichier Markdown de sortie.

    Returns:
        Tuple (content_mdx, path) ou content_mdx est le contenu Markdown
        complet en tant que string (pour push Directus) et path le chemin.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    rows_b = quality_before.get("n_rows", 0)
    rows_a = quality_after.get("n_rows", 0)
    cols_b = quality_before.get("n_cols", 0)
    cols_a = quality_after.get("n_cols", 0)
    null_b = quality_before.get("global_null_rate_pct", 0)
    null_a = quality_after.get("global_null_rate_pct", 0)
    dup_b = quality_before.get("n_duplicates", 0)
    dup_a = quality_after.get("n_duplicates", 0)

    lines = [
        "# Rapport ETL — Nettoyage et Transformation",
        "",
        f"**Genere le** : {now}",
        "",
        "---",
        "",
        "## Comparaison Avant / Apres",
        "",
        "| Indicateur | Avant | Apres | Variation |",
        "|------------|-------|-------|-----------|",
        f"| Lignes           | {rows_b:,} | {rows_a:,} | {rows_a-rows_b:+,} |",
        f"| Colonnes         | {cols_b}   | {cols_a}   | {cols_a-cols_b:+} |",
        f"| Taux nullite (%) | {null_b}   | {null_a}   | {null_a-null_b:+.2f} |",
        f"| Doublons         | {dup_b}    | {dup_a}    | {dup_a-dup_b:+} |",
        "",
        "---",
        "",
        "## Transformations Appliquees",
        "",
    ]

    for i, entry in enumerate(transformation_log, 1):
        step = entry.get("etape", entry.get("step", f"step_{i}"))
        feuille = entry.get("feuille", "")
        label = f"{step}" + (f" [{feuille}]" if feuille else "")
        params = entry.get("params", {})

        # Section speciale pour le Star Schema
        if "decomposer_table_plate" in step and params.get("dimensions"):
            lines.append(f"### {i}. {label}")
            lines.append("")
            lines.append("#### Dimensions detectees")
            lines.append("")
            lines.append("| Dimension | Colonne principale | Colonnes | Nb valeurs |")
            lines.append("|-----------|-------------------|----------|------------|")
            for dim_name, dim_info in params["dimensions"].items():
                col_princ = dim_info.get("col_principale", "")
                colonnes = dim_info.get("colonnes", [])
                n_vals = dim_info.get("n_valeurs", "")
                lines.append(
                    f"| `{dim_name}` | `{col_princ}` | {colonnes} | {n_vals} |"
                )
            lines.append("")
            lines.append("#### Mesures (table de faits)")
            lines.append("")
            mesures = params.get("mesures", [])
            lines.append(f"`{'`, `'.join(mesures)}`" if mesures else "_aucune_")
            lines.append("")
            fact_cols = params.get("fact_columns", [])
            if fact_cols:
                lines.append("#### Colonnes de la table de faits")
                lines.append("")
                lines.append(", ".join(f"`{c}`" for c in fact_cols))
                lines.append("")
            fichiers = params.get("fichiers", [])
            if fichiers:
                lines.append("#### Fichiers generés dans `mapping_tables/`")
                lines.append("")
                for f in fichiers:
                    lines.append(f"- `{f}`")
                lines.append("")
            continue

        # Etapes standard
        detail = {
            k: v for k, v in entry.items()
            if k not in ("etape", "step", "feuille", "params")
        }
        lines.append(f"### {i}. {label}")
        lines.append("")
        for k, v in list(detail.items())[:8]:
            if isinstance(v, list) and len(v) > 10:
                v = v[:10] + ["..."]
            lines.append(f"- **{k}** : `{v}`")
        lines.append("")

    # Statistiques finales
    numeric_stats = quality_after.get("numeric_stats", {})
    if numeric_stats:
        lines += [
            "---",
            "",
            "## Statistiques Apres Nettoyage",
            "",
            "| Colonne | Mean | Std | Min | Mediane | Max |",
            "|---------|------|-----|-----|---------|-----|",
        ]
        for col, s in numeric_stats.items():
            lines.append(
                f"| {col} | {s.get('mean','N/A')} | {s.get('std','N/A')} | "
                f"{s.get('min','N/A')} | {s.get('50%','N/A')} | {s.get('max','N/A')} |"
            )

    content = "\n".join(lines)
    path.write_text(content, encoding="utf-8")
    logger.info("Rapport Markdown genere : %s", path)

    return content, path


def generate_etl_script(
    transformation_log: list[dict[str, Any]],
    dataset_info: dict[str, Any],
    output_path: str | Path,
) -> Path:
    """
    Genere un script Python autonome reproduisant le pipeline ETL.

    Le script inclut tous les imports, les constantes et les transformations
    dans l'ordre exact. Il est executable directement sur un nouveau dataset
    du meme format.

    Args:
        transformation_log: Journal des transformations effectuees.
        dataset_info      : Meta du dataset original
                            {input_path, shape_before}.
        output_path       : Chemin du script Python de sortie.

    Returns:
        Path vers le script genere.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    original_file = dataset_info.get("input_path", "dataset.xlsx")
    shape_before = dataset_info.get("shape_before", "N/A")

    # Construire les lignes de transformation dynamiquement
    transform_lines: list[str] = []
    for entry in transformation_log:
        step = entry.get("etape", entry.get("step", ""))

        if step == "handle_missing_values" or entry.get("step") == "imputation":
            strategy = entry.get("strategy", "auto")
            fill_mode = entry.get("fill_mode", "smart")
            transform_lines += [
                "    # Valeurs manquantes",
                f"    df, _ = handle_missing_values(df, strategy='{strategy}', fill_mode='{fill_mode}')",
            ]
        elif step == "remove_duplicates":
            transform_lines += [
                "    # Suppression des doublons",
                "    df, _ = remove_duplicates(df)",
            ]
        elif step == "fix_data_types":
            transform_lines += [
                "    # Correction des types",
                "    df, _ = fix_data_types(df)",
            ]
        elif step == "detect_and_treat_outliers":
            method = entry.get("method", "iqr")
            action = entry.get("action", "cap")
            columns = entry.get("columns", [])
            transform_lines += [
                "    # Outliers",
                f"    df, _ = detect_and_treat_outliers(df, columns={columns!r}, "
                f"method='{method}', action='{action}')",
            ]
        elif step == "encode_categorical":
            columns = entry.get("columns", [])
            method = entry.get("method", "auto")
            transform_lines += [
                "    # Encodage categorial",
                f"    df, _ = encode_categorical(df, columns={columns!r}, method='{method}')",
            ]
        elif step == "scale_features":
            columns = entry.get("columns", [])
            method = entry.get("method", "standard")
            transform_lines += [
                "    # Scaling",
                f"    df, _ = scale_features(df, columns={columns!r}, method='{method}')",
            ]
        elif step == "drop_high_nullity_columns":
            dropped = entry.get("columns_dropped", [])
            transform_lines += [
                "    # Suppression colonnes trop lacunaires",
                f"    df = df.drop(columns={dropped!r}, errors='ignore')",
            ]

        if transform_lines and not transform_lines[-1].startswith("    #"):
            transform_lines.append("")

    transforms_block = (
        "\n".join(transform_lines)
        if transform_lines
        else "    # Aucune transformation enregistree\n"
    )

    script_lines = [
        "#!/usr/bin/env python3",
        '"""',
        "Script ETL Reproductible — Genere par AI DATA SKILL SYSTEM",
        "=" * 65,
        f"Dataset original : {original_file}",
        f"Shape originale  : {shape_before}",
        f"Genere le        : {now}",
        "",
        "Execution :",
        f"    python {path.name} --input data/raw/{Path(original_file).name} --output data/processed/clean.csv",
        "",
        "Dependances :",
        "    pip install pandas numpy scikit-learn openpyxl",
        '"""',
        "",
        "import argparse, logging, sys",
        "from pathlib import Path",
        "import pandas as pd",
        "sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))",
        "",
        "from skills.etl_skill.core.cleaner import (",
        "    load_dataset, handle_missing_values, remove_duplicates,",
        "    fix_data_types, sanitize_column_names,",
        ")",
        "from skills.etl_skill.core.transformer import (",
        "    detect_and_treat_outliers, encode_categorical, scale_features,",
        ")",
        "from skills.etl_skill.core.exporter import save_dataset",
        "",
        "logging.basicConfig(level=logging.INFO,",
        '    format="%(asctime)s [%(levelname)s] %(name)s : %(message)s")',
        'logger = logging.getLogger("etl_script")',
        "",
        "",
        "def run_etl(input_path: str, output_path: str) -> pd.DataFrame:",
        '    """Execute le pipeline ETL complet."""',
        '    logger.info("=== DEMARRAGE DU PIPELINE ETL ===")',
        "    df, _ = load_dataset(input_path)",
        "    if isinstance(df, dict):",
        "        df = next(iter(df.values()))",
        "    df = sanitize_column_names(df)",
        '    logger.info("Dataset charge : %d lignes x %d colonnes", *df.shape)',
        "",
        transforms_block,
        "    out = Path(output_path)",
        "    save_dataset(df, out.parent, out.name, format='csv')",
        '    logger.info("=== PIPELINE TERMINE : %d lignes x %d colonnes ===", *df.shape)',
        "    return df",
        "",
        "",
        'if __name__ == "__main__":',
        '    parser = argparse.ArgumentParser(description="Pipeline ETL reproductible")',
        '    parser.add_argument("--input",  "-i", required=True)',
        '    parser.add_argument("--output", "-o", required=True)',
        "    args = parser.parse_args()",
        "    result = run_etl(args.input, args.output)",
        '    print(f"\\nTermine : {result.shape[0]:,} lignes x {result.shape[1]} colonnes")',
    ]

    path.write_text("\n".join(script_lines) + "\n", encoding="utf-8")
    logger.info("Script ETL reproductible genere : %s", path)
    return path