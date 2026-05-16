"""
backend/skills/etl_skill/core/cleaner.py
Chargement universel et nettoyage des datasets bruts.

Compatible : CSV (auto-sep + auto-enc), Excel mono/multi-feuilles,
             JSON (multi-orientations), Parquet.

Fonctions principales :
    load_dataset          : Chargement multi-format avec detection automatique
    remove_duplicates     : Suppression des doublons avec rapport
    fix_data_types        : Correction automatique des types de donnees
    handle_missing_values : Gestion intelligente des valeurs manquantes
    sanitize_column_names : Normalisation des noms de colonnes
    format_date_columns   : Formatage propre des colonnes datetime
    is_protected_column   : Detection des colonnes a ne pas transformer
"""

from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Constantes de chargement ──────────────────────────────────────────────────
_CSV_ENCODINGS: list[str] = ["utf-8", "utf-8-sig", "latin-1", "cp1252", "iso-8859-1"]
_CSV_SEPARATORS: list[str] = [",", ";", "\t", "|"]
_JSON_ORIENTATIONS: list[str] = ["records", "columns", "index", "split"]
_SUPPORTED_FORMATS: set[str] = {
    ".csv", ".tsv", ".txt", ".xlsx", ".xlsm", ".xls", ".json", ".parquet"
}
# Seuil de pertes acceptees lors d'une conversion de type (20%)
_CONVERSION_THRESHOLD: float = 0.20

# ── Patterns de detection de colonnes protegees ───────────────────────────────
_ID_PATTERNS = re.compile(
    r"(^id$|^id_|_id$|^pk$|^uuid$|^matricule|^code_|^ref_|^num_|^numero|^cle$)",
    re.IGNORECASE,
)
_EMAIL_PATTERNS = re.compile(r"(email|mail|courriel)", re.IGNORECASE)
_PHONE_PATTERNS = re.compile(r"(telephone|phone|tel$|mobile|portable|gsm)", re.IGNORECASE)
_DATE_PATTERNS = re.compile(
    r"(date|naissance|embauche|inscription|creation|debut|fin)", re.IGNORECASE
)
_FREETEXT_PATTERNS = re.compile(
    r"(^nom$|^prenom$|^nom_|^prenom_|firstname|lastname|^name$|^bureau$)",
    re.IGNORECASE,
)
_TELEPHONE_PATTERNS = re.compile(
    r"(telephone|phone|tel$|mobile|portable|gsm)", re.IGNORECASE
)
_ANNEE_PATTERNS = re.compile(
    r"(annee[_\s]inscription|annee[_\s]naissance|annee[_\s]scolaire"
    r"|year[_\s]|[_\s]year$|^year$)",
    re.IGNORECASE,
)
_LIBELLE_PATTERNS = re.compile(
    r"(nom_cours|libelle|designation|intitule|description)", re.IGNORECASE
)


# ── Helpers internes ──────────────────────────────────────────────────────────

def _sans_accent(s: str) -> str:
    """Supprime les accents d'une chaine de caracteres."""
    return "".join(
        c for c in unicodedata.normalize("NFD", str(s))
        if unicodedata.category(c) != "Mn"
    )


def _load_csv(path: Path) -> tuple[pd.DataFrame, str, str]:
    """
    Charge un fichier CSV en testant les combinaisons encodage x separateur.

    Args:
        path: Chemin vers le fichier CSV/TSV/TXT.

    Returns:
        Tuple (DataFrame, encodage_utilise, separateur_utilise).

    Raises:
        ValueError: Si aucune combinaison ne produit un DataFrame valide.
    """
    for enc in _CSV_ENCODINGS:
        for sep in _CSV_SEPARATORS:
            try:
                df = pd.read_csv(path, sep=sep, encoding=enc, engine="python")
                if df.shape[1] > 1:
                    logger.debug("CSV charge — encodage=%s, sep=%r", enc, sep)
                    return df, enc, sep
            except Exception:
                continue
    # Dernier recours : detection automatique du separateur
    try:
        df = pd.read_csv(path, sep=None, encoding="utf-8", engine="python")
        return df, "utf-8", "auto"
    except Exception as exc:
        raise ValueError(
            f"Impossible de charger le CSV '{path.name}' : {exc}"
        ) from exc


