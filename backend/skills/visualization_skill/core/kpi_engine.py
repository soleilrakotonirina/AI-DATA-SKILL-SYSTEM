"""
backend/skills/visualization_skill/core/kpi_engine.py
Moteur de KPI et detection intelligente des colonnes.

Adapte depuis kpi_engine.py. Detecte automatiquement le type
semantique de chaque colonne et calcule des KPIs pertinents.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ─── Regex strictes ───────────────────────────────────────────────────────────

_RE_TEMPOREL = re.compile(
    r"(^annee[_\s]|[_\s]annee$|^annee$"
    r"|^mois[_\s]|[_\s]mois$|^mois$"
    r"|^jour[_\s]|[_\s]jour$|^jour$"
    r"|^year[_\s]|[_\s]year$|^year$"
    r"|^month[_\s]|[_\s]month$|^month$"
    r"|^day[_\s]|[_\s]day$|^day$"
    r"|^date[_\s]|[_\s]date$|^date$"
    r"|^trimestre|^quarter"
    r"|^periode[_\s]|^period[_\s]"
    r"|timestamp|annee_inscription|annee_naissance"
    r"|annee_academique|annee_scolaire|annee_academique_cours)",
    re.IGNORECASE,
)

_RE_ID = re.compile(
    r"(^id[_\s]?$|[_\s]?id$|.*_id$|.*_code$"
    r"|^code[_\s]?$|^num[_\s]?$|^numero$|^matricule$|^uuid$|^pk$|^fk$)",
    re.IGNORECASE,
)

_KEYWORDS_CONTACT = [
    "telephone", "tel", "phone", "mobile", "portable", "email", "mail",
    "adresse", "address", "rue", "commune", "cp", "postal", "fax",
]

_KEYWORDS_NOM_PROPRE = [
    "^nom$", "^prenom$", "^firstname$", "^lastname$", "^fullname$",
    "^nom_", "_nom$", "^prenom_", "_prenom$",
    "nom_enseignants", "prenom_enseignants",
]

_RE_NOM_PROPRE = re.compile(
    "|".join(_KEYWORDS_NOM_PROPRE),
    re.IGNORECASE,
)

_KEYWORDS_VALEUR = [
    "montant", "valeur", "total", "chiffre", "ca", "revenu", "recette",
    "budget", "cout", "prix", "salaire", "score", "note", "taux",
    "pct", "percent", "ratio", "credits", "credit", "ects", "volume",
    "quantite", "qte", "effectif", "population",
    "export", "import", "marge", "benefice", "ventes",
    "usd", "ariary", "eur", "note_finale", "note_moyenne",
]


# ─── Fonctions de detection (logique kpi_engine.py v7) ────────────────────────

def _est_dtype_texte(serie: pd.Series) -> bool:
    """Retourne True si la serie est de type texte (pandas 2/3 compatible)."""
    return pd.api.types.is_string_dtype(serie) or serie.dtype == object


def _est_temporelle(col: str, serie: Optional[pd.Series] = None) -> bool:
    """Deteccion stricte v7 — evite les faux positifs sur IDs sequentiels."""
    col_l = col.lower().strip()
    if _RE_TEMPOREL.search(col_l):
        return True
    if serie is not None and pd.api.types.is_numeric_dtype(serie):
        v = serie.dropna()
        if len(v) == 0:
            return False
        mn, mx, nu = float(v.min()), float(v.max()), int(v.nunique())
        if nu > 200 or (mx - mn) > 200:
            return False
        # Verifie qu'on n'est pas un ID sequentiel
        if nu <= 15:
            try:
                sv = sorted(v.unique())
                diffs = [sv[i + 1] - sv[i] for i in range(len(sv) - 1)]
                if all(d == 1 for d in diffs):
                    return False
            except Exception:
                pass
        if 1900 <= mn and mx <= 2100 and nu <= 130:
            return True
        if 1 <= mn and mx <= 12 and 6 <= nu <= 12:
            return True
    return False


def _est_id(col: str, serie: Optional[pd.Series] = None) -> bool:
    """Detection des colonnes identifiant."""
    if _RE_ID.match(col.lower().strip()):
        return True
    if serie is not None and pd.api.types.is_numeric_dtype(serie):
        v = serie.dropna()
        n_u, n_t = v.nunique(), len(v)
        if n_t > 10 and (n_u / n_t) > 0.95:
            try:
                sv = sorted(v.unique())
                diffs = [sv[i + 1] - sv[i] for i in range(min(len(sv) - 1, 15))]
                if all(d == 1 for d in diffs):
                    return True
            except Exception:
                pass
    return False


def _est_contact(col: str) -> bool:
    """Detection des colonnes de contact (email, telephone...)."""
    return any(kw in col.lower() for kw in _KEYWORDS_CONTACT)


def _est_nom_propre(col: str) -> bool:
    """Detection des noms propres (non analytiques)."""
    return bool(_RE_NOM_PROPRE.search(col.lower().strip()))


def _est_constante(serie: pd.Series) -> bool:
    """Retourne True si la colonne a moins de 2 valeurs distinctes."""
    return serie.dropna().nunique() < 2


def _est_valeur_reelle(col: str, serie: pd.Series) -> bool:
    """Detection des mesures numeriques reelles (non-ID, non-temporelle)."""
    if not pd.api.types.is_numeric_dtype(serie):
        return False
    if _est_temporelle(col, serie):
        return False
    if _est_contact(col):
        return False
    if _est_id(col, serie):
        return False
    v = serie.dropna()
    if len(v) < 2 or float(v.std()) == 0:
        return False
    kw_match = any(kw in col.lower() for kw in _KEYWORDS_VALEUR)
    # Accepter si mot-cle valeur OU si variance suffisante avec cardinalite raisonnable
    if not kw_match and v.nunique() < 3:
        return False
    return True


def _est_entite(col: str, serie: pd.Series, max_u: int = 60) -> bool:
    """Detection des dimensions analytiques (colonnes categorielles pertinentes)."""
    if not _est_dtype_texte(serie):
        return False
    if _RE_ID.match(col.lower().strip()):
        return False
    if _est_contact(col):
        return False
    if _est_nom_propre(col):
        return False
    n_u, n_t = serie.nunique(), len(serie.dropna())
    if n_u < 2 or n_u > max_u:
        return False
    return True


# ─── Classificateur principal ─────────────────────────────────────────────────

def classifier_colonnes(df: pd.DataFrame) -> Dict[str, List[str]]:
    """
    Classifie chaque colonne du DataFrame par type semantique.

    Args:
        df: DataFrame a analyser.

    Returns:
        Dict avec les cles :
        {
          "entites":    [col, ...],  # dimensions analytiques
          "mesures":    [col, ...],  # valeurs numeriques reelles
          "temporelles":[col, ...],  # annees/periodes numeriques
          "dates_str":  [col, ...],  # dates texte
          "noms_propres":[col, ...], # noms non analytiques
          "exclues":    [col, ...],  # IDs, contacts, constantes
        }
    """
    entites: List[str] = []
    mesures: List[str] = []
    temporelles: List[str] = []
    dates_str: List[str] = []
    noms_propres: List[str] = []
    exclues: List[str] = []

    for col in df.columns:
        serie = df[col]

        # 1. Constante → exclue
        if _est_constante(serie):
            exclues.append(col)
            continue

        # 2. ID → exclu
        if _est_id(col, serie):
            exclues.append(col)
            continue

        # 3. Contact → exclu
        if _est_contact(col):
            exclues.append(col)
            continue

        # 4. Nom propre (texte non analytique)
        if _est_nom_propre(col):
            noms_propres.append(col)
            continue

        # 5. Date texte (format YYYY-MM-DD, etc.)
        if _est_dtype_texte(serie):
            sample = serie.dropna().head(10).astype(str)
            if sample.str.match(r"^\d{4}-\d{2}-\d{2}").mean() > 0.7:
                dates_str.append(col)
                continue

        # 6. Temporelle numerique
        if _est_temporelle(col, serie):
            temporelles.append(col)
            continue

        # 7. Mesure numerique reelle
        if _est_valeur_reelle(col, serie):
            mesures.append(col)
            continue

        # 8. Dimension analytique
        if _est_entite(col, serie):
            entites.append(col)
            continue

        # 9. Reste → exclu
        exclues.append(col)

    logger.info(
        "[KPI] Colonnes classifiees — entites=%d, mesures=%d, temporelles=%d, exclues=%d",
        len(entites), len(mesures), len(temporelles), len(exclues),
    )
    return {
        "entites":     entites,
        "mesures":     mesures,
        "temporelles": temporelles,
        "dates_str":   dates_str,
        "noms_propres": noms_propres,
        "exclues":     exclues,
    }


# ─── Calcul des KPIs ──────────────────────────────────────────────────────────

def calculer_kpis(
    df: pd.DataFrame,
    colonnes: Dict[str, List[str]],
    spec_kpis: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Calcule les KPIs principaux du dataset.

    Args:
        df:        DataFrame source.
        colonnes:  Colonnes classifiees (depuis classifier_colonnes).
        spec_kpis: Spec Gemini [{"label", "colonne", "formule", "icone"}] ou None.

    Returns:
        Dict :
        {
          "kpis_principaux": [{"label", "valeur", "icone", "formule"}],
          "distributions":   {col: [{val, count, pct}]},
          "stats_mesures":   {col: {mean, std, min, max}},
          "evolution":       {col: [{periode, count}]},
        }
    """
    result: Dict[str, Any] = {
        "kpis_principaux": [],
        "distributions":   {},
        "stats_mesures":   {},
        "evolution":       {},
    }

    n_rows = len(df)

    # ── KPIs depuis spec Gemini ───────────────────────────────────────────────
    if spec_kpis:
        for spec in spec_kpis:
            label   = spec.get("label", "")
            col     = spec.get("colonne")
            formule = spec.get("formule", "count")
            icone   = spec.get("icone", "📊")

            try:
                valeur = _calculer_valeur_kpi(df, col, formule, n_rows)
                result["kpis_principaux"].append({
                    "label":   label,
                    "valeur":  valeur,
                    "icone":   icone,
                    "formule": formule,
                })
            except Exception as exc:
                logger.debug("[KPI] Spec '%s' echouee : %s", label, exc)

    # ── KPIs automatiques si pas de spec ────────────────────────────────────
    if not result["kpis_principaux"]:
        result["kpis_principaux"] = _kpis_automatiques(df, colonnes, n_rows)

    # ── Distributions des entites ────────────────────────────────────────────
    for col in colonnes.get("entites", [])[:8]:
        vc = df[col].value_counts().head(20)
        result["distributions"][col] = [
            {"valeur": str(k), "count": int(v), "pct": round(v / n_rows * 100, 1)}
            for k, v in vc.items()
        ]

    # ── Stats des mesures ────────────────────────────────────────────────────
    for col in colonnes.get("mesures", []):
        v = df[col].dropna()
        if len(v) < 2:
            continue
        result["stats_mesures"][col] = {
            "mean":   round(float(v.mean()), 2),
            "std":    round(float(v.std()), 2),
            "min":    round(float(v.min()), 2),
            "max":    round(float(v.max()), 2),
            "median": round(float(v.median()), 2),
        }

    # ── Evolution temporelle ─────────────────────────────────────────────────
    for col in colonnes.get("temporelles", []):
        par_date = df.groupby(col).size().reset_index(name="count")
        par_date = par_date.sort_values(col)
        result["evolution"][col] = [
            {"periode": int(row[col]) if pd.api.types.is_numeric_dtype(df[col]) else str(row[col]),
             "count": int(row["count"])}
            for _, row in par_date.iterrows()
        ]

    return result


