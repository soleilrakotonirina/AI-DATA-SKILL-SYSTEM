# AI DATA SKILL SYSTEM — Étape 2 : Visualization Skill

## Ce qui a été construit dans cette étape

Le **Visualization Skill** est le deuxième module du système. Il reçoit le dataset
propre produit par le ETL Skill et génère automatiquement un dashboard BI intelligent :

- **Classification automatique des colonnes** : dimensions, mesures, temporelles, IDs, contacts, noms propres — aucune colonne absurde dans les graphiques
- **KPIs intelligents** calculés automatiquement (total, uniques, moyennes, taux de validation...)
- **Plan de graphiques via Gemini** : Gemini analyse le dataset et choisit les meilleures relations X/Y. Fallback local intelligent si Gemini indisponible
- **Substitution ID → Libellé** : `id_cours` → `nom_cours`, `id_enseignant` → `nom_Enseignants` détectés automatiquement. L'ID reste référence interne mais n'apparaît jamais dans les graphiques
- **8 types de graphiques style Power BI** : bar, donut, stacked bar, boxplot, line, heatmap, scatter — palette colorblind-friendly
- **Relations X/Y cohérentes** : jamais de graphique absurde (email vs salaire, ID vs crédits...)
- **Commentaires narratifs Gemini** par graphique en langage métier
- **Rapport EDA MDX complet** avec KPIs, statistiques, évolution temporelle, graphiques commentés — publié dans Directus
- **Rotation automatique des clés Gemini** : bascule sur GEMINI_API_KEY_2, _3... en cas de quota
- **Multi-fichiers** : traitement d'un fichier, d'un dossier entier ou d'un pattern glob en une seule commande
- **Hiérarchie de sortie** cohérente avec l'Étape 1 ETL

---

## Architecture intelligente

```
Dataset CSV / Excel / Parquet
          │
          ▼
┌─────────────────────────────────────┐
│  kpi_engine.py                      │
│  - Classifier chaque colonne        │
│    entite / mesure / temporelle /   │
│    id / contact / nom_propre /      │
│    constante → exclue               │
│  - Detecter mappings ID → Libelle   │
│    id_cours    → nom_cours          │
│    id_enseignant → nom_Enseignants  │
│  - Calculer KPIs intelligents       │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  dashboard_builder.py               │
│  - Appel Gemini → plan JSON         │
│    (type, x, y, color, titre...)    │
│  - Si quota → fallback local        │
│  - Substituer IDs par libellés      │
│  - Valider plan (colonnes ok ?)     │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  charts.py  (style Power BI)        │
│  - generate_bar_count()             │
│  - generate_bar_mesure()            │
│  - generate_donut()                 │
│  - generate_stacked_bar()           │
│  - generate_boxplot_mesure()        │
│  - generate_line_count()            │
│  - generate_heatmap_crosstab()      │
│  - generate_scatter_mesures()       │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  exporter.py                        │
│  - Export HTML + PNG (kaleido)      │
│  - Serialisation JSON → Directus    │
│  - Rapport MDX complet :            │
│    frontmatter / score_global /     │
│    KPIs / stats / distributions /   │
│    évolution temporelle /           │
│    graphiques commentés /           │
│    conclusions                      │
└──────────────┬──────────────────────┘
               │
               ▼
         Directus CMS
    charts + reports_mdx
```

---

## Hiérarchie de sortie (cohérente avec ETL)

Le Visualization Skill respecte la même hiérarchie que l'ETL Skill.

**Input ETL :**
```
data/processed/Donnees_Universitaires/
├── core_data/
│   ├── Etudiants.csv
│   ├── Cours.csv
│   └── Enseignants.csv
└── mapping_tables/
    └── Donnees_Universitaires_JOINTE.csv
```

**Output Visualization :**
```
outputs/
├── charts/
│   └── Donnees_Universitaires/
│       ├── Donnees_Universitaires_JOINTE/
│       │   ├── 01_donut_statut.html
│       │   ├── 01_donut_statut.png
│       │   ├── 02_bar_niveau_etude.html
│       │   ├── 02_bar_niveau_etude.png
│       │   └── ...
│       ├── Etudiants/
│       │   └── ...
│       └── Cours/
│           └── ...
│
└── rapport_eda/
    └── Donnees_Universitaires/
        ├── Donnees_Universitaires_JOINTE/
        │   └── eda_report_Donnees_Universitaires_JOINTE.md
        ├── Etudiants/
        │   └── eda_report_Etudiants.md
        └── Cours/
            └── eda_report_Cours.md
```