def _load_excel(
    path: Path, sheet_name: Any
) -> pd.DataFrame | dict[str, pd.DataFrame]:
    """
    Charge un fichier Excel mono ou multi-feuilles.

    Args:
        path       : Chemin vers le fichier Excel.
        sheet_name : Nom/index de la feuille, ou None pour toutes les feuilles.

    Returns:
        DataFrame si sheet_name est specifie, dict {nom_feuille: DataFrame} sinon.

    Raises:
        ValueError: Si le fichier ne peut pas etre lu par openpyxl.
    """
    try:
        if sheet_name is None:
            xl = pd.ExcelFile(path, engine="openpyxl")
            result: dict[str, pd.DataFrame] = {}
            for name in xl.sheet_names:
                df = xl.parse(name)
                if not df.empty:
                    result[name] = df
            return result
        return pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl")
    except Exception as exc:
        raise ValueError(
            f"Impossible de charger l'Excel '{path.name}' : {exc}"
        ) from exc


def _load_json(path: Path) -> pd.DataFrame:
    """
    Charge un fichier JSON en testant plusieurs orientations.

    Args:
        path: Chemin vers le fichier JSON.

    Returns:
        DataFrame charge depuis le JSON.

    Raises:
        ValueError: Si aucune orientation ne produit un DataFrame valide.
    """
    for orient in _JSON_ORIENTATIONS:
        try:
            df = pd.read_json(path, orient=orient)
            if not df.empty:
                logger.debug("JSON charge — orientation=%s", orient)
                return df
        except Exception:
            continue
    raise ValueError(f"Impossible de charger le JSON '{path.name}'.")


# ── Detection de colonnes protegees ───────────────────────────────────────────

def is_id_column(col: str, series: pd.Series | None = None) -> bool:
    """
    Detecte si une colonne est un identifiant technique (ID, PK, FK).

    Args:
        col    : Nom de la colonne.
        series : Serie pandas optionnelle pour analyse des valeurs.

    Returns:
        True si la colonne est un identifiant technique.
    """
    col_l = _sans_accent(col).lower().strip()
    if _ID_PATTERNS.match(col_l):
        return True
    if series is not None and pd.api.types.is_object_dtype(series):
        sample = series.dropna().astype(str).head(5).tolist()
        if any(re.match(r"^[A-Z]{2,5}\d{3,}", s) for s in sample):
            return True
    return False


def is_telephone_column(col: str, series: pd.Series | None = None) -> bool:
    """
    Detecte les colonnes contenant des numeros de telephone.

    Args:
        col    : Nom de la colonne.
        series : Serie pandas optionnelle pour analyse des valeurs.

    Returns:
        True si la colonne contient probablement des numeros de telephone.
    """
    if _TELEPHONE_PATTERNS.search(col.lower()):
        return True
    if series is not None and pd.api.types.is_integer_dtype(series):
        sample = series.dropna()
        if len(sample) > 0:
            avg_len = sample.astype(str).str.len().mean()
            if 8 <= avg_len <= 12 and sample.nunique() / len(sample) > 0.8:
                return True
    return False


def is_annee_column(col: str, series: pd.Series | None = None) -> bool:
    """
    Detecte les colonnes contenant des annees (ex : 2020, 2021).

    Args:
        col    : Nom de la colonne.
        series : Serie pandas optionnelle pour analyse des valeurs.

    Returns:
        True si la colonne contient probablement des annees.
    """
    col_n = _sans_accent(col).lower()
    if _ANNEE_PATTERNS.search(col_n):
        return True
    if series is not None and pd.api.types.is_integer_dtype(series):
        s = series.dropna()
        if len(s) > 0:
            mn, mx = float(s.min()), float(s.max())
            if 1900 <= mn and mx <= 2100 and s.nunique() <= 20:
                return True
    return False


def is_libelle_column(col: str, series: pd.Series | None = None) -> bool:
    """
    Detecte les colonnes de libelles (descriptions uniques non agregables).

    Args:
        col    : Nom de la colonne.
        series : Serie pandas optionnelle pour analyse des valeurs.

    Returns:
        True si la colonne est un libelle non transformable.
    """
    col_n = _sans_accent(col).lower()
    if _LIBELLE_PATTERNS.search(col_n):
        return True
    if series is not None and pd.api.types.is_string_dtype(series):
        s = series.dropna()
        if len(s) > 2 and s.nunique() == len(s):
            return True
    return False


