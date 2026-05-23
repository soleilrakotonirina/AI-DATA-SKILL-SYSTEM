# AI DATA SKILL SYSTEM — Étape 1 : ETL Skill

## Ce qui a été construit dans cette étape

Le **ETL Skill** est le premier module du système. Il prend un fichier brut ou une
URL distante et produit des données propres, structurées et exploitables par les
Skills suivants (Visualization, Modeling, Prediction...).

Pipeline en **16 étapes** entièrement automatisé :

- **Chargement multi-format** : CSV, Excel (multi-feuilles), JSON, Parquet, URL distante
- **Chargement depuis URL** : REST API paginée (World Bank, OpenData), CSV distant, JSON, XML
- **Normalisation du schéma** : noms de colonnes standardisés via scoring v3
- **Nettoyage** : valeurs manquantes, doublons, outliers IQR/Z-score
- **Transformation** : encodage catégoriel, scaling, features dérivées
- **Modélisation dimensionnelle** : construction automatique d'un Star Schema + table jointe
- **Rapports qualité** : avant/après avec métriques complètes, poussés dans Directus
- **Script ETL reproductible** : génération d'un script Python autonome re-exécutable
- **Rapport MDX** : publié dans Directus, lisible depuis Next.js

---

## Architecture du pipeline

```
Fichier local / URL distante
          │
          ▼
┌─────────────────────────────────────┐
│  loader.py                          │
│  - CSV, Excel, JSON, Parquet        │
│  - URL REST avec pagination auto    │
│    (page / offset / cursor)         │
│  - World Bank, OpenData, DRF, OData │
│  - XML converti en JSON             │
│  → DataFrame brut + métadonnées     │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  normalizer.py  (v3 scoring)        │
│  - Standardise les noms de colonnes │
│  - Scoring : PascalCase(4,3) >      │
│    Acronyme(4,2) > Title(4,1) >     │
│    Title court(3,0) > UPPER(2,0) >  │
│    lower(1,0)                       │
│  - Règle préfixe pour fuzzy         │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  cleaner.py                         │
│  - Nettoyage noms de colonnes       │
│  - Valeurs manquantes               │
│    (médiane / mode / constante /    │
│     suppression)                    │
│  - Suppression doublons             │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  transformer.py                     │
│  - Outliers IQR ou Z-score          │
│    (cap / remove / flag)            │
│  - Encodage catégoriel              │
│    (auto / label / onehot)          │
│  - Scaling numérique                │
│    (standard / minmax)              │
│  - Features dérivées automatiques   │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  star_schema.py                     │
│  - Détection auto dimensions/faits  │
│    seuil adaptatif selon n_rows     │
│    (0.70 petite → 0.40 grande)      │
│  - BFS transitif pour jointures     │
│  - creer_table_jointe()             │
│  - 4 feuilles Excel → tables Star   │
│  - Rejet annees (1900-2100)         │
│  - Rejet téléphones (> 10k)         │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  validator.py + exporter.py         │
│  - Rapport qualité AVANT / APRÈS    │
│  - Script ETL Python reproductible  │
│  - Sauvegarde CSV/Parquet propre    │
│  - Rapport MDX → Directus           │
└──────────────┬──────────────────────┘
               │
               ▼
         Directus CMS
    reports_mdx (3 rapports)
    + fichiers data/processed/
```

---

## Paramètres ETLRequest

| Paramètre | Type | Défaut | Description |
|-----------|------|--------|-------------|
| `session_id` | str | — | ID session Directus (obligatoire) |
| `input_path` | str\|null | null | Chemin fichier local (CSV, Excel, JSON, Parquet) |
| `input_url` | str\|null | null | URL distante REST (alternative à input_path) |
| `missing_strategy` | enum | `"auto"` | `auto`=médiane/mode, `constant`=N/D/0, `drop`=suppression |
| `fill_mode` | enum | `"smart"` | `smart`=adapté au type, `constant`=valeurs fixes |
| `outlier_action` | enum | `"cap"` | `cap`=capping bornes, `remove`=ligne, `flag`=colonne |
| `outlier_method` | enum | `"iqr"` | `iqr`=1.5×IQR, `zscore`=\|z\|>3 |
| `encode_method` | enum | `"auto"` | `auto`=label si card≤10 sinon onehot, `label`, `onehot` |
| `scale_method` | enum | `"standard"` | `standard`=StandardScaler, `minmax`=MinMaxScaler [0,1] |
| `generate_script` | bool | `true` | Générer script ETL Python reproductible |
| `dimensional_modeling` | bool | `false` | Construire Star Schema (tables faits + dimensions) |
| `target_column` | str\|null | null | Colonne ML protégée des encodages et scalings |
| `columns_to_exclude` | list | `[]` | Colonnes exclues de toutes les transformations |

