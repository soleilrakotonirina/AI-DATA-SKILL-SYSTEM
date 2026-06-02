"""
skills/etl_skill/scripts/run.py
Orchestrateur synchrone ETL — appelé par mcp/etl_mcp/server.py.

Identique à logic.py pour le transformation_log :
- Même détail pour decomposer_table_plate (dimensions/mesures/fichiers)
- Même détail pour creer_table_jointe (liaisons FK→PK)
- Même format _log_step (fonction, rows_before, rows_after, duration_ms)
- Pas d'async/await, pas de Pydantic, pas de Directus
"""

from __future__ import annotations

import json
import logging
import time
from argparse import Namespace
from pathlib import Path
from typing import Any

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

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
    create_features,
    detect_and_treat_outliers,
    encode_categorical,
    scale_features,
)
from skills.etl_skill.core.validator import generate_quality_report

logger = logging.getLogger(__name__)


def _log_step(
    log: list[dict],
    etape: str,
    fonction: str,
    params: dict,
    rows_before: int,
    rows_after: int | None,
    duration_ms: float,
) -> None:
    """Ajoute une entrée au journal — format identique à logic.py."""
    log.append({
        "etape":       etape,
        "fonction":    fonction,
        "params":      params,
        "rows_before": rows_before,
        "rows_after":  rows_after if rows_after is not None else rows_before,
        "duration_ms": round(duration_ms, 1),
    })


