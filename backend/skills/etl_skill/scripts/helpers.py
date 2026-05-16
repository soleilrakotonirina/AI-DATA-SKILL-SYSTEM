"""
backend/skills/etl_skill/scripts/helpers.py
Fonctions utilitaires partagees par main.py et logic.py.

Fonctions :
    detect_file_format    : Detection du format depuis l'extension
    infer_column_role     : Inference du role semantique d'une colonne
    build_schema_summary  : Resume du schema pour prompt Gemini
    sanitize_column_names : Normalisation des noms de colonnes
    format_duration       : Formatage de duree en chaine lisible
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd

_SUPPORTED_FORMATS: set[str] = {
    ".csv", ".tsv", ".txt", ".xlsx", ".xlsm", ".xls", ".json", ".parquet"
}


def _sans_accent(s: str) -> str:
    """Supprime les accents d'une chaine."""
    return "".join(
        c for c in unicodedata.normalize("NFD", str(s))
        if unicodedata.category(c) != "Mn"
    )


def detect_file_format(filepath: str | Path) -> str:
    """
    Retourne le format d'un fichier a partir de son extension.

    Args:
        filepath: Chemin vers le fichier.

    Returns:
        Extension normalisee sans le point ('csv', 'xlsx', 'json', 'parquet').

    Raises:
        ValueError: Si l'extension n'est pas supportee.
    """
    ext = Path(filepath).suffix.lower()
    if ext not in _SUPPORTED_FORMATS:
        raise ValueError(
            f"Format non supporte : '{ext}'. "
            f"Formats : {sorted(_SUPPORTED_FORMATS)}"
        )
    return ext.lstrip(".")


def infer_column_role(series: pd.Series) -> str:
    """
    Infere le role semantique d'une colonne d'un DataFrame.

    Categories possibles :
    - 'id'          : colonne d'identifiant (entiers sequentiels)
    - 'numeric'     : mesure numerique agregable
    - 'categorical' : variable categorielle (peu de valeurs uniques)
    - 'datetime'    : colonne de date/heure
    - 'text'        : texte libre (haute cardinalite, chaines longues)

    Args:
        series: Colonne du DataFrame a analyser.

    Returns:
        Chaine decrivant le role infere.
    """
    name_l = _sans_accent(series.name or "").lower()
    n_unique = series.nunique()
    n_total = len(series.dropna())

    if n_total == 0:
        return "categorical"

    ratio = n_unique / n_total

    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"

    id_patterns = {"id", "pk", "key", "uuid", "code", "ref", "num", "numero", "matricule"}
    if any(p in name_l for p in id_patterns):
        return "id"

    if pd.api.types.is_integer_dtype(series) and ratio > 0.95 and n_unique > 20:
        return "id"

    if pd.api.types.is_numeric_dtype(series):
        return "numeric"

    if series.dtype == object:
        avg_len = series.dropna().astype(str).str.len().mean()
        if avg_len > 50 and ratio > 0.8:
            return "text"

    return "categorical"


def build_schema_summary(df: pd.DataFrame) -> dict[str, Any]:
    """
    Construit un resume du schema d'un DataFrame.

    Adapte a l'injection dans un prompt Gemini. Contient pour
    chaque colonne : dtype, role infere, cardinalite, exemples.

    Args:
        df: DataFrame a resumer.

    Returns:
        Dict JSON-serialisable decrivant la structure du DataFrame.
    """
    schema: dict[str, Any] = {
        "n_rows": len(df),
        "n_cols": len(df.columns),
        "columns": {},
    }

    for col in df.columns:
        s = df[col]
        role = infer_column_role(s)
        examples = [
            str(e) if not isinstance(e, (int, float, bool, str)) else e
            for e in s.dropna().head(5).tolist()
        ]
        col_info: dict[str, Any] = {
            "dtype": str(s.dtype),
            "role": role,
            "n_unique": int(s.nunique()),
            "n_null": int(s.isna().sum()),
            "examples": examples,
        }
        if pd.api.types.is_numeric_dtype(s) and not s.empty:
            col_info.update({
                "min": float(s.min()),
                "max": float(s.max()),
                "mean": round(float(s.mean()), 4),
            })
        schema["columns"][col] = col_info

    return schema


def sanitize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalise les noms de colonnes d'un DataFrame.

    Transformations :
    - Suppression des accents
    - Passage en minuscules
    - Caracteres speciaux et espaces -> underscores
    - Underscores multiples -> un seul
    - Deduplication

    Args:
        df: DataFrame a normaliser.

    Returns:
        DataFrame avec noms de colonnes normalises.
    """
    new_cols: list[str] = []
    for col in df.columns:
        clean = _sans_accent(str(col)).strip().lower()
        clean = re.sub(r"[^\w]", "_", clean)
        clean = re.sub(r"_+", "_", clean).strip("_")
        if not clean:
            clean = f"col_{len(new_cols)}"
        new_cols.append(clean)

    seen: dict[str, int] = {}
    dedup: list[str] = []
    for name in new_cols:
        if name in seen:
            seen[name] += 1
            dedup.append(f"{name}_{seen[name]}")
        else:
            seen[name] = 0
            dedup.append(name)

    df = df.copy()
    df.columns = dedup
    return df


def format_duration(ms: float) -> str:
    """
    Formate une duree en millisecondes en chaine lisible.

    Args:
        ms: Duree en millisecondes.

    Returns:
        Chaine formatee : '450ms', '1.23s', '2m 15s'.
    """
    if ms < 1000:
        return f"{ms:.0f}ms"
    s = ms / 1000
    if s < 60:
        return f"{s:.2f}s"
    return f"{int(s // 60)}m {s % 60:.0f}s"