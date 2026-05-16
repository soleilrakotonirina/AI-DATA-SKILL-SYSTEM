"""
backend/skills/etl_skill/scripts/logic.py
Orchestration du pipeline ETL complet (v1.1 avec Star Schema automatique).

Pont entre l'orchestrateur Gemini (executor.py) et les modules core/.
Recoit un ETLRequest Pydantic, execute le pipeline, publie le rapport MDX
dans Directus, et retourne un ETLResponse.

Workflow execute :
    A.  Detection mono-feuille vs multi-feuilles
    B.  Nettoyage de chaque feuille (sans encodage ni scaling)
    C.  Sauvegarde des donnees LISIBLES dans data/processed/{stem}/core_data/
    D.  Construction du Star Schema (mono) ou de la TABLE JOINTE (multi)
        → data/processed/{stem}/mapping_tables/
    E.  Encodage et scaling sur le DataFrame principal (pour ETLResponse)
    F.  Generation du rapport Markdown comparatif
    G.  Push du rapport MDX vers Directus
    H.  Retour ETLResponse Pydantic

Structure de sortie :
    data/processed/{stem}/
        core_data/                 ← donnees PROPRES et LISIBLES (par feuille)
            {feuille}.csv
        mapping_tables/            ← Star Schema OU Table Jointe
            {stem}_dim_*.csv       (mono-feuille decomposee)
            {stem}_fact_*.csv      (mono-feuille decomposee)
            {stem}_JOINTE.csv      (multi-feuilles avec FK→PK)
    outputs/rapport_etl/{stem}/
        etl_quality_report_before.md
        etl_quality_report_after.md
        etl_report_{stem}.md       (rapport MDX comparatif)
        etl_script_{stem}.py       (script Python reproductible)
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from schemas.etl import ETLRequest, ETLResponse
from skills.etl_skill.core.cleaner import (
    fix_data_types,
    format_date_columns,
    handle_missing_values,
    is_protected_column,
    load_dataset,
    remove_duplicates,
    sanitize_column_names,
)
from skills.etl_skill.core.exporter import (
    generate_etl_script,
    generate_markdown_report,
    save_dataset,
)
from skills.etl_skill.core.normalizer import consolidate_categorical_values
from skills.etl_skill.core.star_schema import (
    creer_table_jointe,
    decomposer_table_plate,
    detecter_schema_relationnel,
    sauvegarder_star_schema,
)
from skills.etl_skill.core.transformer import (
    detect_and_treat_outliers,
    encode_categorical,
    scale_features,
)
from skills.etl_skill.core.validator import generate_quality_report
from skills.etl_skill.scripts.helpers import format_duration
from src.utils.directus_client import (
    append_pipeline_log,
    push_report_mdx,
)

logger = logging.getLogger(__name__)


def _log_step(
    log: list[dict[str, Any]],
    etape: str,
    fonction: str,
    params: dict[str, Any],
    rows_before: int,
    rows_after: int | None,
    duration_ms: float,
) -> None:
    """Ajoute une entree au journal de transformations."""
    log.append({
        "etape": etape,
        "fonction": fonction,
        "params": params,
        "rows_before": rows_before,
        "rows_after": rows_after if rows_after is not None else rows_before,
        "duration_ms": round(duration_ms, 1),
    })


def _detect_numeric_columns_to_scale(
    df: pd.DataFrame,
    target_column: str | None,
    columns_to_exclude: list[str],
) -> list[str]:
    """Detecte les colonnes numeriques mesures eligibles au scaling."""
    excluded = set(columns_to_exclude or [])
    if target_column:
        excluded.add(target_column)

    candidates: list[str] = []
    for col in df.select_dtypes(include=[np.number]).columns:
        if col in excluded:
            continue
        if is_protected_column(col, df[col]):
            continue
        if df[col].std() == 0 or df[col].nunique() <= 1:
            continue
        candidates.append(col)
    return candidates


def _detect_categorical_columns_to_encode(
    df: pd.DataFrame,
    target_column: str | None,
    columns_to_exclude: list[str],
) -> list[str]:
    """Detecte les colonnes categorielles eligibles a l'encodage."""
    excluded = set(columns_to_exclude or [])
    if target_column:
        excluded.add(target_column)

    candidates: list[str] = []
    for col in df.columns:
        if col in excluded:
            continue
        if df[col].dtype != object and not pd.api.types.is_string_dtype(df[col]):
            continue
        if is_protected_column(col, df[col]):
            continue
        # Eviter les colonnes constantes (cardinalite 1)
        if df[col].nunique() <= 1:
            continue
        candidates.append(col)
    return candidates