def is_protected_column(col: str, series: pd.Series | None = None) -> bool:
    """
    Retourne True si la colonne NE DOIT PAS etre encodee ni scalee.

    Les colonnes protegees sont : IDs, emails, telephones, dates,
    noms/prenoms libres, annees, libelles uniques.

    Args:
        col    : Nom de la colonne.
        series : Serie pandas optionnelle pour analyse semantique.

    Returns:
        True si la colonne doit etre exclue des transformations.
    """
    if is_id_column(col, series):
        return True
    col_l = _sans_accent(col).lower()
    for pattern in [_EMAIL_PATTERNS, _PHONE_PATTERNS, _DATE_PATTERNS, _FREETEXT_PATTERNS]:
        if pattern.search(col_l):
            return True
    if is_telephone_column(col, series):
        return True
    if is_annee_column(col, series):
        return True
    if is_libelle_column(col, series):
        return True
    return False


# ── API publique ──────────────────────────────────────────────────────────────

def sanitize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalise les noms de colonnes : sans accents, minuscules, underscores.

    Transformations appliquees :
    - Suppression des accents
    - Passage en minuscules
    - Caracteres speciaux et espaces -> underscores
    - Underscores multiples -> un seul
    - Deduplication des noms identiques

    Args:
        df: DataFrame avec les noms de colonnes a normaliser.

    Returns:
        DataFrame avec les noms de colonnes normalises.
    """
    new_cols: list[str] = []
    for col in df.columns:
        clean = _sans_accent(str(col)).strip().lower()
        clean = re.sub(r"[^\w]", "_", clean)
        clean = re.sub(r"_+", "_", clean).strip("_")
        if not clean:
            clean = f"col_{len(new_cols)}"
        new_cols.append(clean)

    # Deduplication : ajouter suffixe _1, _2... si doublons
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


def format_date_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Formate proprement toutes les colonnes datetime en 'YYYY-MM-DD'.

    Elimine le '00:00:00.000000000' des dates pures.
    Si la colonne contient des heures non nulles, conserve 'YYYY-MM-DD HH:MM:SS'.
    Remplace les valeurs NaT par une chaine vide.

    Args:
        df: DataFrame contenant des colonnes datetime.

    Returns:
        DataFrame avec les colonnes datetime formatees en chaines lisibles.
    """
    df = df.copy()
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            s = df[col].dropna()
            if len(s) == 0:
                continue
            has_time = (
                (s.dt.hour != 0).any()
                or (s.dt.minute != 0).any()
                or (s.dt.second != 0).any()
            )
            if has_time:
                df[col] = df[col].dt.strftime("%Y-%m-%d %H:%M:%S")
                logger.info("Date formatee '%s' → YYYY-MM-DD HH:MM:SS", col)
            else:
                df[col] = df[col].dt.strftime("%Y-%m-%d")
                logger.info("Date formatee '%s' → YYYY-MM-DD", col)
            df[col] = df[col].replace("NaT", "")
    return df


