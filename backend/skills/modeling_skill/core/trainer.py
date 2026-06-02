"""
backend/skills/modeling_skill/core/trainer.py
Pipeline sklearn : preprocessing, entrainement, tuning, sauvegarde.

Correctifs appliques :
- LabelEncoder XGBoost utilise numpy dtype.kind (pas dtype==object fragile)
- class_weight non applique sur XGBoost/LightGBM (non supporte)
- Decode y_pred via inverse_transform apres predict XGBoost
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import cross_val_score, RandomizedSearchCV
from sklearn.pipeline import Pipeline

logger = logging.getLogger(__name__)


def build_preprocessing_pipeline(
    df: pd.DataFrame,
    target_column: str,
    encoders: Optional[Dict[str, Any]] = None,
    scalers: Optional[Dict[str, Any]] = None,
) -> Tuple[Any, List[str]]:
    """
    Construit un pipeline sklearn de preprocessing.

    Colonnes numeriques   : SimpleImputer(median) + StandardScaler
    Colonnes categorielles: SimpleImputer(most_frequent) + OneHotEncoder

    Args:
        df:            DataFrame source (hors split train/test).
        target_column: Nom de la colonne cible (a exclure).
        encoders:      Encodeurs ETL Skill optionnels.
        scalers:       Scalers ETL Skill optionnels.

    Returns:
        (preprocessor, feature_names_in)
    """
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import StandardScaler, OneHotEncoder

    X = df.drop(columns=[target_column], errors="ignore")
    feature_names_in = X.columns.tolist()

    numeric_cols     = X.select_dtypes(include="number").columns.tolist()
    categorical_cols = X.select_dtypes(exclude="number").columns.tolist()

    transformers = []

    if numeric_cols:
        numeric_pipeline = Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler",  StandardScaler()),
        ])
        transformers.append(("num", numeric_pipeline, numeric_cols))

    if categorical_cols:
        categorical_pipeline = Pipeline([
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("encoder", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ])
        transformers.append(("cat", categorical_pipeline, categorical_cols))

    if not transformers:
        logger.warning("[Trainer] Aucune colonne utilisable pour le preprocessing")
        from sklearn.preprocessing import FunctionTransformer
        preprocessor = FunctionTransformer()
    else:
        preprocessor = ColumnTransformer(transformers=transformers, remainder="drop")

    logger.info(
        "[Trainer] Preprocessor : %d num., %d cat.",
        len(numeric_cols), len(categorical_cols),
    )
    return preprocessor, feature_names_in


def train_and_evaluate_models(
    X_train: pd.DataFrame,
    X_test: pd.DataFrame,
    y_train: pd.Series,
    y_test: pd.Series,
    configs: List[Dict[str, Any]],
    problem_type: str,
    cv: int = 5,
    class_weight_method: bool = False,
) -> List[Dict[str, Any]]:
    """
    Entraine et evalue tous les algorithmes de la liste configs.

    Gestion XGBoost :
    - Labels string encodes en int via LabelEncoder (numpy dtype.kind)
    - y_pred decode via inverse_transform pour les metriques
    - class_weight non applique sur XGBoost/LightGBM (non supporte)

    Args:
        X_train:             Features d'entrainement.
        X_test:              Features de test.
        y_train:             Labels d'entrainement.
        y_test:              Labels de test.
        configs:             Configs depuis build_algorithm_configs.
        problem_type:        Type de probleme ML.
        cv:                  Nombre de folds cross-validation.
        class_weight_method: Si True, appliquer class_weight='balanced' si supporte.

    Returns:
        [{"model_name", "metrics", "cv_scores", "trained_model", "duration_s"}]
    """
    from skills.modeling_skill.core.evaluator import (
        compute_classification_metrics,
        compute_regression_metrics,
    )

    scoring_map = {
        "binary_classification":    "roc_auc",
        "multiclass_classification": "f1_weighted",
        "regression":               "r2",
        "clustering":               None,
    }
    cv_scoring = scoring_map.get(problem_type, "f1_weighted")

    results: List[Dict[str, Any]] = []

    for config in configs:
        model_name = config["name"]
        estimator  = config["estimator"]
        t0         = time.monotonic()

        logger.info("[Trainer] Entrainement : %s ...", model_name)

        try:
            # Ajouter class_weight si applicable
            # XGBoost et LightGBM ne supportent pas class_weight via set_params
            _supports_cw = (
                class_weight_method
                and hasattr(estimator, "class_weight")
                and "XGB" not in model_name
                and "LGBM" not in model_name
            )
            if _supports_cw:
                try:
                    estimator.set_params(class_weight="balanced")
                except Exception:
                    pass

            # Encoder les labels string pour XGBoost (requiert int)
            from sklearn.preprocessing import LabelEncoder as _LE
            _label_encoder = None
            _y_train = y_train
            _y_test  = y_test
            _is_xgb  = "XGB" in model_name or "xgb" in model_name.lower()

            if _is_xgb:
                # numpy kind : i=int, u=uint, f=float → numerique OK
                # Tout autre kind (U=str, O=object, S=bytes) → encoder
                _y_arr = np.asarray(y_train)
                if _y_arr.dtype.kind not in ("i", "u", "f"):
                    _label_encoder = _LE()
                    _y_train = _label_encoder.fit_transform(y_train)
                    _y_test  = _label_encoder.transform(y_test)
                    logger.info(
                        "[Trainer] Labels encodes pour XGBoost : %s",
                        list(_label_encoder.classes_),
                    )

            # Cross-validation — utiliser _y_train (encode si XGBoost)
            cv_scores_arr: Optional[np.ndarray] = None
            if problem_type != "clustering" and cv_scoring:
                try:
                    cv_scores_arr = cross_val_score(
                        estimator,
                        X_train,
                        _y_train,
                        cv=cv,
                        scoring=cv_scoring,
                        n_jobs=-1,
                    )
                except Exception as exc:
                    logger.warning("[Trainer] CV echouee pour %s : %s", model_name, exc)
                    cv_scores_arr = None

            # Entrainement final sur tout le train set
            estimator.fit(X_train, _y_train)
            y_pred_raw = estimator.predict(X_test)

            # Decoder les labels XGBoost si necessaire
            if _label_encoder is not None:
                try:
                    y_pred = _label_encoder.inverse_transform(y_pred_raw.astype(int))
                except Exception:
                    y_pred = y_pred_raw
            else:
                y_pred = y_pred_raw

            # Metriques — utiliser y_test original (labels lisibles)
            if problem_type in ("binary_classification", "multiclass_classification"):
                y_proba = None
                if hasattr(estimator, "predict_proba"):
                    try:
                        y_proba = estimator.predict_proba(X_test)
                        if problem_type == "binary_classification":
                            y_proba = y_proba[:, 1]
                    except Exception:
                        pass
                metrics = compute_classification_metrics(y_test, y_pred, y_proba)

            elif problem_type == "regression":
                metrics = compute_regression_metrics(y_test, y_pred)

            elif problem_type == "clustering":
                metrics = _compute_clustering_metrics(estimator, X_train)
            else:
                metrics = {}

            duration = round(time.monotonic() - t0, 2)

            cv_summary = {}
            if cv_scores_arr is not None:
                cv_summary = {
                    "mean":   round(float(cv_scores_arr.mean()), 4),
                    "std":    round(float(cv_scores_arr.std()), 4),
                    "scores": [round(float(s), 4) for s in cv_scores_arr],
                }

            results.append({
                "model_name":    model_name,
                "metrics":       metrics,
                "cv_scores":     cv_summary,
                "trained_model": estimator,
                "duration_s":    duration,
            })

            primary = list(metrics.values())[0] if metrics else "?"
            logger.info(
                "[Trainer] %s — %.4g (%s) — %.2fs",
                model_name,
                primary if isinstance(primary, (int, float)) else "?",
                list(metrics.keys())[0] if metrics else "?",
                duration,
            )

        except Exception as exc:
            logger.error("[Trainer] Erreur entrainement %s : %s", model_name, exc)
            results.append({
                "model_name":    model_name,
                "metrics":       {},
                "cv_scores":     {},
                "trained_model": None,
                "duration_s":    round(time.monotonic() - t0, 2),
                "error":         str(exc),
            })

    return results


def _compute_clustering_metrics(estimator: Any, X: pd.DataFrame) -> Dict[str, float]:
    """Calcule les metriques de clustering."""
    metrics: Dict[str, float] = {}
    try:
        labels = estimator.labels_
        if hasattr(estimator, "inertia_"):
            metrics["inertia"] = round(float(estimator.inertia_), 4)
        if len(set(labels)) > 1:
            from sklearn.metrics import silhouette_score
            score = silhouette_score(X, labels, sample_size=min(5000, len(X)))
            metrics["silhouette_score"] = round(float(score), 4)
    except Exception as exc:
        logger.warning("[Trainer] Metriques clustering echouees : %s", exc)
    return metrics


def tune_best_model(
    best_config: Dict[str, Any],
    X_train: pd.DataFrame,
    y_train: pd.Series,
    cv: int = 5,
    n_iter: int = 20,
    problem_type: str = "binary_classification",
) -> Tuple[Any, Dict[str, Any], float]:
    """
    Optimise les hyperparametres avec RandomizedSearchCV.

    Args:
        best_config:  Config du meilleur modele.
        X_train:      Features d'entrainement.
        y_train:      Labels d'entrainement.
        cv:           Nombre de folds.
        n_iter:       Iterations RandomizedSearchCV.
        problem_type: Type de probleme ML.

    Returns:
        (best_estimator, best_params, best_score)
    """
    scoring_map = {
        "binary_classification":    "roc_auc",
        "multiclass_classification": "f1_weighted",
        "regression":               "r2",
        "clustering":               None,
    }
    scoring    = scoring_map.get(problem_type, "f1_weighted")
    model_name = best_config["name"]
    estimator  = best_config["estimator"]
    param_grid = best_config.get("param_grid", {})

    if not param_grid or problem_type == "clustering":
        logger.info("[Trainer] Tuning ignore (grille vide ou clustering) : %s", model_name)
        return estimator, {}, 0.0

    logger.info("[Trainer] Tuning RandomizedSearchCV : %s (%d iter, cv=%d)", model_name, n_iter, cv)
    t0 = time.monotonic()

    # Encoder y pour XGBoost si necessaire
    _y_train = y_train
    _label_encoder = None
    if "XGB" in model_name:
        _y_arr = np.asarray(y_train)
        if _y_arr.dtype.kind not in ("i", "u", "f"):
            from sklearn.preprocessing import LabelEncoder as _LE
            _label_encoder = _LE()
            _y_train = _label_encoder.fit_transform(y_train)

    try:
        search = RandomizedSearchCV(
            estimator           = estimator,
            param_distributions = param_grid,
            n_iter              = n_iter,
            cv                  = cv,
            scoring             = scoring,
            random_state        = 42,
            n_jobs              = -1,
            refit               = True,
        )
        search.fit(X_train, _y_train)

        best_params = search.best_params_
        best_score  = round(float(search.best_score_), 4)
        best_est    = search.best_estimator_

        logger.info(
            "[Trainer] Tuning termine en %.2fs — score=%.4f — params=%s",
            time.monotonic() - t0, best_score, best_params,
        )
        return best_est, best_params, best_score

    except Exception as exc:
        logger.warning("[Trainer] Tuning echoue pour %s : %s — modele non-tune", model_name, exc)
        estimator.fit(X_train, _y_train)
        return estimator, {}, 0.0


def save_full_pipeline(
    preprocessor: Any,
    model: Any,
    model_name: str,
    metrics: Dict[str, Any],
    output_dir: str,
) -> str:
    """
    Construit et sauvegarde le pipeline complet avec joblib.

    Nomenclature : {model_name}_{YYYYMMDD}_{v1}.pkl

    Args:
        preprocessor: ColumnTransformer sklearn.
        model:        Estimateur entraine.
        model_name:   Nom de l'algorithme.
        metrics:      Metriques du modele.
        output_dir:   Dossier de sauvegarde.

    Returns:
        Chemin du fichier .pkl genere.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    date_str  = datetime.now().strftime("%Y%m%d")
    file_name = f"{model_name}_{date_str}_v1.pkl"
    file_path = Path(output_dir) / file_name

    full_pipeline = Pipeline([
        ("preprocessor", preprocessor),
        ("model",        model),
    ])

    joblib.dump(
        {
            "pipeline":   full_pipeline,
            "model_name": model_name,
            "metrics":    metrics,
            "saved_at":   datetime.now().isoformat(),
        },
        str(file_path),
        compress=3,
    )

    logger.info("[Trainer] Pipeline sauvegarde : %s", file_path)
    return str(file_path)