def _error_response(
    session_id: str,
    message: str,
    errors: list[str] | None = None,
) -> ETLResponse:
    """Construit une ETLResponse de type 'error'."""
    logger.error("[ETL] Erreur critique : %s", message)
    return ETLResponse(
        skill="ETL",
        session_id=session_id,
        status="error",
        rows_before=0,
        rows_after=0,
        cols_before=0,
        cols_after=0,
        nulls_removed=0,
        duplicates_removed=0,
        script_path=None,
        report_md_path=None,
        report_mdx_id=None,
        transformation_log=[],
        errors=errors or [message],
        error_message=message,
    )


def _nettoyer_feuille(
    df_brut: pd.DataFrame,
    nom_feuille: str,
    request: ETLRequest,
    outputs_dir: Path,
    transformation_log: list[dict[str, Any]],
    errors: list[str],
) -> tuple[pd.DataFrame, dict, dict, dict]:
    """
    Nettoie UNE feuille : normalisation, valeurs manquantes, doublons,
    correction des types, format dates, outliers.

    PAS d'encodage ni de scaling a cette etape (donnees lisibles).

    Returns:
        (df_propre, quality_before, quality_after, dup_report)
    """
    df = df_brut.copy()
    rows_init = len(df)

    # A. Normalisation des noms de colonnes
    t0 = time.monotonic()
    df = sanitize_column_names(df)
    _log_step(transformation_log, f"sanitize_column_names[{nom_feuille}]",
              "sanitize_column_names", {}, rows_init, len(df),
              (time.monotonic() - t0) * 1000)

    # B. Rapport qualite initial
    t0 = time.monotonic()
    try:
        q_before, _ = generate_quality_report(
            df, label=f"before_{nom_feuille}", output_dir=outputs_dir,
        )
    except Exception as exc:
        errors.append(f"Rapport initial '{nom_feuille}' : {exc}")
        q_before = {"n_rows": len(df), "n_cols": df.shape[1],
                    "global_null_rate_pct": 0.0, "n_duplicates": 0,
                    "total_nulls": 0, "numeric_stats": {}}

    # C. Valeurs manquantes
    t0 = time.monotonic()
    try:
        df, _ = handle_missing_values(
            df,
            strategy=request.missing_strategy,
            fill_mode=request.fill_mode,
        )
    except Exception as exc:
        errors.append(f"Valeurs manquantes '{nom_feuille}' : {exc}")

    # D. Suppression doublons
    t0 = time.monotonic()
    dup_report = {"rows_removed": 0}
    try:
        rows_before_dedup = len(df)
        df, dup_report = remove_duplicates(df)
        _log_step(transformation_log, f"remove_duplicates[{nom_feuille}]",
                  "remove_duplicates", {}, rows_before_dedup, len(df),
                  (time.monotonic() - t0) * 1000)
    except Exception as exc:
        errors.append(f"Doublons '{nom_feuille}' : {exc}")

    # D'. Consolidation des valeurs categorielles (casse + fautes de frappe)
    t0 = time.monotonic()
    try:
        df, consolidation_rep = consolidate_categorical_values(df)
        if consolidation_rep:
            total_repl = sum(
                r["n_replacements"] for r in consolidation_rep.values()
            )
            _log_step(
                transformation_log,
                f"consolidate_values[{nom_feuille}]",
                "consolidate_categorical_values",
                {
                    "n_columns_consolidated": len(consolidation_rep),
                    "total_replacements": total_repl,
                    "columns": list(consolidation_rep.keys()),
                },
                len(df), len(df),
                (time.monotonic() - t0) * 1000,
            )
    except Exception as exc:
        errors.append(f"Consolidation valeurs '{nom_feuille}' : {exc}")

    # E. Correction des types
    t0 = time.monotonic()
    try:
        df, _ = fix_data_types(df)
    except Exception as exc:
        errors.append(f"Types '{nom_feuille}' : {exc}")

    # F. Format dates lisibles (YYYY-MM-DD sans 00:00:00)
    try:
        df = format_date_columns(df)
    except Exception as exc:
        errors.append(f"Format dates '{nom_feuille}' : {exc}")

    # G. Outliers (sur colonnes numeriques non protegees)
    numeric_cols = _detect_numeric_columns_to_scale(
        df, request.target_column, request.columns_to_exclude,
    )
    if numeric_cols:
        t0 = time.monotonic()
        try:
            df, _ = detect_and_treat_outliers(
                df,
                columns=numeric_cols,
                method=request.outlier_method,
                action=request.outlier_action,
            )
        except Exception as exc:
            errors.append(f"Outliers '{nom_feuille}' : {exc}")

    # H. Rapport qualite final
    try:
        q_after, _ = generate_quality_report(
            df, label=f"after_{nom_feuille}", output_dir=outputs_dir,
        )
    except Exception as exc:
        errors.append(f"Rapport final '{nom_feuille}' : {exc}")
        q_after = {"n_rows": len(df), "n_cols": df.shape[1],
                   "global_null_rate_pct": 0.0, "n_duplicates": 0,
                   "total_nulls": 0, "numeric_stats": {}}

    return df, q_before, q_after, dup_report