def load_dataset(
    filepath: str | Path,
    sheet_name: Any = None,
) -> tuple[pd.DataFrame | dict[str, pd.DataFrame], dict[str, Any]]:
    """
    Charge un dataset depuis CSV, Excel, JSON ou Parquet.

    Pour les fichiers Excel, si sheet_name=None, charge toutes les feuilles
    et retourne un dict {nom_feuille: DataFrame}.

    Args:
        filepath   : Chemin vers le fichier source.
        sheet_name : Feuille Excel a charger (None = toutes les feuilles).

    Returns:
        Tuple (data, metadata) ou data est un DataFrame ou un dict de DataFrames.
        metadata contient format, encodage, separateur, shape, colonnes, dtypes.

    Raises:
        FileNotFoundError: Si le fichier n'existe pas.
        ValueError        : Si le format n'est pas supporte.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {path}")

    suffix = path.suffix.lower()
    if suffix not in _SUPPORTED_FORMATS:
        raise ValueError(
            f"Format non supporte : '{suffix}'. "
            f"Formats acceptes : {sorted(_SUPPORTED_FORMATS)}"
        )

    meta: dict[str, Any] = {"format": suffix.lstrip(".")}

    if suffix in {".csv", ".tsv", ".txt"}:
        df, enc, sep = _load_csv(path)
        meta.update({
            "encoding": enc,
            "separator": sep,
            "shape": df.shape,
            "columns": df.columns.tolist(),
            "dtypes": df.dtypes.astype(str).to_dict(),
        })
        logger.info(
            "CSV charge : %s (%d lignes x %d colonnes)", path.name, *df.shape
        )
        return df, meta

    if suffix in {".xlsx", ".xlsm", ".xls"}:
        result = _load_excel(path, sheet_name)
        if isinstance(result, dict):
            meta["sheet_names"] = list(result.keys())
            meta["shapes"] = {k: v.shape for k, v in result.items()}
            logger.info(
                "Excel multi-feuilles : %s (%d feuilles)", path.name, len(result)
            )
        else:
            meta.update({
                "shape": result.shape,
                "columns": result.columns.tolist(),
                "dtypes": result.dtypes.astype(str).to_dict(),
            })
            logger.info(
                "Excel charge : %s (%d lignes x %d colonnes)",
                path.name,
                *result.shape,
            )
        return result, meta

    if suffix == ".json":
        df = _load_json(path)
        meta.update({
            "shape": df.shape,
            "columns": df.columns.tolist(),
            "dtypes": df.dtypes.astype(str).to_dict(),
        })
        logger.info(
            "JSON charge : %s (%d lignes x %d colonnes)", path.name, *df.shape
        )
        return df, meta

    if suffix == ".parquet":
        df = pd.read_parquet(path)
        meta.update({
            "shape": df.shape,
            "columns": df.columns.tolist(),
            "dtypes": df.dtypes.astype(str).to_dict(),
        })
        logger.info(
            "Parquet charge : %s (%d lignes x %d colonnes)", path.name, *df.shape
        )
        return df, meta

    raise ValueError(f"Format non gere : {suffix}")


def remove_duplicates(
    df: pd.DataFrame,
    subset: list[str] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Supprime les lignes dupliquees avec rapport detaille.

    Args:
        df    : DataFrame a deduplicationner.
        subset: Colonnes sur lesquelles detecter les doublons (None = toutes).

    Returns:
        Tuple (df_clean, rapport) ou rapport contient rows_before, rows_after,
        rows_removed et percent_removed.
    """
    before = len(df)
    df_clean = df.drop_duplicates(subset=subset, keep="first")
    removed = before - len(df_clean)
    pct = round(removed / before * 100, 2) if before > 0 else 0.0

    if removed > 0:
        logger.info(
            "Doublons supprimes : %d (%.1f%%) — %d lignes restantes",
            removed,
            pct,
            len(df_clean),
        )
    else:
        logger.info("Aucun doublon detecte.")

    rapport = {
        "rows_before": before,
        "rows_after": len(df_clean),
        "rows_removed": removed,
        "percent_removed": pct,
        "subset": subset,
    }
    return df_clean, rapport


