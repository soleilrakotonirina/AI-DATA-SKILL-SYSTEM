"""
backend/skills/etl_skill/core/normalizer.py  (v3)
Consolidation des valeurs textuelles dans les colonnes categorielles.

Detecte et fusionne automatiquement :
1. Variantes de casse     : paris / PARIS / Paris → Paris
2. Variantes d'accents    : Benin / Bénin → Bénin
3. Fautes de frappe       : Frnce / France → France
4. Repetitions de lettres : Madagascararr / Madagascar → Madagascar
5. Espaces parasites      : "Paris " / "Paris" → Paris
6. Lowercase pur seul     : analamanga → Analamanga (Title Case auto)

═══════════════════════════════════════════════════════════════
STRATEGIE DE CHOIX DE LA FORME CANONIQUE (v3)
═══════════════════════════════════════════════════════════════

Passe 1 — Consolidation par cle normalisee (meme mot, casse differente) :

  Priorite 1 : SCORE MAJEUR (qualite de casse)
  Priorite 2 : SOUS-SCORE (type de casse au sein du meme niveau)
  Priorite 3 : FREQUENCE
  Priorite 4 : ORDRE ALPHABETIQUE

  Tableau des scores :
  ┌─────────────────┬───────────┬────────────┬─────────────────────────┐
  │ Forme           │ Maj.      │ Sous-score │ Exemple                 │
  ├─────────────────┼───────────┼────────────┼─────────────────────────┤
  │ PascalCase      │ 4         │ 3          │ MadaExport, OceanTrade  │
  │ Acronyme UPPER  │ 4         │ 2          │ SAVA, USA, NATO         │
  │ Title long      │ 4         │ 1          │ Analamanga, Madagascar  │
  │ Title court     │ 3         │ 0          │ Sava, Lyon, Paris       │
  │ UPPER long      │ 2         │ 0          │ FRANCE, PARIS           │
  │ lowercase       │ 1         │ 0          │ paris, france           │
  │ Mixte bizarre   │ 0         │ 0          │ mAdAeXpOrT              │
  └─────────────────┴───────────┴────────────┴─────────────────────────┘

  Regles speciales :
  - Si aucune variante n'a de casse propre (score majeur >= 3) :
      Si toutes sont UPPER pur : garder UPPER (acronyme seul de la base)
      Sinon : appliquer Title Case automatique sur la plus frequente

Passe 2 — Fuzzy matching (mots differents, typographiquement proches) :

  Priorite 1 : SCORE DE CASSE (tuple)
  Priorite 2 : REGLE PREFIXE — si A est prefixe de B avec 1 a 3 chars
               de surplus, A est la forme correcte (B = repetition/addition)
               Ex. : Madagascar < Madagascararr → Madagascar gagne
                     USA < USAA → USA gagne
                     France < Francee → France gagne
  Priorite 3 : LONGUEUR — pour mots >= 5 chars, la plus longue gagne
               (suppose une lettre oubliee, ex. Frnce → France)
  Priorite 4 : FREQUENCE
═══════════════════════════════════════════════════════════════

Fonction principale : consolidate_categorical_values
"""

from __future__ import annotations

import logging
import unicodedata
from difflib import SequenceMatcher
from typing import Any

import pandas as pd

from skills.etl_skill.core.cleaner import is_protected_column

logger = logging.getLogger(__name__)

# Constantes
DEFAULT_SIMILARITY_THRESHOLD: float = 0.85
DEFAULT_MAX_CARDINALITY: int = 100
DEFAULT_MAX_LENGTH_DIFF: int = 3
DEFAULT_MIN_VALUE_LENGTH: int = 2
DEFAULT_ACRONYM_MAX_LENGTH: int = 4   # USA, NATO, SAVA, FIFA etc.
DEFAULT_PREFIX_SURPLUS_MAX: int = 3   # nb max de chars en surplus pour regle prefixe


# ── Normalisation ─────────────────────────────────────────────────────────────

def _normalize_for_compare(s: str) -> str:
    """Lowercase + sans accents + strip."""
    s = str(s).strip().lower()
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _auto_titlecase(s: str) -> str:
    """
    Title Case intelligent.

    - Chaine courte alphabetique (<= 3 chars) : UPPER (acronyme probable)
    - Sinon : Title Case standard
    """
    s = str(s).strip()
    if not s:
        return s
    if len(s) <= 3 and s.isalpha():
        return s.upper()
    return s.title()


