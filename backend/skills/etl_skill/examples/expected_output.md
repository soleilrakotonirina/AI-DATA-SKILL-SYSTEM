# ETL Skill — Output Attendu

Ce document decrit les sorties attendues lorsque le ETL Skill est execute sur le dataset synthetique cree par `example_usage.py`.

---

## Dataset Source

| Propriete | Valeur |
|-----------|--------|
| Fichier | `synthetic_customers.csv` |
| Lignes avant | environ 210 (200 lignes + environ 10 doublons) |
| Colonnes | 9 |
| Problemes injectes | Nullites 10%, doublons 5%, outliers salary, types incorrects, variantes de casse |

---

## ETLRequest envoye

```python
ETLRequest(
    session_id="example_session_001",
    input_path="/tmp/data/raw/synthetic_customers.csv",
    missing_strategy="auto",
    fill_mode="smart",
    outlier_action="cap",
    outlier_method="iqr",
    encode_method="auto",
    scale_method="standard",
    generate_script=True,
    dimensional_modeling=False,
    target_column="churn",
    columns_to_exclude=["customer_id"],
)
```

---

## ETLResponse retourne (exemple typique)

```json
{
  "skill": "ETL",
  "session_id": "example_session_001",
  "status": "success",
  "rows_before": 210,
  "rows_after": 190,
  "cols_before": 9,
  "cols_after": 9,
  "nulls_removed": 80,
  "duplicates_removed": 10,
  "script_path": "outputs/rapport_etl/synthetic_customers/etl_script_synthetic_customers.py",
  "report_md_path": "outputs/rapport_etl/synthetic_customers/etl_report_synthetic_customers.md",
  "report_mdx_id": "mock_mdx_id_a1b2c3d4",
  "transformation_log": [
    {
      "etape": "load_dataset",
      "fonction": "load_dataset",
      "params": {"input_path": "/tmp/data/raw/synthetic_customers.csv"},
      "rows_before": 210,
      "rows_after": 210,
      "duration_ms": 45.2
    },
    {
      "etape": "sanitize_column_names",
      "fonction": "sanitize_column_names",
      "params": {},
      "rows_before": 210,
      "rows_after": 210,
      "duration_ms": 3.1
    },
    {
      "etape": "quality_report_before",
      "fonction": "generate_quality_report",
      "params": {"label": "before"},
      "rows_before": 210,
      "rows_after": 210,
      "duration_ms": 52.4
    },
    {
      "etape": "handle_missing_values",
      "fonction": "handle_missing_values",
      "params": {"strategy": "auto", "fill_mode": "smart"},
      "rows_before": 210,
      "rows_after": 210,
      "duration_ms": 28.7
    },
    {
      "etape": "remove_duplicates",
      "fonction": "remove_duplicates",
      "params": {},
      "rows_before": 210,
      "rows_after": 200,
      "duration_ms": 12.3
    },
    {
      "etape": "fix_data_types",
      "fonction": "fix_data_types",
      "params": {"n_conversions": 2},
      "rows_before": 200,
      "rows_after": 200,
      "duration_ms": 35.6
    },
    {
      "etape": "detect_and_treat_outliers",
      "fonction": "detect_and_treat_outliers",
      "params": {
        "method": "iqr",
        "action": "cap",
        "columns": ["age", "salary", "score"]
      },
      "rows_before": 200,
      "rows_after": 200,
      "duration_ms": 18.9
    },
    {
      "etape": "encode_categorical",
      "fonction": "encode_categorical",
      "params": {
        "method": "auto",
        "columns": ["city", "category"]
      },
      "rows_before": 200,
      "rows_after": 200,
      "duration_ms": 22.4
    },
    {
      "etape": "scale_features",
      "fonction": "scale_features",
      "params": {
        "method": "standard",
        "columns": ["age", "salary", "score"]
      },
      "rows_before": 200,
      "rows_after": 200,
      "duration_ms": 8.7
    },
    {
      "etape": "quality_report_after",
      "fonction": "generate_quality_report",
      "params": {"label": "after"},
      "rows_before": 200,
      "rows_after": 200,
      "duration_ms": 48.1
    }
  ],
  "errors": [],
  "error_message": null
}
```

---

## Transformations Attendues