---

## Chargement depuis URL (loader.py)

Le loader supporte la pagination automatique pour les APIs REST.

| Style API | Paramètre pagination | Exemple |
|-----------|---------------------|---------|
| World Bank | `page=N` | `api.worldbank.org/v2/...?format=json&per_page=50` |
| OpenData offset | `offset=N&limit=L` | API INSEE, data.gouv.fr |
| Cursor | `cursor=TOKEN` | APIs modernes |
| DRF | `page=N` | Django REST Framework |
| OData | `$skip=N` | Microsoft OData |

```bash
# Exemple World Bank
uv run --env-file .env python -m skills.etl_skill.scripts.main \
  --url "https://api.worldbank.org/v2/country/all/indicator/NY.GDP.MKTP.CD?format=json&per_page=50" \
  --session-id session_worldbank
```

```
INFO [Loader] Structure World Bank : page 1/352, total=17556
INFO [Loader] Page 1 : 50 records (cumul : 50)
INFO [ETL] URL -> CSV temporaire : url_import_xxx.csv (2500 lignes x 8 cols)
```

---

## Modélisation dimensionnelle (star_schema.py)

Quand `dimensional_modeling=true`, le pipeline construit automatiquement :

**Détection des colonnes :**
- `_est_dimension()` : seuil adaptatif — 70% unicité pour petites tables, 40% pour grandes
- `_est_mesure()` : rejette les années (1900-2100), téléphones (>10k à faible variance)
- `_est_temporelle()` : mots-clés + valeurs entières dans plage temporelle

**Résultat pour un Excel multi-feuilles :**
```
data/processed/Donnees_Universitaires/
├── core_data/
│   ├── Etudiants.csv
│   ├── Cours.csv
│   └── Enseignants.csv
└── mapping_tables/
    ├── Donnees_Universitaires_JOINTE.csv   ← table jointe finale
    ├── dim_niveau_etude.csv
    ├── dim_ville.csv
    └── fact_inscriptions.csv
```

**BFS transitif :** si `Inscriptions → Cours` et `Cours → Enseignants`,
la table jointe inclut automatiquement les colonnes Enseignants.

---

## Normalizer v3 (normalizer.py)

Système de scoring pour choisir le meilleur nom de colonne :

| Format | Score principal | Score secondaire | Exemple |
|--------|----------------|-----------------|---------|
| PascalCase | 4 | 3 | `NomEtudiant` |
| Acronyme court | 4 | 2 | `ECTS` |
| Title long (>8 chars) | 4 | 1 | `Nom Etudiant` |
| Title court | 3 | 0 | `Nom` |
| UPPER long | 2 | 0 | `NOM_ETUDIANT` |
| lower | 1 | 0 | `nom_etudiant` |

Règle préfixe pour fuzzy matching : `Madagascar` > `Madagascararr` ✓

---

## Sorties ETLResponse

| Champ | Type | Description |
|-------|------|-------------|
| `skill` | str | Toujours `"ETL"` |
| `session_id` | str | ID session |
| `status` | str | `"success"` ou `"error"` |
| `rows_before` / `rows_after` | int | Lignes avant/après nettoyage |
| `cols_before` / `cols_after` | int | Colonnes avant/après |
| `nulls_removed` | int | Valeurs manquantes traitées |
| `duplicates_removed` | int | Doublons supprimés |
| `script_path` | str | Chemin du script ETL reproductible |
| `report_md_path` | str | Chemin rapport Markdown local |
| `report_mdx_id` | str | UUID du rapport MDX dans Directus |
| `transformation_log` | list | Journal complet des 16 étapes |
| `errors` | list | Erreurs non bloquantes |