---

## Nouveautés par rapport à la version initiale

| Fonctionnalité | Avant | Après |
|----------------|-------|-------|
| Sélection graphiques | 1 graphique par colonne | Plan Gemini ou fallback intelligent |
| Relations X/Y | Aléatoires | Cohérentes et analytiques uniquement |
| Colonnes IDs | Affichées brutes (CRS001...) | Remplacées par libellé (nom_cours) |
| Colonnes exclues | Aucune exclusion | IDs, contacts, noms propres, constantes exclus |
| KPIs | Absents | Calculés automatiquement |
| Types graphiques | histogram / boxplot / heatmap | 8 types style Power BI |
| Couleurs | Palette générique | Colorblind-friendly + couleurs sémantiques |
| Rapport MDX | Basique | KPIs + distributions + évolution + commentaires |
| Gemini quota | Erreur bloquante | Rotation automatique sur clés de secours |
| Input | Fichier unique uniquement | Fichier / dossier / glob |
| Hiérarchie sortie | `outputs/charts/{stem}/` | `outputs/charts/{groupe}/{stem}/` |

---

## Stack technique

| Composant | Technologie | Rôle |
|-----------|-------------|------|
| Backend | FastAPI | Endpoint POST /api/visualization/eda |
| Validation | Pydantic v2 | VisualizationRequest / VisualizationResponse |
| Graphiques | Plotly | 8 types de graphiques interactifs style BI |
| Export PNG | kaleido | Export statique des graphiques |
| IA orchestration | Gemini 2.5 Flash | Plan graphiques + commentaires narratifs |
| Rotation clés | gemini_client.py | Bascule GEMINI_API_KEY → _2 → _3 si quota |
| CMS | Directus | Stockage Plotly JSON (charts) + MDX (reports_mdx) |
| DB Directus | SQLite | Zéro installation |
| Frontend | Next.js + Plotly.js | Rendu depuis Directus |

---

## Structure des fichiers

```
skills/visualization_skill/
│
├── SKILL.md                    Documentation LLM — quand activer ce Skill
├── api-guide.md                Guide intégration TypeScript + FastAPI
│
├── core/
│   ├── kpi_engine.py           Classification colonnes + KPIs + mappings ID→Libellé
│   ├── eda.py                  Corrélation Pearson, stats descriptives, patterns
│   ├── charts.py               8 types de graphiques Plotly style Power BI
│   ├── dashboard_builder.py    Plan Gemini + fallback local + substitution IDs
│   └── exporter.py             Export HTML/PNG + rapport MDX complet
│
├── scripts/
│   ├── main.py                 CLI multi-fichiers + executor.py entry point
│   ├── logic.py                Pipeline 11 étapes
│   └── helpers.py              build_chart_stats_summary, sanitize_filename
│
└── examples/
    ├── example_usage.py        Démo standalone (Directus mocké si absent)
    ├── sample_config.json      Plan JSON complet
    └── expected_output.md      Output attendu pour validation
```

---

## Variables d'environnement

```bash
# backend/.env
GEMINI_API_KEY=AIzaSy...          # Clé principale
GEMINI_API_KEY_2=AIzaSy...        # Rotation si quota (optionnel)
GEMINI_API_KEY_3=AIzaSy...        # Jusqu'à GEMINI_API_KEY_20
DIRECTUS_URL=http://localhost:8055
DIRECTUS_TOKEN=votre_token
```

---

## Usages CLI

### Fichier unique

```bash
uv run --env-file .env python -m skills.visualization_skill.scripts.main \
  --input data/processed/Donnees_Universitaires/mapping_tables/Donnees_Universitaires_JOINTE.csv \
  --session-id session_viz_jointe
```

### Dossier entier — traite tous les CSV/Excel/Parquet trouvés récursivement

```bash
uv run --env-file .env python -m skills.visualization_skill.scripts.main \
  --input data/processed/Donnees_Universitaires/ \
  --session-id session_viz_all
```

### Glob — seulement les tables core_data

```bash
uv run --env-file .env python -m skills.visualization_skill.scripts.main \
  --input "data/processed/Donnees_Universitaires/core_data/*" \
  --session-id session_viz_core
```

### Glob — seulement les mapping_tables

```bash
uv run --env-file .env python -m skills.visualization_skill.scripts.main \
  --input "data/processed/Donnees_Universitaires/mapping_tables/*" \
  --session-id session_viz_mapping
```

### Sans Gemini — fallback local, plus rapide, pas de quota