def fix_data_types(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """
    Corrige automatiquement les types des colonnes object en datetime ou float.

    Tentative datetime : si moins de 20% de NaT produits, appliquer.
    Tentative float    : si moins de 20% de NaN produits, appliquer.

    Args:
        df: DataFrame avec des colonnes potentiellement mal typees.

    Returns:
        Tuple (df_fixed, conversions_log) ou conversions_log liste les
        conversions effectuees {column, type_before, type_after, method}.
    """
    df_fixed = df.copy()
    log: list[dict[str, Any]] = []

    for col in df_fixed.select_dtypes(include=["object", "str"]).columns:
        orig = str(df_fixed[col].dtype)
        non_null = df_fixed[col].dropna()
        if len(non_null) == 0:
            continue

        # Tentative datetime
        try:
            converted_dt = pd.to_datetime(non_null, errors="coerce", format="mixed")
        except TypeError:
            converted_dt = pd.to_datetime(non_null, errors="coerce")

        if converted_dt.isna().sum() / len(non_null) <= _CONVERSION_THRESHOLD:
            try:
                df_fixed[col] = pd.to_datetime(
                    df_fixed[col], errors="coerce", format="mixed"
                )
            except TypeError:
                df_fixed[col] = pd.to_datetime(df_fixed[col], errors="coerce")
            log.append({
                "column": col,
                "type_before": orig,
                "type_after": str(df_fixed[col].dtype),
                "method": "datetime",
            })
            logger.info(
                "Conversion datetime : '%s' (%s → %s)", col, orig, df_fixed[col].dtype
            )
            continue

        # Tentative numerique
        converted_num = pd.to_numeric(non_null, errors="coerce")
        if converted_num.isna().sum() / len(non_null) <= _CONVERSION_THRESHOLD:
            df_fixed[col] = pd.to_numeric(df_fixed[col], errors="coerce")
            log.append({
                "column": col,
                "type_before": orig,
                "type_after": str(df_fixed[col].dtype),
                "method": "numeric",
            })
            logger.info(
                "Conversion numerique : '%s' (%s → %s)",
                col,
                orig,
                df_fixed[col].dtype,
            )

    return df_fixed, log


def handle_missing_values(
    df: pd.DataFrame,
    strategy: str = "auto",
    threshold: float = 0.5,
    fill_mode: str = "smart",
    drop_empty_rows: bool = True,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """
    Gere les valeurs manquantes selon la strategie et le mode choisis.

    Etape 1 : Suppression des lignes entierement vides (si drop_empty_rows=True).
    Etape 2 : Suppression des colonnes avec taux nullite > threshold.
    Etape 3 : Imputation des valeurs restantes selon strategy + fill_mode.
    Etape 4 : Logging de chaque imputation.

    Strategies :
        'auto' + 'smart'    : mediane (numerique), mode (categoriel), ffill (datetime)
        'constant'          : 0 (numerique), 'N/D' (texte), ffill (datetime)
        'drop'              : suppression des lignes avec valeurs manquantes

    Args:
        df             : DataFrame a traiter.
        strategy       : 'auto', 'constant', ou 'drop'.
        threshold      : Seuil de nullite pour suppression de colonne (0.0 a 1.0).
        fill_mode      : 'smart' ou 'constant'.
        drop_empty_rows: Supprimer les lignes entierement vides avant imputation.

    Returns:
        Tuple (df_imputed, imputation_log) ou imputation_log liste les
        imputations effectuees {step, column, n_values_treated, method}.
    """
    df_out = df.copy()
    log: list[dict[str, Any]] = []

    # Etape 1 — Lignes entierement vides
    if drop_empty_rows:
        before = len(df_out)
        df_out = df_out.dropna(how="all")
        removed = before - len(df_out)
        if removed > 0:
            log.append({"step": "drop_empty_rows", "rows_removed": removed})
            logger.info("Lignes vides supprimees : %d", removed)

    # Etape 2 — Colonnes trop lacunaires
    cols_drop = [
        c for c in df_out.columns
        if df_out[c].isna().mean() > threshold
    ]
    if cols_drop:
        df_out = df_out.drop(columns=cols_drop)
        log.append({
            "step": "drop_high_nullity_columns",
            "columns_dropped": cols_drop,
        })
        logger.info(
            "Colonnes supprimees (>%.0f%% nulls) : %s", threshold * 100, cols_drop
        )

    # Etape 3 — Imputation
    use_constant = (strategy == "constant") or (fill_mode == "constant")

    for col in df_out.columns:
        n_missing = int(df_out[col].isna().sum())
        if n_missing == 0:
            continue

        dtype = df_out[col].dtype

        if strategy == "drop":
            df_out = df_out.dropna(subset=[col])
            log.append({
                "step": "drop_rows",
                "column": col,
                "rows_dropped": n_missing,
            })
            continue

        if use_constant:
            if pd.api.types.is_datetime64_any_dtype(dtype):
                df_out[col] = df_out[col].ffill().bfill()
                method = "forward_fill"
            elif pd.api.types.is_numeric_dtype(dtype):
                df_out[col] = df_out[col].fillna(0)
                method = "constant_0"
            else:
                df_out[col] = df_out[col].astype(object).fillna("N/D")
                method = "constant_ND"
        else:
            # Mode smart
            if pd.api.types.is_datetime64_any_dtype(dtype):
                df_out[col] = df_out[col].ffill().bfill()
                method = "temporal_ffill"
            elif pd.api.types.is_numeric_dtype(dtype):
                med = df_out[col].median()
                df_out[col] = df_out[col].fillna(med)
                method = f"median({med:.4g})"
            else:
                modes = df_out[col].mode()
                fill_val = modes.iloc[0] if len(modes) > 0 else "N/D"
                df_out[col] = df_out[col].astype(object).fillna(fill_val)
                method = f"mode('{fill_val}')"

        log.append({
            "step": "imputation",
            "column": col,
            "n_values_treated": n_missing,
            "method": method,
        })
        logger.info("Imputation '%s' : %d valeurs → %s", col, n_missing, method)

    return df_out, log