---

## Structure des fichiers

```
backend/
├── schemas/
│   └── etl.py                 ETLRequest + ETLResponse (Pydantic v2)
│
├── src/utils/
│   ├── directus_client.py     Client HTTP async (push MDX, charts, logs)
│   └── gemini_client.py       Rotation automatique clés Gemini
│
├── api/routes/
│   └── etl.py                 Endpoint POST /api/etl/run
│
├── skills/etl_skill/
│   ├── SKILL.md               Documentation LLM (frontmatter YAML)
│   ├── api-guide.md           Guide intégration FastAPI + TypeScript
│   │
│   ├── core/
│   │   ├── cleaner.py         Chargement multi-format + nettoyage
│   │   ├── loader.py          Chargement URL distante + pagination auto
│   │   ├── transformer.py     Encodage + scaling + outliers + features
│   │   ├── normalizer.py      Normalisation schéma v3 (scoring)
│   │   ├── star_schema.py     Star Schema + BFS transitif + table jointe
│   │   ├── validator.py       Rapports qualité avant/après
│   │   └── exporter.py        Sauvegarde + rapport Markdown + script ETL
│   │
│   ├── scripts/
│   │   ├── main.py            CLI (--input / --url / --plan) + executor.py
│   │   ├── logic.py           Pipeline async 16 étapes
│   │   └── helpers.py         Utilitaires partagés
│   │
│   └── examples/
│       ├── example_usage.py   Exemple complet avec dataset synthétique
│       ├── sample_config.json Plan JSON d'exemple
│       └── expected_output.md Description des sorties attendues
│
└── tests/
    └── test_etl.py            Tests unitaires + endpoint FastAPI
```

---

## Démarrage rapide

### Variables d'environnement

```bash
# backend/.env
GEMINI_API_KEY=AIzaSy...
GEMINI_API_KEY_2=AIzaSy...    # Rotation si quota (optionnel)
DIRECTUS_URL=http://localhost:8055
DIRECTUS_TOKEN=votre_token

DATA_RAW_DIR=./data/raw
DATA_PROCESSED_DIR=./data/processed
```

### Lancer le pipeline

```bash
cd backend

# Fichier local CSV ou Excel
uv run --env-file .env python -m skills.etl_skill.scripts.main \
  --input data/raw/Donnees_Universitaires.xlsx \
  --session-id session_etl_001

# Fichier local avec Star Schema
uv run --env-file .env python -m skills.etl_skill.scripts.main \
  --input data/raw/Donnees_Universitaires.xlsx \
  --session-id session_etl_002

# URL distante (World Bank)
uv run --env-file .env python -m skills.etl_skill.scripts.main \
  --url "https://api.worldbank.org/v2/country/all/indicator/NY.GDP.MKTP.CD?format=json&per_page=50" \
  --session-id session_worldbank

# Via plan JSON orchestrateur
uv run --env-file .env python -m skills.etl_skill.scripts.main \
  --plan examples/sample_config.json \
  --session-id session_plan_001
```

### Résultat attendu dans les logs

```
INFO [ETL] Demarrage pipeline — session=session_etl_001, input=Donnees_Universitaires.xlsx
INFO [Loader] Multi-feuilles detecte : 4 feuilles (Inscriptions, Etudiants, Cours, Enseignants)
INFO [Normalizer] Colonnes normalisees : 33 colonnes traitees, score moyen=3.8
INFO [Cleaner] CSV charge : Donnees_Universitaires.xlsx (353 lignes x 33 colonnes)
INFO [Cleaner] Aucun doublon detecte
INFO [Validator] Rapport qualite 'before' ecrit : outputs/rapport_etl/...
INFO [StarSchema] 4 tables construites + table JOINTE (353 lignes x 33 cols)
INFO [Exporter] Script ETL reproductible genere : outputs/.../etl_script_xxx.py
INFO [Directus] 3 rapports MDX pousses (before / after / comparatif)
INFO [ETL] Pipeline termine en 3.2s — status=success, errors=0
```

### Via FastAPI Swagger

```bash
uvicorn api.main:app --reload --port 8000
# http://localhost:8000/docs → POST /api/etl/run
```