def run_pipeline(args: Namespace) -> dict[str, Any]:
    """
    Exécute le pipeline ETL complet de façon synchrone.
    Produit le même transformation_log détaillé que logic.py.
    """
    t_start = time.monotonic()

    input_path   = getattr(args, "input_path", "")
    target_col   = getattr(args, "target_column", "") or ""
    miss_strat   = getattr(args, "missing_strategy", "auto") or "auto"
    fill_mode    = getattr(args, "fill_mode", "smart") or "smart"
    out_action   = getattr(args, "outlier_action", "cap") or "cap"
    out_method   = getattr(args, "outlier_method", "iqr") or "iqr"
    enc_method   = getattr(args, "encode_method", "auto") or "auto"
    scl_method   = getattr(args, "scale_method", "standard") or "standard"
    excl_raw     = getattr(args, "columns_to_exclude", "") or ""
    feat_ops_raw = getattr(args, "feature_operations", "") or ""

    exclude_cols = [c.strip() for c in excl_raw.split(",") if c.strip()]
    if target_col and target_col not in exclude_cols:
        exclude_cols.append(target_col)

    feat_ops: list[dict] = []
    if feat_ops_raw:
        try:
            feat_ops = json.loads(feat_ops_raw)
        except json.JSONDecodeError:
            logger.warning("[run.py] feature_operations JSON invalide — ignoré")

    errors: list[str] = []
    transformation_log: list[dict] = []

    # ── Chemins de sortie ──────────────────────────────────────────────────
    stem         = _clean_stem(Path(input_path).stem)
    data_out_dir = _resolve_output_dir(input_path)
    data_out_dir.mkdir(parents=True, exist_ok=True)

    try:
        parts = list(Path(input_path).resolve().parts)
        if "backend" in parts:
            idx = parts.index("backend")
            backend_root = Path(*parts[:idx+1])
            reports_out_dir = backend_root / "outputs" / "rapport_etl" / stem
        else:
            reports_out_dir = Path("outputs") / "rapport_etl" / stem
    except Exception:
        reports_out_dir = Path("outputs") / "rapport_etl" / stem
    reports_out_dir.mkdir(parents=True, exist_ok=True)

    # ── Étape 1 : Chargement ───────────────────────────────────────────────
    t0 = time.monotonic()
    try:
        raw, _meta = load_dataset(input_path)
    except Exception as exc:
        return {"status": "error", "error_message": f"Chargement impossible : {exc}", "input_path": input_path}

    is_multi = isinstance(raw, dict)
    if is_multi:
        feuilles_brutes = raw
        rows_before = sum(len(df) for df in feuilles_brutes.values())
        cols_before = max(df.shape[1] for df in feuilles_brutes.values())
    else:
        feuilles_brutes = {stem: raw}
        rows_before = len(raw)
        cols_before = raw.shape[1]

    _log_step(transformation_log, "load_dataset", "load_dataset",
              {"input_path": input_path, "n_sheets": len(feuilles_brutes)},
              rows_before, rows_before, (time.monotonic() - t0) * 1000)

    # ── Étape 2 : Nettoyage de chaque feuille ─────────────────────────────
    feuilles_propres: dict[str, Any] = {}
    qualites_before: dict[str, dict] = {}
    qualites_after:  dict[str, dict] = {}

    for nom, df_brut in feuilles_brutes.items():
        df_propre, q_bf, q_af = _nettoyer_feuille(
            df_brut, nom, exclude_cols, miss_strat, fill_mode,
            out_action, out_method, reports_out_dir, transformation_log, errors
        )
        feuilles_propres[nom] = df_propre
        qualites_before[nom]  = q_bf
        qualites_after[nom]   = q_af

    # ── Étape 3 : Sauvegarde core_data/ (lisible, avant encodage) ─────────
    core_dir = data_out_dir / "core_data"
    core_dir.mkdir(parents=True, exist_ok=True)
    saved_files = []
    for nom_feuille, df_propre in feuilles_propres.items():
        try:
            save_dataset(df_propre, core_dir, f"{nom_feuille}.csv", format="csv")
            saved_files.append(core_dir / f"{nom_feuille}.csv")
        except Exception as exc:
            errors.append(f"Sauvegarde core_data '{nom_feuille}' : {exc}")

    # ── Étape 4A : Star Schema individuel par feuille ──────────────────────
    star_results: dict[str, Any] = {}
    for nom, df_propre in feuilles_propres.items():
        try:
            t0_star = time.monotonic()
            star_result = decomposer_table_plate(df_propre, nom)
            if star_result.get("has_star_schema"):
                out_star = data_out_dir / "mapping_tables"
                fichiers_crees = sauvegarder_star_schema(star_result, stem, nom, out_star)
                star_results[nom] = star_result.get("tables_generated", [])

                rapport_dim  = star_result.get("rapport", {})
                fichiers_noms = (
                    [f.name for f in fichiers_crees]
                    if isinstance(fichiers_crees, (list, tuple))
                    else []
                )
                _log_step(
                    transformation_log,
                    f"decomposer_table_plate[{nom}]",
                    "decomposer_table_plate",
                    {
                        "n_dimensions": len(rapport_dim.get("dimensions", {})),
                        "dimensions":   rapport_dim.get("dimensions", {}),
                        "mesures":      rapport_dim.get("mesures", []),
                        "fact_columns": rapport_dim.get("fact_columns", []),
                        "fichiers":     fichiers_noms,
                    },
                    len(df_propre), len(df_propre),
                    (time.monotonic() - t0_star) * 1000,
                )
        except Exception as exc:
            errors.append(f"Star schema '{nom}' : {exc}")

    # ── Étape 4B : Table Jointe (multi-feuilles uniquement) ────────────────
    df_joint = None
    if is_multi:
        try:
            schema_rel = detecter_schema_relationnel(feuilles_propres)
            if schema_rel and schema_rel.get("liaisons"):
                out_joined  = data_out_dir / "mapping_tables"
                chemin_jointe = creer_table_jointe(feuilles_propres, schema_rel, stem, out_joined)

                if chemin_jointe:
                    rows_jointe, cols_jointe = 0, 0
                    fact_columns: list[str] = []
                    mesures_jointe: list[str] = []
                    try:
                        import pandas as pd
                        df_joint      = pd.read_csv(chemin_jointe)
                        rows_jointe   = len(df_joint)
                        cols_jointe   = df_joint.shape[1]
                        fact_columns  = list(df_joint.columns)
                        for c in df_joint.columns:
                            cl = c.lower()
                            if cl.startswith("id_") or cl.endswith("_id") or cl == "id":
                                continue
                            if not pd.api.types.is_numeric_dtype(df_joint[c]):
                                continue
                            if is_protected_column(c, df_joint[c]):
                                continue
                            if df_joint[c].nunique() <= 1 or df_joint[c].std() == 0:
                                continue
                            mesures_jointe.append(c)
                    except Exception as exc:
                        errors.append(f"Analyse table jointe : {exc}")

                    dimensions_list = sorted({l["cible_table"] for l in schema_rel["liaisons"]})
                    nom_fichier = (
                        chemin_jointe.name
                        if hasattr(chemin_jointe, "name")
                        else str(chemin_jointe).split("/")[-1]
                    )
                    _log_step(
                        transformation_log,
                        "creer_table_jointe",
                        "creer_table_jointe",
                        {
                            "n_liaisons":        len(schema_rel["liaisons"]),
                            "table_fait":        schema_rel.get("table_fait", ""),
                            "liaisons":          schema_rel["liaisons"],
                            "fichiers":          [nom_fichier],
                            "feuilles_sources":  list(feuilles_propres.keys()),
                            "rows_jointe":       rows_jointe,
                            "cols_jointe":       cols_jointe,
                            "dimensions_tables": dimensions_list,
                            "mesures":           mesures_jointe,
                            "fact_columns":      fact_columns,
                        },
                        rows_before, rows_before, 0,
                    )
        except Exception as exc:
            errors.append(f"Table jointe : {exc}")

    # ── Étape 5 : DataFrame principal (première feuille) ──────────────────
    nom_principal = list(feuilles_propres.keys())[0]
    df = feuilles_propres[nom_principal].copy()

    # ── Étape 6 : Encodage ────────────────────────────────────────────────
    cat_cols = [
        c for c in df.select_dtypes(exclude="number").columns
        if c not in exclude_cols
        and not is_protected_column(c, df[c])
        and df[c].nunique() > 1
    ]
    if cat_cols and enc_method != "none":
        t0 = time.monotonic()
        try:
            df, _ = encode_categorical(df, columns=cat_cols, method=enc_method)
            _log_step(transformation_log, "encode_categorical", "encode_categorical",
                      {"method": enc_method, "columns": cat_cols},
                      len(df), len(df), (time.monotonic() - t0) * 1000)
        except Exception as exc:
            errors.append(f"Encodage : {exc}")

    # ── Étape 7 : Scaling ─────────────────────────────────────────────────
    num_cols = [
        c for c in df.select_dtypes(include="number").columns
        if c not in exclude_cols
        and not is_protected_column(c, df[c])
        and df[c].std() != 0
        and df[c].nunique() > 1
    ]
    if num_cols and scl_method != "none":
        t0 = time.monotonic()
        try:
            df, _ = scale_features(df, columns=num_cols, method=scl_method)
            _log_step(transformation_log, "scale_features", "scale_features",
                      {"method": scl_method, "columns": num_cols},
                      len(df), len(df), (time.monotonic() - t0) * 1000)
        except Exception as exc:
            errors.append(f"Scaling : {exc}")

    # ── Étape 8 : Feature engineering ─────────────────────────────────────
    if feat_ops:
        t0 = time.monotonic()
        try:
            df, feat_log = create_features(df, operations=feat_ops)
            _log_step(transformation_log, "create_features", "create_features",
                      {"n_created": len(feat_log)},
                      len(df), len(df), (time.monotonic() - t0) * 1000)
        except Exception as exc:
            errors.append(f"Feature engineering : {exc}")

    # ── Métriques globales ────────────────────────────────────────────────
    import numpy as np
    rows_after_total = sum(len(d) for d in feuilles_propres.values())

    quality_before = {
        "n_rows":               rows_before,
        "n_cols":               cols_before,
        "global_null_rate_pct": round(
            float(np.mean([q.get("global_null_rate_pct", 0) for q in qualites_before.values()])), 4
        ),
        "total_nulls":  sum(q.get("total_nulls",  0) for q in qualites_before.values()),
        "n_duplicates": sum(q.get("n_duplicates", 0) for q in qualites_before.values()),
        "numeric_stats": {},
    }
    quality_after = {
        "n_rows":               rows_after_total,
        "n_cols":               cols_before,
        "global_null_rate_pct": round(
            float(np.mean([q.get("global_null_rate_pct", 0) for q in qualites_after.values()])), 4
        ),
        "total_nulls":  sum(q.get("total_nulls",  0) for q in qualites_after.values()),
        "n_duplicates": sum(q.get("n_duplicates", 0) for q in qualites_after.values()),
        "numeric_stats": qualites_after.get(nom_principal, {}).get("numeric_stats", {}),
    }

    # ── Étape 9 : Rapport Markdown ────────────────────────────────────────
    report_path = reports_out_dir / f"etl_report_{stem}.md"
    try:
        generate_markdown_report(
            quality_before=quality_before,
            quality_after=quality_after,
            transformation_log=transformation_log,
            output_path=str(report_path),
        )
    except Exception as exc:
        errors.append(f"Rapport Markdown : {exc}")
        report_path = None

    # ── Étape 10 : Script ETL reproductible ───────────────────────────────
    script_path = reports_out_dir / f"etl_script_{stem}.py"
    try:
        generate_etl_script(
            transformation_log=transformation_log,
            dataset_info={"input_path": input_path, "shape_before": (rows_before, cols_before)},
            output_path=script_path,
        )
    except Exception as exc:
        errors.append(f"Script ETL : {exc}")
        script_path = None

    # ── Contenu du rapport pour Open WebUI ────────────────────────────────
    report_content = ""
    if report_path and Path(str(report_path)).exists():
        try:
            report_content = Path(str(report_path)).read_text(encoding="utf-8")
        except Exception:
            pass

    clean_path = saved_files[0] if saved_files else None
    duration   = round(time.monotonic() - t_start, 3)

    pipeline_steps = " → ".join(
        e.get("etape", "").split("[")[0]
        for e in transformation_log
    )

    return {
        "status":          "success" if not errors else "success_with_warnings",
        "dataset_name":    stem,
        "rows_before":     rows_before,
        "rows_after":      rows_after_total,
        "cols_before":     cols_before,
        "cols_after":      df.shape[1],
        "clean_path":      str(clean_path) if clean_path and Path(str(clean_path)).exists() else "",
        "report_path":     str(report_path) if report_path and Path(str(report_path)).exists() else "",
        "report_content":  report_content,
        "script_path":     str(script_path) if script_path and Path(str(script_path)).exists() else "",
        "star_schema":     star_results,
        "transformations": len(transformation_log),
        "pipeline":        pipeline_steps,
        "duration_s":      duration,
        "errors":          errors[:5],
    }


