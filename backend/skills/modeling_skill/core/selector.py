"""
backend/skills/modeling_skill/core/selector.py
Selection automatique des algorithmes ML via Gemini.

Detection du type de probleme, recommandation Gemini,
construction des configs sklearn.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


def detect_problem_type(
    df: pd.DataFrame,
    target_column: str,
) -> Dict[str, Any]:
    """
    Detecte automatiquement le type de probleme ML.

    Args:
        df:            DataFrame source.
        target_column: Nom de la colonne cible.

    Returns:
        {"problem_type", "n_classes", "target_distribution"}
    """
    if target_column not in df.columns:
        logger.info("[Selector] target_column absent → clustering")
        return {"problem_type": "clustering", "n_classes": None, "target_distribution": {}}

    series   = df[target_column].dropna()
    n_unique = int(series.nunique())
    vc       = series.value_counts()
    target_distribution = {str(k): int(v) for k, v in vc.head(20).items()}

    if pd.api.types.is_numeric_dtype(series) and n_unique > 20:
        problem_type = "regression"
        n_classes    = None
    elif n_unique == 2:
        problem_type = "binary_classification"
        n_classes    = 2
    elif n_unique <= 20:
        problem_type = "multiclass_classification"
        n_classes    = n_unique
    else:
        problem_type = "regression"
        n_classes    = None

    logger.info(
        "[Selector] Probleme detecte : %s (n_classes=%s, n_unique=%d)",
        problem_type, n_classes, n_unique,
    )
    return {"problem_type": problem_type, "n_classes": n_classes,
            "target_distribution": target_distribution}


_PROMPT_RECOMMENDATION = """Tu es un expert en Machine Learning.

Dataset :
- Lignes         : {n_rows}
- Features       : {n_features}
- Type probleme  : {problem_type}
- Distribution cible : {target_distribution}

Recommande 2 ou 3 algorithmes sklearn/xgboost/lightgbm adaptes a ce probleme.
Reponds UNIQUEMENT en JSON valide (pas de markdown) :
[
  {{
    "algorithm": "NomClasseExact",
    "justification": "Pourquoi cet algorithme est adapte en 1 phrase",
    "initial_params": {{"param1": valeur1, "param2": valeur2}}
  }}
]

Algorithmes supportes :
- Classification : RandomForestClassifier, XGBClassifier, LGBMClassifier,
                   LogisticRegression, SVC
- Regression     : RandomForestRegressor, XGBRegressor, LGBMRegressor,
                   Ridge, Lasso, LinearRegression
- Clustering     : KMeans, DBSCAN"""


def get_gemini_model_recommendation(
    problem_type: str,
    dataset_info: Dict[str, Any],
    api_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Recommande des algorithmes via Gemini selon le type de probleme.

    Args:
        problem_type:  Type de probleme ML.
        dataset_info:  {n_rows, n_features, target_distribution}.
        api_key:       Non utilise — rotation via gemini_client.

    Returns:
        [{"algorithm", "justification", "initial_params"}]
    """
    try:
        from src.utils.gemini_client import generate_content

        prompt = _PROMPT_RECOMMENDATION.format(
            n_rows              = dataset_info.get("n_rows", "?"),
            n_features          = dataset_info.get("n_features", "?"),
            problem_type        = problem_type,
            target_distribution = json.dumps(
                dataset_info.get("target_distribution", {}), ensure_ascii=False
            )[:200],
        )

        text = generate_content(prompt, temperature=0.1)
        if not text:
            raise ValueError("Gemini n'a pas repondu")

        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text  = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        recommendations = json.loads(text)
        if not isinstance(recommendations, list) or len(recommendations) == 0:
            raise ValueError("Format Gemini invalide")

        logger.info("[Selector] Gemini recommande : %s",
                    [r.get("algorithm") for r in recommendations])
        return recommendations

    except Exception as exc:
        logger.warning("[Selector] Gemini echoue (%s) — fallback local", exc)
        return _fallback_recommendations(problem_type)


def _fallback_recommendations(problem_type: str) -> List[Dict[str, Any]]:
    """Retourne des recommendations locales si Gemini est indisponible."""
    fallbacks: Dict[str, List[Dict[str, Any]]] = {
        "binary_classification": [
            {"algorithm": "RandomForestClassifier",
             "justification": "Robuste, peu de tuning requis",
             "initial_params": {"n_estimators": 100, "max_depth": 10, "random_state": 42}},
            {"algorithm": "LogisticRegression",
             "justification": "Rapide, interpretable, bon baseline",
             "initial_params": {"max_iter": 1000, "random_state": 42}},
        ],
        "multiclass_classification": [
            {"algorithm": "RandomForestClassifier",
             "justification": "Excellent pour multiclasse",
             "initial_params": {"n_estimators": 100, "max_depth": 10, "random_state": 42}},
            {"algorithm": "LogisticRegression",
             "justification": "Baseline solide pour multiclasse",
             "initial_params": {"max_iter": 1000, "multi_class": "auto", "random_state": 42}},
        ],
        "regression": [
            {"algorithm": "RandomForestRegressor",
             "justification": "Robuste et performant pour la regression",
             "initial_params": {"n_estimators": 100, "max_depth": 10, "random_state": 42}},
            {"algorithm": "Ridge",
             "justification": "Regression lineaire regularisee",
             "initial_params": {"alpha": 1.0}},
        ],
        "clustering": [
            {"algorithm": "KMeans",
             "justification": "Clustering partitionnel rapide",
             "initial_params": {"n_clusters": 5, "random_state": 42, "n_init": 10}},
        ],
    }
    result = fallbacks.get(problem_type, fallbacks["binary_classification"])
    logger.info("[Selector] Fallback local : %s", [r["algorithm"] for r in result])
    return result