# ── Scoring de casse ──────────────────────────────────────────────────────────

def _case_score_tuple(s: str) -> tuple[int, int]:
    """
    Retourne (score_majeur, sous_score) pour le tri fin.

    Voir tableau dans la docstring du module.
    """
    if not s:
        return (0, 0)

    # Acronyme court UPPER (USA, NATO, SAVA, FIFA)
    if len(s) <= DEFAULT_ACRONYM_MAX_LENGTH and s.isupper() and s.isalpha():
        return (4, 2)

    # PascalCase / CamelCase : majuscule debut + majuscule milieu + minuscule
    if (
        len(s) > 1
        and s[0].isupper()
        and any(c.isupper() for c in s[1:])
        and any(c.islower() for c in s)
    ):
        return (4, 3)

    # Title case
    if s.istitle():
        return (4, 1) if len(s) > 5 else (3, 0)

    # UPPER long (FRANCE, PARIS)
    if s.isupper():
        return (2, 0)

    # lowercase
    if s.islower():
        return (1, 0)

    # casse mixte non standard
    return (0, 0)


def _case_score(s: str) -> int:
    """Score majeur uniquement (retrocompatibilite)."""
    return _case_score_tuple(s)[0]


# ── Choix de la forme canonique ───────────────────────────────────────────────

def _choose_canonical(
    variants: list[str],
    frequencies: dict[str, int],
) -> str:
    """
    Choisit la forme canonique parmi des variantes de meme cle normalisee.

    Algorithme :
    1. Si au moins une variante a un score majeur >= 3 (casse propre) :
       trier par (-score_majeur, -sous_score, -freq, alpha)
       et prendre le premier.
    2. Si toutes les variantes sont en UPPER pur (peu importe longueur) :
       garder UPPER (acronyme saisi intentionnellement, ex. BRICS, NASDAQ).
    3. Sinon : Title Case automatique sur la valeur la plus frequente.

    Args:
        variants    : Variantes groupees par cle normalisee.
        frequencies : Frequences brutes {variante: count}.

    Returns:
        Forme canonique (peut etre generee par _auto_titlecase).
    """
    scored = [(v, _case_score_tuple(v), frequencies.get(v, 0)) for v in variants]

    # Cas 1 : au moins une variante bien casee
    well_cased = [(v, t, f) for v, t, f in scored if t[0] >= 3]
    if well_cased:
        well_cased.sort(key=lambda x: (-x[1][0], -x[1][1], -x[2], x[0]))
        return well_cased[0][0]

    # Cas 2 : toutes en UPPER pur (acronyme volontaire de n'importe quelle longueur)
    all_upper = all(v.isupper() and v.isalpha() for v, _, _ in scored)
    if all_upper:
        scored.sort(key=lambda x: (-x[2], x[0]))
        return scored[0][0]

    # Cas 3 : Title Case automatique sur la plus frequente
    scored.sort(key=lambda x: (-x[2], x[0]))
    return _auto_titlecase(scored[0][0])


def _choose_fuzzy_canonical(
    val_a: str,
    val_b: str,
    freq_a: int,
    freq_b: int,
) -> tuple[str, str]:
    """
    Choisit la forme canonique entre deux variantes fuzzy-similaires.

    Regles dans l'ordre :
    1. Score de casse (tuple) : la casse la plus specifique gagne.
    2. Regle prefixe : si A est prefixe strict de B avec 1 a N chars
       de surplus, A est la forme correcte (B = lettre(s) ajoutee(s) par erreur).
       Exemples : Madagascar < Madagascararr (3 surplus) → Madagascar
                  USA < USAA (1 surplus) → USA
                  France < Francee (1 surplus) → France
    3. Longueur : pour mots >= 5 chars, la plus longue gagne
       (suppose lettre omise dans la forme courte, ex. Frnce → France).
    4. Frequence : en dernier recours.

    Returns:
        (canonical, other) ou canonical est la forme retenue.
    """
    t_a = _case_score_tuple(val_a)
    t_b = _case_score_tuple(val_b)

    # Regle 1 : score de casse
    if t_a > t_b:
        return val_a, val_b
    if t_b > t_a:
        return val_b, val_a

    # Regle 2 : prefixe (addition de lettres = typo)
    a_l = _normalize_for_compare(val_a)
    b_l = _normalize_for_compare(val_b)
    if a_l != b_l:
        diff_a_to_b = len(b_l) - len(a_l)
        diff_b_to_a = len(a_l) - len(b_l)
        if b_l.startswith(a_l) and 1 <= diff_a_to_b <= DEFAULT_PREFIX_SURPLUS_MAX:
            return val_a, val_b    # val_a est le prefixe → forme correcte
        if a_l.startswith(b_l) and 1 <= diff_b_to_a <= DEFAULT_PREFIX_SURPLUS_MAX:
            return val_b, val_a    # val_b est le prefixe → forme correcte

    # Regle 3 : longueur (lettre oubliee dans la forme courte)
    if max(len(val_a), len(val_b)) >= 5:
        if len(val_a) > len(val_b):
            return val_a, val_b
        if len(val_b) > len(val_a):
            return val_b, val_a

    # Regle 4 : frequence
    if freq_a >= freq_b:
        return val_a, val_b
    return val_b, val_a