```bash
uv run --env-file .env python -m skills.visualization_skill.scripts.main \
  --input data/processed/Donnees_Universitaires/mapping_tables/Donnees_Universitaires_JOINTE.csv \
  --session-id session_viz_local \
  --no-gemini
```

### Avec question analytique et variable cible

```bash
uv run --env-file .env python -m skills.visualization_skill.scripts.main \
  --input data/processed/clients/core_data/clients.csv \
  --target churn \
  --question "Quelles variables distinguent le mieux les churners ?" \
  --session-id session_viz_churn
```

### Sans rapport MDX (graphiques uniquement)

```bash
uv run --env-file .env python -m skills.visualization_skill.scripts.main \
  --input data/processed/Donnees_Universitaires/core_data/Etudiants.csv \
  --session-id session_viz_etudiants \
  --no-report
```

---

## Résumé multi-fichiers

Quand plusieurs fichiers sont traités, le résumé final s'affiche :

```json
{
  "total": 4,
  "succes": 4,
  "echecs": 0,
  "fichiers": [
    {"fichier": "Cours.csv",                         "status": "success", "charts": 8,  "mdx_id": "uuid-1"},
    {"fichier": "Etudiants.csv",                     "status": "success", "charts": 10, "mdx_id": "uuid-2"},
    {"fichier": "Enseignants.csv",                   "status": "success", "charts": 6,  "mdx_id": "uuid-3"},
    {"fichier": "Donnees_Universitaires_JOINTE.csv", "status": "success", "charts": 14, "mdx_id": "uuid-4"}
  ]
}
```

---

## Logs attendus (fichier unique avec Gemini)

```
INFO  [Viz Skill] 1 fichier(s) a traiter
INFO  [Viz Skill] (1/1) Traitement : Donnees_Universitaires_JOINTE.csv — session=session_viz_jointe
INFO  [Viz] Dataset charge : Donnees_Universitaires_JOINTE.csv (353 lignes x 33 cols)
INFO  [Viz] Sorties : charts=outputs/charts/Donnees_Universitaires/Donnees_Universitaires_JOINTE
INFO  [KPI] Colonnes classifiees — entites=12, mesures=3, temporelles=3, exclues=7
INFO  [KPI] Mappings ID->Libelle detectes : {'id_cours': 'nom_cours', 'id_enseignant': 'nom_Enseignants'}
INFO  [Dashboard] Appel Gemini pour planifier le dashboard...
WARN  [Gemini] GEMINI_API_KEY quota depasse — rotation vers GEMINI_API_KEY_2
INFO  [Gemini] Succes avec GEMINI_API_KEY_2 (cle 2/10)
INFO  [Dashboard] Plan Gemini valide : 14 graphiques, 6 KPIs
INFO  [Dashboard] 14 graphiques Plotly construits
INFO  [Exporter] Rapport MDX : eda_report_Donnees_Universitaires_JOINTE.md (347 lignes)
INFO  [Viz Skill] (1/1) OK — Donnees_Universitaires_JOINTE.csv — 14 charts — mdx=uuid-xxx
```

---

## Logs attendus (sans Gemini)

```
INFO  [KPI] Colonnes classifiees — entites=12, mesures=3, temporelles=3, exclues=7
WARN  [Dashboard] Gemini n'a pas repondu — fallback local
INFO  [KPI] Plan local : 11 graphiques generes
INFO  [Dashboard] 11 graphiques Plotly construits
INFO  [Viz] Pipeline termine en 2.1s — 11 charts — source=local
```

---

## Types de graphiques générés

| Type | Quand | Exemple |
|------|-------|---------|
| `donut` | Dimension 2-5 valeurs | Répartition par sexe (M/F) |
| `bar` count | Dimension ≤ 20 valeurs | Inscriptions par niveau_etude |
| `bar` mesure | Dimension × mesure agrégée | Salaire moyen par grade |
| `stacked_bar` | 2 dimensions croisées | Niveau × statut coloré |
| `boxplot` | Dimension × mesure distribution | Crédits ECTS par niveau_etude |
| `line` | Temporelle × count ou mesure | Évolution des inscriptions |
| `heatmap` | 2 dimensions ≤ 8 valeurs chacune | Spécialisation × spécialité |
| `scatter` | 2 mesures numériques | credits_ects vs volume_horaire |

---

## Classification des colonnes (kpi_engine.py)