def _nettoyer_feuille(
    df: Any,
    nom: str,
    exclude_cols: list[str],
    miss_strat: str,
    fill_mode: str,
    out_action: str,
    out_method: str,
    out_dir: Path,
    transformation_log: list[dict],
    errors: list[str],
) -> tuple[Any, dict, dict]:
    """Nettoie une feuille — identique à logic.py avec logs enrichis."""

    # A. Rapport qualité AVANT (appelé en premier comme dans logic.py)
    q_before: dict = {}
    try:
        q_before, _ = generate_quality_report(df, label=f"before_{nom}", output_dir=out_dir)
    except Exception as exc:
        errors.append(f"Rapport initial '{nom}' : {exc}")

    # B. Sanitize
    t0 = time.monotonic()
    try:
        df = sanitize_column_names(df)
        _log_step(transformation_log, f"sanitize_column_names[{nom}]",
                  "sanitize_column_names", {}, len(df), len(df),
                  (time.monotonic() - t0) * 1000)
    except Exception as exc:
        errors.append(f"Sanitize '{nom}' : {exc}")

    # C. Valeurs manquantes
    t0 = time.monotonic()
    try:
        rows_bef = len(df)
        df, _ = handle_missing_values(df, strategy=miss_strat, fill_mode=fill_mode)
        _log_step(transformation_log, f"handle_missing_values[{nom}]",
                  "handle_missing_values",
                  {"strategy": miss_strat, "fill_mode": fill_mode},
                  rows_bef, len(df), (time.monotonic() - t0) * 1000)
    except Exception as exc:
        errors.append(f"Missing values '{nom}' : {exc}")

    # D. Doublons
    t0 = time.monotonic()
    try:
        rows_bef = len(df)
        df, dup_rep = remove_duplicates(df)
        _log_step(transformation_log, f"remove_duplicates[{nom}]",
                  "remove_duplicates",
                  {"removed": rows_bef - len(df)},
                  rows_bef, len(df), (time.monotonic() - t0) * 1000)
    except Exception as exc:
        errors.append(f"Doublons '{nom}' : {exc}")

    # E. Consolidation catégorielle
    t0 = time.monotonic()
    try:
        df, consolidation_rep = consolidate_categorical_values(df)
        if consolidation_rep:
            total_repl = sum(r.get("n_replacements", 0) for r in consolidation_rep.values())
            _log_step(transformation_log, f"consolidate_categorical_values[{nom}]",
                      "consolidate_categorical_values",
                      {
                          "n_columns_consolidated": len(consolidation_rep),
                          "total_replacements":     total_repl,
                          "columns":                list(consolidation_rep.keys()),
                      },
                      len(df), len(df), (time.monotonic() - t0) * 1000)
    except Exception as exc:
        errors.append(f"Consolidation '{nom}' : {exc}")

    # F. Types
    t0 = time.monotonic()
    try:
        df, _ = fix_data_types(df)
        _log_step(transformation_log, f"fix_data_types[{nom}]",
                  "fix_data_types", {}, len(df), len(df),
                  (time.monotonic() - t0) * 1000)
    except Exception as exc:
        errors.append(f"Types '{nom}' : {exc}")

    # G. Format dates
    try:
        df = format_date_columns(df)
    except Exception as exc:
        errors.append(f"Format dates '{nom}' : {exc}")

    # H. Outliers
    num_cols = [
        c for c in df.select_dtypes(include="number").columns
        if c not in exclude_cols and not is_protected_column(c, df[c])
    ]
    if num_cols:
        t0 = time.monotonic()
        try:
            df, _ = detect_and_treat_outliers(
                df, columns=num_cols, method=out_method, action=out_action
            )
            _log_step(transformation_log, f"outliers[{nom}]",
                      "detect_and_treat_outliers",
                      {"method": out_method, "action": out_action, "columns": num_cols},
                      len(df), len(df), (time.monotonic() - t0) * 1000)
        except Exception as exc:
            errors.append(f"Outliers '{nom}' : {exc}")

    # I. Rapport qualité APRÈS
    q_after: dict = {}
    try:
        q_after, _ = generate_quality_report(df, label=f"after_{nom}", output_dir=out_dir)
    except Exception as exc:
        errors.append(f"Rapport final '{nom}' : {exc}")

    return df, q_before, q_after


def _clean_stem(stem: str) -> str:
    """Supprime le préfixe UUID Open WebUI du nom de fichier."""
    if "_" in stem:
        parts_stem = stem.split("_", 1)
        candidate  = parts_stem[0].replace("-", "")
        if len(candidate) >= 16 and all(c in "0123456789abcdefABCDEF" for c in candidate):
            return parts_stem[1] if len(parts_stem) > 1 else stem
    return stem


def _resolve_output_dir(input_path: str) -> Path:
    """Calcule le dossier de sortie depuis le chemin d'entrée."""
    p     = Path(input_path)
    parts = list(p.parts)
    if "uploads" in parts:
        try:
            idx  = parts.index("uploads")
            base = Path(*parts[:idx]).parent
            return base / "data" / "processed" / _clean_stem(p.stem)
        except (ValueError, IndexError):
            pass
    try:
        idx = parts.index("raw")
        parts[idx] = "processed"
        return Path(*parts).parent / _clean_stem(p.stem)
    except ValueError:
        return p.parent / "processed" / _clean_stem(p.stem)