async def run_etl_pipeline(request: ETLRequest) -> ETLResponse:
    """
    Execute le pipeline ETL complet de bout en bout.

    Args:
        request: ETLRequest Pydantic valide.

    Returns:
        ETLResponse Pydantic avec metriques, chemins et report_mdx_id.
    """
    session_id = request.session_id
    transformation_log: list[dict[str, Any]] = []
    errors: list[str] = []
    pipeline_start = time.monotonic()

    logger.info(
        "[ETL] Demarrage pipeline — session=%s, input=%s",
        session_id, request.input_path,
    )
    await append_pipeline_log(
        session_id, "ETL", "pipeline_start", "running",
        f"Pipeline ETL demarre sur {request.input_path}",
    )

    # ── Preparation des chemins de sortie ────────────────────────────────────
    source_path = Path(request.input_path)
    if not source_path.exists():
        return _error_response(
            session_id, f"Fichier introuvable : {request.input_path}",
        )

    stem = source_path.stem
    base_dir = Path("data/processed") / stem
    core_dir = base_dir / "core_data"
    mapping_dir = base_dir / "mapping_tables"
    outputs_dir = Path("outputs") / "rapport_etl" / stem

    base_dir.mkdir(parents=True, exist_ok=True)
    core_dir.mkdir(parents=True, exist_ok=True)
    mapping_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)

    # ── Etape 1 : Chargement (mono ou multi-feuilles) ────────────────────────
    t0 = time.monotonic()
    try:
        raw_data, metadata = load_dataset(
            request.input_path,
            sheet_name=None if source_path.suffix.lower() in {".xlsx", ".xlsm", ".xls"} else 0,
        )
    except (FileNotFoundError, ValueError) as exc:
        return _error_response(session_id, str(exc))

    is_multi = isinstance(raw_data, dict)
    if is_multi:
        feuilles_brutes = raw_data
        logger.info(
            "[ETL] Multi-feuilles detecte : %d feuilles (%s)",
            len(feuilles_brutes), list(feuilles_brutes.keys()),
        )
    else:
        # Fallback mono-feuille : utiliser le stem comme nom
        feuilles_brutes = {stem: raw_data}
        logger.info("[ETL] Mono-feuille detecte : '%s'", stem)

    # Comptage initial total
    rows_init_total = sum(len(df) for df in feuilles_brutes.values())
    cols_init_total = max(df.shape[1] for df in feuilles_brutes.values())

    _log_step(transformation_log, "load_dataset", "load_dataset",
              {"input_path": request.input_path, "n_sheets": len(feuilles_brutes)},
              rows_init_total, rows_init_total,
              (time.monotonic() - t0) * 1000)

    # ── Etape 2 : Nettoyage de chaque feuille (donnees LISIBLES) ─────────────
    feuilles_propres: dict[str, pd.DataFrame] = {}
    qualites_before: dict[str, dict] = {}
    qualites_after: dict[str, dict] = {}
    total_duplicates = 0
    total_nulls_before = 0

    for nom_feuille, df_brut in feuilles_brutes.items():
        logger.info("[ETL] Nettoyage feuille '%s'...", nom_feuille)
        df_propre, q_before, q_after, dup_rep = _nettoyer_feuille(
            df_brut, nom_feuille, request, outputs_dir,
            transformation_log, errors,
        )
        feuilles_propres[nom_feuille] = df_propre
        qualites_before[nom_feuille] = q_before
        qualites_after[nom_feuille] = q_after
        total_duplicates += dup_rep.get("rows_removed", 0)
        total_nulls_before += q_before.get("total_nulls", 0)

    # ── Etape 3 : Sauvegarde core_data/ (valeurs LISIBLES) ───────────────────
    for nom_feuille, df_propre in feuilles_propres.items():
        try:
            save_dataset(df_propre, core_dir, f"{nom_feuille}.csv", format="csv")
        except Exception as exc:
            errors.append(f"Sauvegarde core_data '{nom_feuille}' : {exc}")

    logger.info("[ETL] core_data/ : %d feuille(s) sauvegardee(s)", len(feuilles_propres))

    # Push des rapports qualite before/after vers Directus
    for nom_feuille in feuilles_propres.keys():
        for label in [f"before_{nom_feuille}", f"after_{nom_feuille}"]:
            rp = outputs_dir / f"etl_quality_report_{label}.md"
            if not rp.exists():
                continue
            try:
                mdx_content = rp.read_text(encoding="utf-8")
                phase = "avant" if label.startswith("before") else "apres"
                await push_report_mdx(
                    session_id=session_id,
                    report_type="etl",
                    title=f"Qualite {phase} — {nom_feuille}",
                    content_mdx=mdx_content,
                )
            except Exception as exc:
                errors.append(f"Push rapport qualite '{label}' : {exc}")

    # ── Etape 4 : Construction Star Schema OU Table Jointe ───────────────────
    # mapping_tables/ est TOUJOURS produit (independamment de dimensional_modeling)
    has_star_or_joined = False

    if is_multi:
        # Multi-feuilles : detecter relations FK→PK et faire la jointure
        try:
            schema_rel = detecter_schema_relationnel(feuilles_propres)
            if schema_rel.get("liaisons"):
                chemin_jointe = creer_table_jointe(
                    feuilles_propres, schema_rel, stem, mapping_dir,
                )
                if chemin_jointe:
                    has_star_or_joined = True
                    _log_step(transformation_log, "creer_table_jointe",
                              "creer_table_jointe",
                              {"liaisons": len(schema_rel["liaisons"])},
                              rows_init_total, rows_init_total, 0)
            else:
                logger.info(
                    "[ETL] Multi-feuilles sans relations FK→PK detectees → "
                    "decomposition de chaque feuille",
                )
        except Exception as exc:
            errors.append(f"Detection relations : {exc}")

    # Mono-feuille OU multi-feuilles sans relations : decomposer chaque feuille
    if not has_star_or_joined:
        for nom_feuille, df_propre in feuilles_propres.items():
            try:
                star_result = decomposer_table_plate(df_propre, nom_feuille)
                if star_result.get("has_star_schema"):
                    sauvegarder_star_schema(
                        star_result, stem, nom_feuille, mapping_dir,
                    )
                    has_star_or_joined = True
                    _log_step(transformation_log,
                              f"decomposer_table_plate[{nom_feuille}]",
                              "decomposer_table_plate",
                              {"n_dimensions": len(star_result.get("rapport", {}).get("dimensions", {}))},
                              len(df_propre), len(df_propre), 0)
            except Exception as exc:
                errors.append(f"Star Schema '{nom_feuille}' : {exc}")

    if not has_star_or_joined:
        logger.info(
            "[ETL] Aucun Star Schema ni TABLE JOINTE construit "
            "(donnees insuffisantes en mesures/dimensions)",
        )

    # ── Etape 5 : DataFrame principal pour la reponse Pydantic ───────────────
    # On utilise la premiere feuille comme reference pour les metriques globales
    nom_principal = list(feuilles_propres.keys())[0]
    df = feuilles_propres[nom_principal].copy()

    # ── Etape 6 : Encodage et scaling (sur df principal uniquement) ──────────
    categorical_cols = _detect_categorical_columns_to_encode(
        df, request.target_column, request.columns_to_exclude,
    )
    if categorical_cols:
        t0 = time.monotonic()
        try:
            df, _ = encode_categorical(
                df, columns=categorical_cols, method=request.encode_method,
            )
            _log_step(transformation_log, "encode_categorical",
                      "encode_categorical",
                      {"method": request.encode_method,
                       "columns": categorical_cols},
                      len(df), len(df), (time.monotonic() - t0) * 1000)
        except Exception as exc:
            errors.append(f"Encodage : {exc}")

    numeric_cols_post = _detect_numeric_columns_to_scale(
        df, request.target_column, request.columns_to_exclude,
    )
    if numeric_cols_post:
        t0 = time.monotonic()
        try:
            df, _ = scale_features(
                df, columns=numeric_cols_post, method=request.scale_method,
            )
            _log_step(transformation_log, "scale_features", "scale_features",
                      {"method": request.scale_method,
                       "columns": numeric_cols_post},
                      len(df), len(df), (time.monotonic() - t0) * 1000)
        except Exception as exc:
            errors.append(f"Scaling : {exc}")

    # ── Etape 7 : Rapports qualite globaux (pour le rapport MDX) ─────────────
    quality_before_global = {
        "n_rows": sum(q.get("n_rows", 0) for q in qualites_before.values()),
        "n_cols": max(q.get("n_cols", 0) for q in qualites_before.values()),
        "global_null_rate_pct": np.mean([
            q.get("global_null_rate_pct", 0) for q in qualites_before.values()
        ]),
        "total_nulls": sum(q.get("total_nulls", 0) for q in qualites_before.values()),
        "n_duplicates": sum(q.get("n_duplicates", 0) for q in qualites_before.values()),
        "numeric_stats": {},
    }
    quality_after_global = {
        "n_rows": sum(len(df_p) for df_p in feuilles_propres.values()),
        "n_cols": max(df_p.shape[1] for df_p in feuilles_propres.values()),
        "global_null_rate_pct": np.mean([
            q.get("global_null_rate_pct", 0) for q in qualites_after.values()
        ]),
        "total_nulls": sum(q.get("total_nulls", 0) for q in qualites_after.values()),
        "n_duplicates": 0,
        "numeric_stats": qualites_after.get(nom_principal, {}).get("numeric_stats", {}),
    }

    # ── Etape 8 : Rapport Markdown comparatif ────────────────────────────────
    report_md_path: str | None = None
    content_mdx: str = ""
    try:
        report_path = outputs_dir / f"etl_report_{stem}.md"
        content_mdx, report_path = generate_markdown_report(
            quality_before_global, quality_after_global,
            transformation_log, report_path,
        )
        report_md_path = str(report_path)
    except Exception as exc:
        errors.append(f"Rapport Markdown : {exc}")

    # ── Etape 9 : Script ETL reproductible ───────────────────────────────────
    script_path: str | None = None
    if request.generate_script:
        try:
            script_file = outputs_dir / f"etl_script_{stem}.py"
            generate_etl_script(
                transformation_log,
                {"input_path": request.input_path,
                 "shape_before": (rows_init_total, cols_init_total)},
                script_file,
            )
            script_path = str(script_file)
        except Exception as exc:
            errors.append(f"Script ETL : {exc}")

    # ── Etape 10 : Push rapport MDX vers Directus ────────────────────────────
    report_mdx_id: str | None = None
    if content_mdx:
        try:
            report_mdx_id = await push_report_mdx(
                session_id=session_id,
                report_type="etl",
                title=f"Rapport ETL — {stem}",
                content_mdx=content_mdx,
            )
            if report_mdx_id:
                logger.info(
                    "[ETL] Rapport MDX publie dans Directus — ID=%s",
                    report_mdx_id,
                )
        except Exception as exc:
            errors.append(f"Push Directus : {exc}")
            logger.warning("Push Directus echoue : %s", exc)

    # ── Calculs finaux ───────────────────────────────────────────────────────
    rows_after_total = sum(len(df_p) for df_p in feuilles_propres.values())
    cols_after_total = df.shape[1]
    nulls_after_total = sum(
        int(df_p.isnull().sum().sum()) for df_p in feuilles_propres.values()
    )
    nulls_removed = max(0, total_nulls_before - nulls_after_total)

    pipeline_duration_ms = (time.monotonic() - pipeline_start) * 1000
    logger.info(
        "[ETL] Pipeline termine en %s — status=%s, errors=%d",
        format_duration(pipeline_duration_ms),
        "success" if not errors else "success_partial",
        len(errors),
    )

    await append_pipeline_log(
        session_id, "ETL", "pipeline_end",
        "success" if not errors else "partial",
        f"Pipeline ETL termine — {rows_after_total} lignes x {cols_after_total} colonnes",
    )

    return ETLResponse(
        skill="ETL",
        session_id=session_id,
        status="success",
        rows_before=rows_init_total,
        rows_after=rows_after_total,
        cols_before=cols_init_total,
        cols_after=cols_after_total,
        nulls_removed=nulls_removed,
        duplicates_removed=total_duplicates,
        script_path=script_path,
        report_md_path=report_md_path,
        report_mdx_id=report_mdx_id,
        transformation_log=transformation_log,
        errors=errors,
        error_message=None,
    )