# ── Fonction principale ───────────────────────────────────────────────────────

def consolidate_categorical_values(
    df: pd.DataFrame,
    columns: list[str] | None = None,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    max_cardinality: int = DEFAULT_MAX_CARDINALITY,
    enable_fuzzy: bool = True,
    auto_titlecase_isolated: bool = False,
) -> tuple[pd.DataFrame, dict[str, dict[str, Any]]]:
    """
    Consolide les variantes textuelles dans les colonnes categorielles.

    Effectue deux passes :

    Passe 1 — Consolidation par cle normalisee.
    Regroupe les variantes qui correspondent au meme mot (meme cle
    lowercase + sans accents + strip). Exemple : Paris / paris / PARIS
    sont un seul groupe. Choisit la forme canonique via _choose_canonical.

    Passe 2 — Fuzzy matching.
    Compare chaque paire de valeurs consolidees via SequenceMatcher.ratio().
    Si ratio >= similarity_threshold et longueur comparable, fusionne
    via _choose_fuzzy_canonical.

    Args:
        df                      : DataFrame a consolider.
        columns                 : Colonnes a traiter. None = auto-detection
                                  (colonnes texte, cardinalite raisonnable,
                                  non protegees).
        similarity_threshold    : Seuil fuzzy (defaut 0.85).
        max_cardinality         : Cardinalite max pour traiter une colonne.
        enable_fuzzy            : Activer la detection de fautes de frappe.
        auto_titlecase_isolated : Si True, applique Title Case aux valeurs
                                  sans variante dans la passe 1.
                                  Ex. : "analamanga" seul → "Analamanga".
                                  False par defaut (plus conservateur).

    Returns:
        Tuple (df_consolide, rapport) :
        {
          "colonne": {
            "n_replacements": int,
            "n_values_before": int,
            "n_values_after": int,
            "details": [
              {"from": str, "to": str, "type": "case"|"fuzzy", "count": int}
            ]
          }
        }
    """
    df_out = df.copy()
    rapport: dict[str, dict[str, Any]] = {}

    # Auto-detection des colonnes
    if columns is None:
        columns = []
        for c in df_out.columns:
            is_text = (
                df_out[c].dtype == object
                or pd.api.types.is_string_dtype(df_out[c])
            )
            if not is_text:
                continue
            n_unique = df_out[c].nunique()
            if n_unique <= 1 or n_unique > max_cardinality:
                continue
            if is_protected_column(c, df_out[c]):
                continue
            columns.append(c)

    if not columns:
        return df_out, rapport

    logger.info(
        "[Consolidation] Analyse de %d colonne(s) : %s",
        len(columns), columns,
    )

    for col in columns:
        if col not in df_out.columns:
            continue

        # Frequences brutes
        value_counts = (
            df_out[col].dropna().astype(str).str.strip().value_counts()
        )
        if len(value_counts) == 0:
            continue

        # Filtrer les valeurs trop courtes
        value_counts = value_counts[
            value_counts.index.to_series().str.len() >= DEFAULT_MIN_VALUE_LENGTH
        ]
        if len(value_counts) == 0:
            continue

        frequencies: dict[str, int] = value_counts.to_dict()
        replacements: dict[str, str] = {}

        # ── Passe 1 : Consolidation par cle normalisee ───────────────────────
        groups: dict[str, list[str]] = {}
        for value in value_counts.index:
            key = _normalize_for_compare(value)
            groups.setdefault(key, []).append(value)

        for _key, variants in groups.items():
            if len(variants) > 1:
                canonical = _choose_canonical(variants, frequencies)
                for v in variants:
                    if v != canonical:
                        replacements[v] = canonical
            elif auto_titlecase_isolated:
                # Valeur seule sans variante : Title Case si score <= 1
                v = variants[0]
                if _case_score(v) <= 1:
                    # Garder les acronymes courts UPPER
                    if v.isupper() and v.isalpha() and len(v) <= DEFAULT_ACRONYM_MAX_LENGTH:
                        continue
                    new_val = _auto_titlecase(v)
                    if new_val != v:
                        replacements[v] = new_val

        # ── Passe 2 : Fuzzy matching ─────────────────────────────────────────
        if enable_fuzzy and len(value_counts) > 1:
            # Frequences apres passe 1
            consolidated_freq: dict[str, int] = {}
            for orig, count in frequencies.items():
                target = replacements.get(orig, orig)
                consolidated_freq[target] = (
                    consolidated_freq.get(target, 0) + count
                )

            consolidated_values = list(consolidated_freq.keys())
            fuzzy_done: set[str] = set()

            for i, val_a in enumerate(consolidated_values):
                if val_a in fuzzy_done:
                    continue
                for val_b in consolidated_values[i + 1:]:
                    if val_b in fuzzy_done:
                        continue
                    # Ecart de longueur trop grand
                    if abs(len(val_a) - len(val_b)) > DEFAULT_MAX_LENGTH_DIFF:
                        continue
                    # Calcul du ratio sur valeurs normalisees
                    ratio = SequenceMatcher(
                        None,
                        _normalize_for_compare(val_a),
                        _normalize_for_compare(val_b),
                    ).ratio()
                    if ratio < similarity_threshold:
                        continue
                    # Choisir la forme canonique
                    canonical, other = _choose_fuzzy_canonical(
                        val_a, val_b,
                        consolidated_freq[val_a],
                        consolidated_freq[val_b],
                    )
                    # Propager aux valeurs originales pointant vers other
                    for orig, target in list(replacements.items()):
                        if target == other:
                            replacements[orig] = canonical
                    if other not in replacements:
                        replacements[other] = canonical
                    fuzzy_done.add(other)
                    logger.info(
                        "[Consolidation] Fuzzy '%s' (%dx) ↔ '%s' (%dx) "
                        "ratio=%.2f → %s",
                        val_a, consolidated_freq[val_a],
                        val_b, consolidated_freq[val_b],
                        ratio, canonical,
                    )
                    break

        # ── Application des remplacements ─────────────────────────────────────
        if replacements:
            mask = df_out[col].notna()
            df_out.loc[mask, col] = (
                df_out.loc[mask, col]
                .astype(str)
                .str.strip()
                .map(lambda v: replacements.get(v, v))
            )

            n_before = len(value_counts)
            n_after = int(df_out[col].nunique())

            details: list[dict[str, Any]] = []
            for src, dst in replacements.items():
                rep_type = (
                    "case"
                    if _normalize_for_compare(src) == _normalize_for_compare(dst)
                    else "fuzzy"
                )
                details.append({
                    "from": src,
                    "to": dst,
                    "type": rep_type,
                    "count": int(frequencies.get(src, 0)),
                })

            rapport[col] = {
                "n_replacements": len(replacements),
                "n_values_before": n_before,
                "n_values_after": n_after,
                "details": details,
            }

            logger.info(
                "[Consolidation] '%s' : %d valeurs → %d (%d remplacements)",
                col, n_before, n_after, len(replacements),
            )
            for src, dst in list(replacements.items())[:5]:
                logger.info("  '%s' → '%s'", src, dst)

    if rapport:
        total = sum(r["n_replacements"] for r in rapport.values())
        logger.info(
            "[Consolidation] Total : %d remplacements, %d colonne(s) normalisee(s)",
            total, len(rapport),
        )
    else:
        logger.info("[Consolidation] Aucune normalisation necessaire.")

    return df_out, rapport