def build_algorithm_configs(
    recommendations: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Construit les configurations sklearn depuis les recommandations Gemini.

    Args:
        recommendations: Liste de dicts depuis get_gemini_model_recommendation.

    Returns:
        [{"name", "estimator", "param_grid"}]
    """
    configs: List[Dict[str, Any]] = []

    for rec in recommendations:
        algo_name      = rec.get("algorithm", "")
        initial_params = rec.get("initial_params", {})

        estimator = _instanciate_estimator(algo_name, initial_params)
        if estimator is None:
            logger.warning("[Selector] Algorithme non supporte : %s", algo_name)
            continue

        param_grid = _get_param_grid(algo_name)
        configs.append({"name": algo_name, "estimator": estimator, "param_grid": param_grid})
        logger.debug("[Selector] Config construite : %s", algo_name)

    logger.info("[Selector] %d configs construites", len(configs))
    return configs


def _instanciate_estimator(name: str, params: Dict[str, Any]) -> Any:
    """Instancie un estimateur sklearn par son nom."""
    safe_params = {
        k: v for k, v in params.items()
        if isinstance(v, (int, float, str, bool, type(None)))
    }

    try:
        if name == "RandomForestClassifier":
            from sklearn.ensemble import RandomForestClassifier
            return RandomForestClassifier(**safe_params)
        if name == "XGBClassifier":
            from xgboost import XGBClassifier
            safe_params.setdefault("eval_metric", "logloss")
            safe_params.pop("use_label_encoder", None)  # deprecie depuis XGBoost 1.6
            return XGBClassifier(**safe_params)
        if name == "LGBMClassifier":
            from lightgbm import LGBMClassifier
            safe_params.setdefault("verbose", -1)
            return LGBMClassifier(**safe_params)
        if name == "LogisticRegression":
            from sklearn.linear_model import LogisticRegression
            safe_params.setdefault("max_iter", 1000)
            return LogisticRegression(**safe_params)
        if name == "SVC":
            from sklearn.svm import SVC
            safe_params.setdefault("probability", True)
            return SVC(**safe_params)
        if name == "RandomForestRegressor":
            from sklearn.ensemble import RandomForestRegressor
            return RandomForestRegressor(**safe_params)
        if name == "XGBRegressor":
            from xgboost import XGBRegressor
            safe_params.pop("use_label_encoder", None)
            return XGBRegressor(**safe_params)
        if name == "LGBMRegressor":
            from lightgbm import LGBMRegressor
            safe_params.setdefault("verbose", -1)
            return LGBMRegressor(**safe_params)
        if name == "LinearRegression":
            from sklearn.linear_model import LinearRegression
            return LinearRegression()
        if name == "Ridge":
            from sklearn.linear_model import Ridge
            return Ridge(**safe_params)
        if name == "Lasso":
            from sklearn.linear_model import Lasso
            return Lasso(**safe_params)
        if name == "KMeans":
            from sklearn.cluster import KMeans
            safe_params.setdefault("n_init", 10)
            return KMeans(**safe_params)
        if name == "DBSCAN":
            from sklearn.cluster import DBSCAN
            return DBSCAN(**safe_params)
    except ImportError as exc:
        logger.warning("[Selector] Import echoue pour %s : %s", name, exc)
        return None
    except Exception as exc:
        logger.warning("[Selector] Instantiation echouee pour %s : %s", name, exc)
        return None

    return None


def _get_param_grid(name: str) -> Dict[str, List[Any]]:
    """Retourne la grille d'hyperparametres pour RandomizedSearchCV."""
    grids: Dict[str, Any] = {
        "RandomForestClassifier": {
            "n_estimators": [50, 100, 200],
            "max_depth":    [5, 10, 20, None],
            "min_samples_split": [2, 5, 10],
            "min_samples_leaf":  [1, 2, 4],
        },
        "RandomForestRegressor": {
            "n_estimators": [50, 100, 200],
            "max_depth":    [5, 10, 20, None],
            "min_samples_split": [2, 5, 10],
        },
        "XGBClassifier": {
            "n_estimators":  [50, 100, 200],
            "max_depth":     [3, 6, 10],
            "learning_rate": [0.01, 0.1, 0.3],
            "subsample":     [0.7, 0.8, 1.0],
        },
        "XGBRegressor": {
            "n_estimators":  [50, 100, 200],
            "max_depth":     [3, 6, 10],
            "learning_rate": [0.01, 0.1, 0.3],
        },
        "LGBMClassifier": {
            "n_estimators":  [50, 100, 200],
            "num_leaves":    [31, 63, 127],
            "learning_rate": [0.01, 0.1, 0.3],
        },
        "LGBMRegressor": {
            "n_estimators":  [50, 100, 200],
            "num_leaves":    [31, 63, 127],
            "learning_rate": [0.01, 0.1, 0.3],
        },
        "LogisticRegression": {
            "C":      [0.01, 0.1, 1.0, 10.0],
            "solver": ["lbfgs", "liblinear"],
        },
        "Ridge":  {"alpha": [0.01, 0.1, 1.0, 10.0, 100.0]},
        "Lasso":  {"alpha": [0.001, 0.01, 0.1, 1.0, 10.0]},
        "SVC": {
            "C":      [0.1, 1.0, 10.0],
            "kernel": ["rbf", "linear"],
            "gamma":  ["scale", "auto"],
        },
        "KMeans": {
            "n_clusters": [3, 4, 5, 6, 7, 8],
            "init":       ["k-means++", "random"],
        },
    }
    return grids.get(name, {})