def _calculer_valeur_kpi(
    df: pd.DataFrame,
    col: Optional[str],
    formule: str,
    n_rows: int,
) -> Any:
    """Calcule la valeur d'un KPI selon sa formule."""
    if formule == "count" or col is None:
        return n_rows
    if col not in df.columns:
        return None

    serie = df[col].dropna()

    if formule == "nunique":
        return int(serie.nunique())
    if formule == "sum":
        return round(float(serie.sum()), 2)
    if formule == "mean":
        return round(float(serie.mean()), 2)
    if formule == "median":
        return round(float(serie.median()), 2)

    # Formule speciale: pct_value=XXX
    if formule.startswith("pct_value="):
        target = formule.split("=", 1)[1]
        count_target = int((df[col].astype(str) == target).sum())
        return round(count_target / n_rows * 100, 1)

    return None


def _kpis_automatiques(
    df: pd.DataFrame,
    colonnes: Dict[str, List[str]],
    n_rows: int,
) -> List[Dict[str, Any]]:
    """Genere automatiquement les KPIs les plus pertinents."""
    kpis = []

    # KPI 1 — Nombre total de lignes
    kpis.append({"label": "Total enregistrements", "valeur": n_rows, "icone": "📋", "formule": "count"})

    # KPI 2 — Entites uniques principales
    entites = colonnes.get("entites", [])
    for col in entites[:3]:
        n_unique = int(df[col].nunique())
        if 2 <= n_unique <= 200:
            label = col.replace("_", " ").title()
            kpis.append({
                "label":   f"{label} distincts",
                "valeur":  n_unique,
                "icone":   "🏷️",
                "formule": "nunique",
            })

    # KPI 3 — Mesures moyennes
    for col in colonnes.get("mesures", [])[:3]:
        v = df[col].dropna()
        if len(v) > 0:
            label = col.replace("_", " ").title()
            kpis.append({
                "label":   f"{label} (moy.)",
                "valeur":  round(float(v.mean()), 2),
                "icone":   "📊",
                "formule": "mean",
            })

    return kpis[:8]


