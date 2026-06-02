# AI DATA SKILL SYSTEM — Étape 3 : Modeling Skill

## Objectif

**Entraîner un modèle ML sur le dataset propre, l'évaluer et le sauvegarder.**

```
Étape 1 (ETL)           → dataset brut     → dataset propre
Étape 2 (Visualization) → dataset propre   → graphiques + KPIs
Étape 3 (Modeling)      → dataset propre   → modèle .pkl + métriques + Model Card
```

L'utilisateur indique une **colonne cible** (ex: `statut`, `churn`, `prix`).
Le système entraîne automatiquement plusieurs algorithmes, compare les résultats
et retourne le meilleur pipeline prêt à faire des prédictions.

---

## Ce que produit cette étape

```
backend/
│
├── models/
│   └── XGBClassifier_20260525_v1.pkl        ← pipeline complet rechargeable
│
└── outputs/
    └── model_cards/
        └── Donnees_Universitaires/
            └── Donnees_Universitaires_JOINTE/
                └── XGBClassifier_model_card.md   ← fiche technique du modèle
```

Si Directus est démarré, 2 éléments supplémentaires sont publiés.

```
Directus (http://localhost:8055)
├── collection charts      → Confusion Matrix (Plotly JSON)
└── collection reports_mdx → Model Card MDX (lisible depuis Next.js)
```

---

## Ce que contient le fichier .pkl

Le pipeline sauvegardé contient deux étapes assemblées en un seul objet.

```
XGBClassifier_20260525_v1.pkl
│
├── preprocessor (ColumnTransformer)
│   ├── colonnes numériques    → SimpleImputer(median) + StandardScaler
│   └── colonnes catégorielles → SimpleImputer(mode)   + OneHotEncoder
│
└── model (XGBClassifier)
    └── paramètres appris pendant l'entraînement
```

Pour l'utiliser.

```python
import joblib
import pandas as pd

artefact = joblib.load("models/XGBClassifier_20260525_v1.pkl")
pipeline = artefact["pipeline"]

X_new = pd.DataFrame([{
    "sexe":           "F",
    "niveau_etude":   "L3",
    "ville":          "Rennes",
    "specialisation": "RH",
    "credits_ects":   4.5,
    "volume_horaire": 120,
    "salaire":        62000,
    "semestre":       "S2",
}])

prediction = pipeline.predict(X_new)
# → ['Validé'] ou ['En cours'] ou ['Inscrit'] ou ['Abandonné']
```

---

## Résultats sur le dataset universitaire

```
Meilleur modèle : XGBClassifier
Accuracy        : 0.41
F1              : 0.40
ROC AUC         : 0.59
Features        : 16 conservées, 18 exclues automatiquement
Durée           : ~26 secondes (sans tuning)
```

Les métriques sont modestes car `statut` est une variable administrative
qui dépend du temps — pas vraiment prédictible depuis les caractéristiques
d'un étudiant. Sur un dataset churn ou prix, les métriques dépassent 0.85.

---

## Filtrage automatique des colonnes (select_analytical_features)

Avant d'entraîner, le système exclut automatiquement les colonnes inutiles.

| Catégorie exclue | Exemples dans ce dataset |
|-----------------|--------------------------|
| IDs séquentiels | id_inscription, id_etudiant, id_cours |
| Contacts | email, telephone |
| Noms propres | nom, prenom |
| Dates string | date_inscription, date_naissance, date_embauche |
| Bureau / salle | bureau |
| Constantes | filiere (= "Gestion" partout) |

Résultat : 18 colonnes exclues sur 33, le modèle travaille sur 16 colonnes utiles.

---

## Pipeline 19 étapes (logic.py)