```json
{
  "session_id":          "test_swagger",
  "input_path":          "data/raw/Donnees_Universitaires.xlsx",
  "missing_strategy":    "auto",
  "outlier_action":      "cap",
  "encode_method":       "auto",
  "scale_method":        "standard",
  "generate_script":     true,
  "dimensional_modeling": true,
  "target_column":       null,
  "columns_to_exclude":  []
}
```

### Via les tests

```bash
pytest tests/test_etl.py -v --cov=skills/etl_skill/core
```

---

## Pipeline 16 étapes (logic.py)

| Étape | Module | Action |
|-------|--------|--------|
| 1 | `loader.py` | Chargement multi-format (CSV/Excel/JSON/Parquet) |
| 2 | `loader.py` | Chargement URL distante avec pagination auto |
| 3 | `normalizer.py` | Scoring v3 + normalisation noms de colonnes |
| 4 | `cleaner.py` | Nettoyage noms colonnes (sanitize) |
| 5 | `cleaner.py` | Valeurs manquantes (médiane/mode/constante/drop) |
| 6 | `cleaner.py` | Suppression doublons |
| 7 | `transformer.py` | Détection + traitement outliers (IQR ou Z-score) |
| 8 | `transformer.py` | Encodage variables catégorielles |
| 9 | `transformer.py` | Scaling variables numériques |
| 10 | `transformer.py` | Génération features dérivées automatiques |
| 11 | `star_schema.py` | Construction Star Schema + table jointe (si activé) |
| 12 | `validator.py` | Rapport qualité AVANT (métriques complètes) |
| 13 | `validator.py` | Rapport qualité APRÈS |
| 14 | `exporter.py` | Sauvegarde datasets nettoyés (CSV + Parquet) |
| 15 | `exporter.py` | Génération script ETL Python reproductible |
| 16 | `directus_client.py` | Push 3 rapports MDX → Directus |

---

## Formats d'entrée supportés

| Format | Extension | Multi-feuilles | Notes |
|--------|-----------|---------------|-------|
| CSV | `.csv` | Non | `low_memory=False` |
| Excel | `.xlsx`, `.xls` | **Oui** | Chaque feuille = dataset indépendant |
| JSON | `.json` | Non | |
| Parquet | `.parquet` | Non | Via pyarrow |
| URL REST | HTTP(S) | Non | Pagination auto |
| URL CSV | HTTP(S) | Non | Téléchargement direct |

---

## Ajouter le endpoint au router FastAPI

```python
# backend/api/main.py
from api.routes.etl import router as etl_router
app.include_router(etl_router, prefix="/api")
```

---

## Fichiers produits par cette étape

| Fichier | Lignes | Rôle |
|---------|--------|------|
| `schemas/etl.py` | ~180 | Pydantic ETLRequest / ETLResponse |
| `src/utils/directus_client.py` | ~150 | Client HTTP async Directus |
| `src/utils/gemini_client.py` | ~160 | Rotation clés Gemini |
| `api/routes/etl.py` | ~80 | Endpoint FastAPI POST /api/etl/run |
| `core/cleaner.py` | ~350 | Chargement + nettoyage |
| `core/loader.py` | ~447 | URL distante + pagination |
| `core/transformer.py` | ~400 | Encodage + scaling + outliers |
| `core/normalizer.py` | ~300 | Scoring v3 noms colonnes |
| `core/star_schema.py` | ~500 | Star Schema + BFS + table jointe |
| `core/validator.py` | ~250 | Rapports qualité |
| `core/exporter.py` | ~300 | Sauvegarde + Markdown + script ETL |
| `scripts/main.py` | ~235 | CLI + executor.py |
| `scripts/logic.py` | ~500 | Pipeline 16 étapes |
| `scripts/helpers.py` | ~100 | Utilitaires |
| `tests/test_etl.py` | ~7554 | Tests unitaires complets |

---

## Prochaine étape

**Étape 2 — Visualization Skill (Session 2.2)**

Classification automatique des colonnes, plan de graphiques via Gemini,
8 types de graphiques style Power BI, substitution ID→Libellé,
rapport EDA MDX complet avec KPIs.

Endpoint : `POST /api/visualization/eda`