# ─── Plan de graphiques local (fallback Gemini) ───────────────────────────────

def plan_graphiques_local(
    df: pd.DataFrame,
    colonnes: Dict[str, List[str]],
) -> List[Dict[str, Any]]:
    """
    Genere un plan de graphiques pertinents sans Gemini.

    Logique:
    - Pour chaque entite avec cardinalite raisonnable → bar count
    - Pour temporelle × count → line
    - Pour mesure × entite → boxplot
    - Pour 2 entites liees → stacked bar
    - Heatmap si 2 entites avec cardinalite <= 8

    Args:
        df:       DataFrame source.
        colonnes: Colonnes classifiees.

    Returns:
        Liste de specs graphiques.
    """
    specs: List[Dict[str, Any]] = []
    entites = colonnes.get("entites", [])
    mesures = colonnes.get("mesures", [])
    temporelles = colonnes.get("temporelles", [])

    _ORDRE_NIVEAU = ["L1", "L2", "L3", "M1", "M2", "M3", "D1", "D2", "D3"]
    _ORDRE_SEMESTRE = ["S1", "S2", "S3", "S4", "S5", "S6"]

    def _ordre_col(col: str) -> Optional[List[str]]:
        """Retourne un ordre logique si la colonne le demande."""
        vals = df[col].dropna().unique().tolist()
        # Niveau d'etude
        if any(v in vals for v in ["L1", "L2", "L3", "M1", "M2"]):
            return [v for v in _ORDRE_NIVEAU if v in vals]
        # Semestre
        if any(v in vals for v in ["S1", "S2", "S3", "S4"]):
            return [v for v in _ORDRE_SEMESTRE if v in vals]
        return None

    # 1. Bar count par dimension (cardinalite <= 20)
    for col in entites:
        n_u = df[col].nunique()
        if 2 <= n_u <= 20:
            orientation = "h" if n_u > 10 else "v"
            specs.append({
                "type": "bar",
                "x": col,
                "y": "count",
                "color": None,
                "titre": f"Inscriptions par {col.replace('_', ' ').title()}",
                "orientation": orientation,
                "ordre_x": _ordre_col(col),
                "top_n": 15,
                "agg": "count",
                "justification": f"Distribution des enregistrements par {col}",
            })

    # 2. Donut pour colonnes binaires ou faible cardinalite (2-5 valeurs)
    for col in entites:
        n_u = df[col].nunique()
        if 2 <= n_u <= 5:
            # Ne pas dupliquer si deja en bar
            existing = [s for s in specs if s["x"] == col]
            if existing:
                # Remplacer le bar par donut pour les colonnes binaires
                if n_u == 2:
                    existing[0]["type"] = "donut"
                    existing[0]["orientation"] = "v"
            else:
                specs.append({
                    "type": "donut",
                    "x": col,
                    "y": "count",
                    "color": col,
                    "titre": f"Répartition par {col.replace('_', ' ').title()}",
                    "orientation": "v",
                    "ordre_x": None,
                    "top_n": None,
                    "agg": "count",
                    "justification": f"Vue d'ensemble de la distribution de {col}",
                })

    # 3. Evolution temporelle (line chart)
    for col in temporelles:
        specs.append({
            "type": "line",
            "x": col,
            "y": "count",
            "color": None,
            "titre": f"Evolution par {col.replace('_', ' ').title()}",
            "orientation": "v",
            "ordre_x": None,
            "top_n": None,
            "agg": "count",
            "justification": f"Tendance temporelle de {col}",
        })

    # 4. Stacked bar — entite1 × entite2 (cardinalite <= 6 pour la couleur)
    paires_stacked = []
    for i, col_x in enumerate(entites):
        n_x = df[col_x].nunique()
        if n_x < 2 or n_x > 15:
            continue
        for col_color in entites[i + 1:]:
            n_color = df[col_color].nunique()
            if 2 <= n_color <= 6 and col_color != col_x:
                paires_stacked.append((col_x, col_color, n_x, n_color))

    # Selectionner les 3 meilleures paires stacked
    paires_stacked.sort(key=lambda t: abs(t[2] - 5) + abs(t[3] - 3))
    for col_x, col_color, _, _ in paires_stacked[:3]:
        specs.append({
            "type": "stacked_bar",
            "x": col_x,
            "y": "count",
            "color": col_color,
            "titre": f"{col_x.replace('_', ' ').title()} par {col_color.replace('_', ' ').title()}",
            "orientation": "v",
            "ordre_x": _ordre_col(col_x),
            "top_n": None,
            "agg": "count",
            "justification": f"Croisement {col_x} × {col_color}",
        })

    # 5. Boxplot mesure × entite
    for col_y in mesures:
        for col_x in entites:
            n_u = df[col_x].nunique()
            if 2 <= n_u <= 10:
                specs.append({
                    "type": "boxplot",
                    "x": col_x,
                    "y": col_y,
                    "color": None,
                    "titre": f"{col_y.replace('_', ' ').title()} par {col_x.replace('_', ' ').title()}",
                    "orientation": "v",
                    "ordre_x": _ordre_col(col_x),
                    "top_n": None,
                    "agg": "distribution",
                    "justification": f"Distribution de {col_y} selon {col_x}",
                })
                break  # 1 boxplot par mesure

    # 6. Bar mesure × entite (moyenne)
    for col_y in mesures:
        for col_x in entites:
            n_u = df[col_x].nunique()
            if 2 <= n_u <= 20:
                # Ne pas dupliquer avec boxplot
                existing_box = [s for s in specs if s["type"] == "boxplot" and s["y"] == col_y]
                if not existing_box:
                    specs.append({
                        "type": "bar",
                        "x": col_x,
                        "y": col_y,
                        "color": None,
                        "titre": f"{col_y.replace('_', ' ').title()} moyen par {col_x.replace('_', ' ').title()}",
                        "orientation": "v" if n_u <= 10 else "h",
                        "ordre_x": _ordre_col(col_x),
                        "top_n": 15,
                        "agg": "mean",
                        "justification": f"Moyenne de {col_y} par {col_x}",
                    })
                break

    # 7. Heatmap crosstab (2 entites, cardinalite 2-8)
    entites_heatmap = [c for c in entites if 2 <= df[c].nunique() <= 8]
    if len(entites_heatmap) >= 2:
        specs.append({
            "type": "heatmap",
            "x": entites_heatmap[0],
            "y": entites_heatmap[1],
            "color": None,
            "titre": f"Heatmap — {entites_heatmap[0].replace('_', ' ').title()} × {entites_heatmap[1].replace('_', ' ').title()}",
            "orientation": "v",
            "ordre_x": _ordre_col(entites_heatmap[0]),
            "top_n": None,
            "agg": "count",
            "justification": "Matrice de contingence entre deux dimensions cles",
        })

    logger.info("[KPI] Plan local : %d graphiques generes", len(specs))
    return specs