| Catégorie | Exemples dataset universitaire | Traitement |
|-----------|-------------------------------|------------|
| **Entités** | sexe, niveau_etude, statut, ville, grade, specialisation | Axe X ou couleur |
| **Mesures** | salaire, credits_ects, volume_horaire | Axe Y |
| **Temporelles** | annee_inscription, annee_academique | Axe X line charts |
| **IDs** | id_cours → nom_cours, id_enseignant → nom_Enseignants | Remplacés par libellé |
| **Contacts** | email, telephone, email_Enseignants | Exclus |
| **Constantes** | filiere (="Gestion"), departement | Exclus (< 2 valeurs) |
| **Noms propres** | nom, prenom, nom_Enseignants | Exclus des graphiques |

---

## Rapport MDX généré

```
outputs/rapport_eda/Donnees_Universitaires/Donnees_Universitaires_JOINTE/
└── eda_report_Donnees_Universitaires_JOINTE.md
```

Structure du rapport :

```markdown
---
title: Rapport EDA — Donnees_Universitaires_JOINTE
date: 23/05/2026 12:35
score_global: 87
---

## Résumé Exécutif
<KeyPoints>
- 353 inscriptions, 168 étudiants uniques, 20 cours, 12 enseignants
- Taux de validation : 21% — 79% en cours ou abandonnés
- Salaire moyen enseignants : 60 324,96 €
</KeyPoints>

## KPI Principaux
| 📚 Total Inscriptions    | 353        |
| ✅ Taux de Validation    | 21.0%      |
| 💰 Salaire Moyen        | 60 324,96  |
| 📖 Nb Cours Uniques     | 20         |
| 👨‍🏫 Nb Enseignants       | 12         |

## Statistiques Numériques
## Statistiques Catégorielles
## Évolution Temporelle
## Graphiques EDA  ← 14 graphiques avec commentaires Gemini
## Conclusions et Recommandations
```

---

## Via FastAPI Swagger

```bash
uvicorn api.main:app --reload --port 8000
# http://localhost:8000/docs → POST /api/visualization/eda
```

```json
{
  "session_id":      "test_swagger",
  "dataset_path":    "data/processed/Donnees_Universitaires/mapping_tables/Donnees_Universitaires_JOINTE.csv",
  "generate_report": true,
  "gemini_comments": true
}
```

---

## Ajouter le endpoint au router FastAPI

```python
# backend/api/main.py
from api.routes.visualization import router as visualization_router
app.include_router(visualization_router, prefix="/api")
```

---

## Via les tests

```bash
pytest tests/test_visualization.py -v --cov=skills/visualization_skill/core
```

---

## Dépendance avec l'Étape 1

Ce Skill réutilise :
- `src/utils/directus_client.py` — push charts et MDX vers Directus
- `src/utils/gemini_client.py` — appels Gemini avec rotation de clés

Il consomme les datasets produits par ETL Skill :

```
data/processed/{groupe}/{core_data|mapping_tables}/{fichier}.csv
                    ↓
         --input accepte :
         fichier unique / dossier / glob
```

---

## Fichiers produits par cette étape

| Fichier | Lignes | Rôle |
|---------|--------|------|
| `schemas/visualization.py` | 188 | Pydantic VisualizationRequest / VisualizationResponse |
| `core/kpi_engine.py` | 609 | Classification colonnes + KPIs + mappings ID→Libellé |
| `core/eda.py` | 190 | Corrélation Pearson + stats descriptives |
| `core/charts.py` | 875 | 8 types graphiques style Power BI |
| `core/dashboard_builder.py` | 513 | Plan Gemini + fallback + substitution IDs |
| `core/exporter.py` | 561 | Export HTML/PNG + rapport MDX complet |
| `scripts/helpers.py` | 133 | Utilitaires |
| `scripts/logic.py` | 362 | Pipeline 11 étapes + hiérarchie de sortie |
| `scripts/main.py` | 235 | CLI multi-fichiers (fichier / dossier / glob) |
| `api/routes/visualization.py` | 80 | Endpoint FastAPI |
| `tests/test_visualization.py` | 791 | Tests unitaires |
| `src/utils/gemini_client.py` | 160 | Rotation clés Gemini |

**Total : ~4 700 lignes de code production-ready**

---

## Prochaine étape

**Étape 3 — Modeling Skill (Session 2.3)**

Feature engineering, sélection automatique d'algorithme via Gemini,
entraînement avec cross-validation, évaluation (accuracy, F1, AUC-ROC, RMSE),
sauvegarde joblib, Model Card MDX dans Directus.

Endpoint : `POST /api/modeling/train`