| Étape | Action |
|-------|--------|
| 1 | Chargement CSV/Excel/JSON/Parquet |
| 2 | Détection automatique du type de problème |
| 3 | Analyse des corrélations features/cible |
| 4 | Création features dérivées (log, interaction, ratio) |
| 5 | SMOTE ou class_weight si déséquilibre > 3 |
| 5b | Filtrage colonnes non-analytiques (IDs, contacts, dates, bureau) |
| 6 | Split train/test avec stratification |
| 7 | Recommandation Gemini (2-3 algorithmes) |
| 8 | Construction configs sklearn |
| 9 | Preprocessing pipeline ColumnTransformer |
| 10 | Cross-validation + évaluation test set |
| 11 | Sélection du meilleur modèle |
| 12 | RandomizedSearchCV tuning (20 itérations) |
| 13 | Sauvegarde pipeline .pkl avec joblib |
| 14 | Extraction feature importance |
| 15 | Confusion matrix → Plotly → Directus |
| 16 | Courbe ROC → Plotly → Directus (binary seulement) |
| 17 | Génération Model Card MDX |
| 18 | Push Model Card MDX → Directus |
| 19 | Retourner ModelingResponse |

---

## Algorithmes supportés

| Type de problème | Algorithmes |
|-----------------|-------------|
| Classification | XGBClassifier, LGBMClassifier, RandomForestClassifier, LogisticRegression, SVC |
| Régression | XGBRegressor, LGBMRegressor, RandomForestRegressor, Ridge, Lasso |
| Clustering | KMeans, DBSCAN |

Gemini choisit automatiquement les 2-3 meilleurs algorithmes selon le dataset.
Fallback local si Gemini est indisponible.

---

## Lancer le pipeline

```bash
cd ~/Formations/AI_DATA_SKILL_SYSTEM/backend

# Dataset universitaire (multiclasse)
uv run --env-file .env python -m skills.modeling_skill.scripts.main \
  --input data/processed/Donnees_Universitaires/mapping_tables/Donnees_Universitaires_JOINTE.csv \
  --target statut \
  --session-id session_modeling \
  --no-tune

# Dataset churn (binaire) avec tuning
uv run --env-file .env python -m skills.modeling_skill.scripts.main \
  --input data/processed/clients/core_data/clients.csv \
  --target churn \
  --session-id session_churn

# Dataset prix (régression)
uv run --env-file .env python -m skills.modeling_skill.scripts.main \
  --input data/processed/immobilier/core_data/immobilier.csv \
  --target prix \
  --problem-type regression \
  --session-id session_prix
```

---

## Logs attendus

```
INFO [Modeling] Dataset charge : Donnees_Universitaires_JOINTE.csv (353 lignes x 33 cols)
INFO [Selector] Probleme detecte : multiclass_classification (n_classes=4)
INFO [FE] 1 features derivees creees
INFO [FE] Features : 16 colonnes conservees, 18 exclues (IDs/contacts/constantes)
INFO [Selector] Gemini recommande : ['XGBClassifier', 'LGBMClassifier', 'RandomForestClassifier']
INFO [Trainer] Labels encodes pour XGBoost : ['Abandonné', 'En cours', 'Inscrit', 'Validé']
INFO [Trainer] XGBClassifier   — 0.4085 (accuracy) — 3.67s
INFO [Trainer] LGBMClassifier  — 0.3239 (accuracy) — 4.06s
INFO [Trainer] RandomForest    — 0.3239 (accuracy) — 1.88s
INFO [Helpers] Meilleur modele : XGBClassifier (f1=0.4005)
INFO [Trainer] Pipeline sauvegarde : models/XGBClassifier_20260525_v1.pkl
INFO [Modeling] Confusion matrix → Directus : (vide si Directus off)
INFO [Modeling] Model Card MDX → local : outputs/model_cards/.../XGBClassifier_model_card.md
INFO [Modeling] Pipeline termine en 26075ms — XGBClassifier — status=success
```

---

## Via FastAPI Swagger

```bash
cd ~/Formations/AI_DATA_SKILL_SYSTEM/backend
uv run uvicorn api.main:app --reload --port 8000
# http://localhost:8000/docs → POST /api/modeling/train
```