| Etape | Action | Detail |
|-------|--------|--------|
| sanitize_column_names | Normalisation | Tous les noms en minuscules avec underscores |
| handle_missing_values | Imputation | `salary` mediane, `city` mode, `age` mediane apres conversion |
| remove_duplicates | Suppression | environ 10 lignes dupliquees supprimees |
| fix_data_types | Conversion | `age` string en float64, `signup_date` string en datetime |
| detect_and_treat_outliers | Capping IQR | `salary` valeurs hors bornes ramenees a Q3+1.5*IQR |
| encode_categorical | Label ou OneHot auto | `city` (cardinalite 6 apres normalisation), `category` (cardinalite 3) |
| scale_features | StandardScaler | `age`, `salary`, `score` (mu=0, sigma=1) |

Colonnes protegees automatiquement (non transformees) :
- `customer_id` (dans columns_to_exclude)
- `churn` (target_column)
- `signup_date` (detecte comme datetime)
- `name` (cardinalite tres elevee, ignore)

---

## Fichiers Generes (arborescence)

```
data/processed/
└── synthetic_customers/
    └── core_data/
        └── synthetic_customers.csv      ← Dataset propre lisible

outputs/
└── rapport_etl/
    └── synthetic_customers/
        ├── etl_quality_report_before.md  ← Rapport qualite initial
        ├── etl_quality_report_after.md   ← Rapport qualite final
        ├── etl_report_synthetic_customers.md   ← Rapport comparatif
        └── etl_script_synthetic_customers.py   ← Script Python autonome
```

---

## Rapport MDX publie dans Directus

Collection `reports_mdx`, item identifie par `report_mdx_id`.

```json
{
  "id": "mock_mdx_id_a1b2c3d4",
  "session_id": "example_session_001",
  "type": "etl",
  "title": "Rapport ETL — synthetic_customers",
  "content_mdx": "# Rapport ETL — Nettoyage et Transformation\n\n**Genere le** : ...",
  "created_at": "2026-05-14T14:32:18Z"
}
```

Le `content_mdx` contient :
- Tableau comparatif avant/apres
- Liste des 10+ transformations appliquees
- Statistiques descriptives apres nettoyage
- Sections rendues par MDXRenderer dans Next.js

---

## Verifications Post-Execution

```python
# Verifier la structure de la reponse
assert response.skill == "ETL"
assert response.status in ("success", "error")
assert response.session_id == "example_session_001"

# Verifier les metriques
assert response.rows_before > 0
assert response.rows_after <= response.rows_before
assert response.duplicates_removed >= 0
assert response.nulls_removed >= 0

# Verifier les fichiers generes
from pathlib import Path
if response.script_path:
    assert Path(response.script_path).exists()
if response.report_md_path:
    assert Path(response.report_md_path).exists()

# Verifier le rapport MDX
if response.report_mdx_id:
    # En production : lire depuis Directus
    # from src.utils.directus_client import get_report_mdx
    # report = await get_report_mdx(response.report_mdx_id)
    # assert report["type"] == "etl"
    pass

# Verifier le log
assert isinstance(response.transformation_log, list)
assert len(response.transformation_log) >= 5
```

---

## Apercu du Rapport Markdown genere

```markdown
# Rapport ETL — Nettoyage et Transformation

**Genere le** : 14/05/2026 14:32:18

---

## Comparaison Avant / Apres

| Indicateur | Avant | Apres | Variation |
|------------|-------|-------|-----------|
| Lignes           | 210   | 200   | -10       |
| Colonnes         | 9     | 9     | +0        |
| Taux nullite (%) | 8.5   | 0.0   | -8.50     |
| Doublons         | 10    | 0     | -10       |

---

## Transformations Appliquees

### 1. load_dataset
- **fonction** : `load_dataset`
- **rows_before** : `210`
- **rows_after** : `210`
- **duration_ms** : `45.2`

### 2. handle_missing_values
- **fonction** : `handle_missing_values`
- **rows_before** : `210`
- **rows_after** : `210`
- **duration_ms** : `28.7`

(... et 8 autres etapes)
```

---

## Cas d'erreur typiques

### Fichier introuvable

```json
{
  "skill": "ETL",
  "session_id": "example_session_001",
  "status": "error",
  "error_message": "Fichier introuvable : /tmp/data/raw/missing.csv",
  "errors": ["Fichier introuvable : /tmp/data/raw/missing.csv"]
}
```

### Format non supporte

```json
{
  "skill": "ETL",
  "session_id": "example_session_001",
  "status": "error",
  "error_message": "Format non supporte : '.xyz'. Formats acceptes : ['.csv', '.json', '.parquet', ...]"
}
```

### Validation Pydantic echouee

```json
{
  "skill": "ETL",
  "session_id": "unknown_session",
  "status": "error",
  "error_message": "Validation Pydantic echouee : missing_strategy must be one of: auto, constant, drop"
}
```