# ─── Detection mappings ID → Libelle ──────────────────────────────────────────

def detecter_mappings_id_label(df: pd.DataFrame) -> Dict[str, str]:
    """
    Detecte automatiquement les paires (colonne_id -> colonne_libelle).

    Pour chaque colonne ID, cherche une colonne texte avec la meme
    cardinalite et un nom semantiquement proche.

    Exemples detectes :
        id_cours      -> nom_cours
        id_enseignant -> nom_Enseignants
        id_etudiant   -> nom  (ou prenom)

    Args:
        df: DataFrame source.

    Returns:
        Dict {id_col: label_col} — substitutions a appliquer dans les graphiques.
    """
    mappings: Dict[str, str] = {}

    for col in df.columns:
        col_l = col.lower().strip()

        # Detection elargie : id_cours, id_enseignant, id_etudiant, xxx_id
        is_id_col = (
            _est_id(col, df[col])
            or col_l.startswith("id_")
            or col_l.startswith("id ")
            or col_l.endswith("_id")
            or col_l.endswith(" id")
        )
        if not is_id_col:
            continue

        # Extraire la racine : id_cours -> cours, id_enseignant -> enseignant
        base = re.sub(r"^id[_\s]?", "", col_l).strip("_")
        if not base:
            continue

        n_unique_id = int(df[col].nunique())
        best: Optional[str] = None
        best_score = 0

        for cand in df.columns:
            if cand == col:
                continue
            if not _est_dtype_texte(df[cand]):
                continue

            cand_l = cand.lower()
            n_unique_cand = int(df[cand].nunique())

            # Meme cardinalite obligatoire
            if n_unique_cand != n_unique_id:
                continue

            score = 0
            if base in cand_l:
                score += 3
            if any(cand_l.startswith(p) for p in ["nom_", "libelle_", "name_", "label_", "titre_"]):
                score += 2
            if cand_l.startswith("nom") or cand_l.startswith("name"):
                score += 1
            if not _est_id(cand, df[cand]):
                score += 1

            if score > best_score:
                best_score = score
                best = cand

        if best and best_score >= 2:
            mappings[col] = best
            logger.debug("[KPI] Mapping ID : %s -> %s", col, best)

    if mappings:
        logger.info("[KPI] Mappings ID->Libelle detectes : %s", mappings)
    return mappings