```json
{
  "session_id":      "test_swagger",
  "dataset_path":    "data/processed/Donnees_Universitaires/mapping_tables/Donnees_Universitaires_JOINTE.csv",
  "target_column":   "statut",
  "problem_type":    "auto",
  "cv_folds":        5,
  "tune_best_model": false
}
```

---

## Via les tests

```bash
cd ~/Formations/AI_DATA_SKILL_SYSTEM/backend
pytest tests/test_modeling.py -v --cov=skills/modeling_skill/core
```

---

## Nouveautés par rapport aux Étapes 1 et 2

| Étape 1 — ETL | Étape 2 — Visualization | Étape 3 — Modeling |
|--------------|------------------------|-------------------|
| Nettoie les données | Génère des graphiques | Entraîne un modèle ML |
| Produit un CSV propre | Produit des charts Plotly | Produit un pipeline .pkl |
| Rapport ETL MDX | Rapport EDA MDX | Model Card MDX |
| `POST /api/etl/run` | `POST /api/visualization/eda` | `POST /api/modeling/train` |

---

## Fichiers produits

| Fichier | Lignes | Rôle |
|---------|--------|------|
| `schemas/modeling.py` | 192 | Pydantic ModelingRequest / ModelingResponse |
| `core/feature_engineer.py` | 374 | Corrélations + SMOTE + select_analytical_features |
| `core/selector.py` | 326 | Détection problème + Gemini + configs sklearn |
| `core/trainer.py` | 408 | Preprocessing + entraînement + tuning + joblib |
| `core/evaluator.py` | 510 | Métriques + confusion matrix + ROC + Model Card |
| `scripts/helpers.py` | 176 | Utilitaires (métriques, importance, serialize) |
| `scripts/logic.py` | 573 | Pipeline 19 étapes |
| `scripts/main.py` | 231 | CLI + executor.py |
| `api/routes/modeling.py` | 85 | Endpoint FastAPI |
| `tests/test_modeling.py` | 583 | Tests unitaires |

**Total : 3 458 lignes — syntaxe validée — errors: []**

---

## Dépendances avec les étapes précédentes

- Réutilise `src/utils/directus_client.py` — push charts et MDX (Étape 1)
- Réutilise `src/utils/gemini_client.py` — rotation clés Gemini (Étape 1)
- Consomme le `dataset_path` produit par ETL Skill (Étape 1)

---

## Prochaine étape

**Étape 6 — Skills Complémentaires (Session 2.3 suite)**

Trois Skills à construire dans cet ordre, toujours dans la même session 2.3.

```
Phase 6.1 — ML Explanation Skill
    Rôle     : rendre le modèle interprétable
    Action   : SHAP values, summary plot, waterfall plot, dependence plot
    Sortie   : SHAP charts → Directus + rapport MDX interprétabilité
    Endpoint : POST /api/explanation/shap

Phase 6.2 — Prediction Skill
    Rôle     : utiliser le modèle .pkl pour prédire sur de nouvelles données
    Action   : batch (CSV entier) ou temps réel (JSON ligne par ligne)
    Sortie   : CSV avec colonne prédiction + probabilités
    Endpoint : POST /api/prediction/run

Phase 6.3 — Analysis Skill
    Rôle     : synthétiser tous les résultats en insights business
    Action   : consolide ETL + EDA + Modeling + Prediction → rapport Gemini
    Sortie   : rapport Analysis MDX → Directus + export PDF
    Endpoint : POST /api/analysis/summary
```

Puis **Étape 4 (suite)** — pages Next.js Modeling & Predictions.

```
Phase 4.6 — Page Modeling
    MetricCard + confusion matrix + ROC + SHAP plots + Model Card MDXRenderer

Phase 4.7 — Page Predictions
    Formulaire features → POST /api/prediction/run + batch CSV + download CSV
```