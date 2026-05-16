---
name: etl-skill
description: Cleans, transforms, and prepares raw datasets for analysis. Exposes a FastAPI endpoint POST /api/etl/run validated by Pydantic. Publishes an MDX report to Directus after execution. Use when the user asks to clean data, fix missing values, remove duplicates, encode variables, normalize features, detect outliers, or generate a reproducible ETL script. Triggers in French and English natural language requests like "nettoie mes donnees", "prepare le dataset", "supprime les doublons", "gere les valeurs manquantes", "encode les variables categorielles", "normalise les features", or "build a star schema from this table".
metadata:
  version: 1.0.0
  author: AI DATA SKILL SYSTEM
  session: 2.1
  endpoint: POST /api/etl/run
  pydantic_request: ETLRequest
  pydantic_response: ETLResponse
  directus_output: reports_mdx
  dependencies:
    - pandas
    - numpy
    - scikit-learn
    - openpyxl
    - pyarrow
    - google-genai
    - httpx
    - pydantic
    - fastapi
  outputs_consumed_by:
    - visualization-skill
    - modeling-skill
    - analysis-skill
---

# ETL Skill

## Description

Le ETL Skill est le premier maillon du pipeline AI DATA SKILL SYSTEM. Il prend en entree un dataset brut (CSV, Excel, JSON, Parquet) et produit un dataset propre, normalise, pret pour la visualisation et le machine learning.

Le Skill est expose comme un endpoint FastAPI valide par Pydantic, orchestrable par Gemini via plan JSON, et publie son rapport MDX dans Directus. Il s'integre dans le flux complet : Next.js, FastAPI, Skills Engine, Python Execution, Directus, Gemini Explanation, Next.js Output.

**Quand utiliser ce Skill** :
- L'utilisateur uploade un dataset et demande de le nettoyer
- L'utilisateur veut traiter les valeurs manquantes, doublons ou outliers
- L'utilisateur veut encoder des variables categorielles ou normaliser des features numeriques
- L'utilisateur demande un script ETL reproductible
- L'utilisateur souhaite construire un Star Schema depuis une table plate

**Quand ne pas utiliser ce Skill** :
- L'utilisateur veut uniquement visualiser sans transformer (utiliser Visualization Skill)
- L'utilisateur veut entrainer un modele ML (utiliser Modeling Skill)
- L'utilisateur fournit deja un dataset propre

## FastAPI Endpoint

```
POST /api/etl/run
Content-Type: application/json
Body: ETLRequest (Pydantic)
Response: ETLResponse (Pydantic)
```

## Inputs (ETLRequest Pydantic)

| Parametre | Type | Defaut | Obligatoire | Description |
|-----------|------|--------|-------------|-------------|
| session_id | str | aucun | Oui | Identifiant de session cree dans Directus |
| input_path | str | aucun | Oui | Chemin du fichier source (CSV, Excel, JSON, Parquet) |
| missing_strategy | "auto", "constant", "drop" | "auto" | Non | Strategie d'imputation des valeurs manquantes |
| fill_mode | "smart", "constant" | "smart" | Non | Mode de remplissage pour les imputations |
| outlier_action | "cap", "remove", "flag" | "cap" | Non | Action sur les valeurs aberrantes detectees |
| outlier_method | "iqr", "zscore" | "iqr" | Non | Methode de detection des outliers |
| encode_method | "auto", "label", "onehot" | "auto" | Non | Methode d'encodage des variables categorielles |
| scale_method | "standard", "minmax" | "standard" | Non | Methode de normalisation des variables numeriques |
| generate_script | bool | true | Non | Generer un script Python reproductible |
| dimensional_modeling | bool | false | Non | Construire un Star Schema |
| target_column | str ou null | null | Non | Colonne cible ML a proteger des transformations |
| columns_to_exclude | list[str] | [] | Non | Colonnes a exclure de toutes les transformations |

## Outputs (ETLResponse Pydantic)

| Cle | Type | Description | Destination |
|-----|------|-------------|-------------|
| skill | str | Toujours "ETL" | Next.js |
| session_id | str | Identifiant de session Directus | Next.js |
| status | "success", "error" | Statut final du pipeline | Next.js |
| rows_before | int | Lignes avant nettoyage | Dashboard |
| rows_after | int | Lignes apres nettoyage | Dashboard |
| cols_before | int | Colonnes avant nettoyage | Dashboard |
| cols_after | int | Colonnes apres nettoyage | Dashboard |
| nulls_removed | int | Valeurs manquantes traitees | Dashboard |
| duplicates_removed | int | Doublons supprimes | Dashboard |
| script_path | str ou null | Chemin du script ETL Python | Telechargement |
| report_md_path | str ou null | Chemin du rapport Markdown local | Telechargement |
| report_mdx_id | str ou null | ID du rapport MDX dans Directus | Lecture Directus |
| transformation_log | list[dict] | Journal des etapes executees | Audit |
| errors | list[str] | Erreurs non bloquantes | Debug |
| error_message | str ou null | Message d'erreur critique | Debug |

## Workflow (16 etapes)

1. **Validation Pydantic** de ETLRequest par FastAPI (automatique avant entree)
2. **load_dataset** depuis CSV, Excel, JSON ou Parquet avec detection automatique
3. **sanitize_column_names** : suppression des accents, minuscules, underscores
4. **generate_quality_report** label='before' (statistiques avant nettoyage)
5. **handle_missing_values** selon la strategie choisie (auto, constant, drop)
6. **remove_duplicates** avec rapport detaille
7. **fix_data_types** : conversion automatique des types object en datetime ou numeric
8. **detect_and_treat_outliers** sur les colonnes numeriques mesures (IQR ou Z-score)
9. **encode_categorical** sur les colonnes categorielles non protegees
10. **scale_features** sur les colonnes numeriques mesures non protegees
11. **create_features** si operations specifiees (age_from_date, ratio, difference)
12. **build_dimensional_model** si dimensional_modeling=True (Star Schema)
13. **generate_quality_report** label='after' (statistiques apres nettoyage)
14. **save_dataset** dans data/processed/{stem}/core_data/
15. **generate_markdown_report** retourne (content_str, path) pour push Directus
16. **generate_etl_script** si generate_script=True (script Python autonome)
17. **push_report_mdx** vers Directus (collection reports_mdx), stocke report_mdx_id
18. **Construction et retour de ETLResponse** Pydantic

## Capabilities

Lecture multi-format : CSV avec detection automatique du separateur et de l'encodage, Excel mono ou multi-feuilles, JSON avec plusieurs orientations, Parquet.

Nettoyage automatique : suppression des lignes entierement vides, suppression des colonnes trop lacunaires (taux nullite superieur a 50% par defaut), imputation intelligente selon le type (mediane pour numerique, mode pour categoriel, interpolation temporelle pour datetime).

Suppression des doublons avec rapport detaille sur les lignes supprimees.

Correction automatique des types : detection de colonnes object convertibles en datetime ou numerique avec seuil de tolerance de 20% de pertes.

Detection et traitement des outliers selon deux methodes (IQR avec 1.5xIQR, Z-score avec seuil 3) et trois actions (capping aux bornes, suppression des lignes, ajout d'une colonne indicateur).

Encodage categoriel automatique : LabelEncoder pour faible cardinalite (jusqu'a 10 valeurs uniques), OneHotEncoder pour cardinalite moyenne (jusqu'a 50 valeurs), exclusion des colonnes haute cardinalite (texte libre).

Normalisation des features numeriques : StandardScaler (moyenne 0, ecart-type 1) ou MinMaxScaler (intervalle 0-1).

Feature engineering : creation de features derivees (age depuis date, ratio entre colonnes, difference entre colonnes).

Suggestions automatiques via Gemini 2.5 Flash pour proposer 3 a 5 nouvelles features pertinentes basees sur le schema du dataset.

Modelisation dimensionnelle : construction automatique d'un Star Schema depuis une table plate avec detection des mesures et dimensions, generation des cles primaires et etrangeres.

Protection automatique des colonnes : IDs, emails, telephones, dates, noms, libelles uniques et annees ne sont jamais encodes ni scales.

Generation d'un script Python autonome reproduisant tout le pipeline applique, executable directement sur un nouveau dataset du meme format.

Generation d'un rapport Markdown comparatif avant/apres detaillant chaque transformation.

Publication automatique du rapport au format MDX dans Directus (collection reports_mdx) pour affichage dans le dashboard Next.js.

## Fichiers core/ (Logique Python pure)

| Fichier | Responsabilite |
|---------|----------------|
| cleaner.py | Chargement multi-format, nettoyage, gestion des valeurs manquantes, suppression des doublons, correction des types, detection des colonnes protegees |
| transformer.py | Encodage categoriel, normalisation, traitement des outliers, feature engineering, suggestions Gemini, construction du Star Schema |
| validator.py | Generation des rapports qualite avant/apres, validation de l'integrite referentielle des Star Schemas |
| exporter.py | Sauvegarde du dataset propre, generation du rapport Markdown, generation du script ETL reproductible |

## Fichiers scripts/ (Interface orchestrateur)

| Fichier | Responsabilite |
|---------|----------------|
| main.py | Point d'entree pour executor.py, validation Pydantic du plan JSON, wrapper synchrone, CLI standalone |
| logic.py | Orchestration des 16 etapes du pipeline, gestion des logs vers Directus, construction de l'ETLResponse |
| helpers.py | Fonctions utilitaires partagees (detect_file_format, infer_column_role, build_schema_summary, format_duration) |

## Exemple d'utilisation Python

```python
import asyncio
from schemas.etl import ETLRequest
from skills.etl_skill.scripts.logic import run_etl_pipeline

async def main():
    request = ETLRequest(
        session_id="user_42_2025-06-01_14-30-22",
        input_path="data/raw/customers.csv",
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

    response = await run_etl_pipeline(request)
    print(f"Status: {response.status}")
    print(f"Rows: {response.rows_before} -> {response.rows_after}")
    print(f"MDX report ID: {response.report_mdx_id}")

asyncio.run(main())
```

## Exemple d'appel TypeScript depuis Next.js

```typescript
import { getReportMDX } from '@/lib/directus'

const etlRequest = {
  session_id: 'user_42_2025-06-01_14-30-22',
  input_path: 'data/raw/customers.csv',
  missing_strategy: 'auto',
  fill_mode: 'smart',
  outlier_action: 'cap',
  generate_script: true,
  target_column: 'churn',
  columns_to_exclude: ['customer_id'],
}

const res = await fetch(`${process.env.NEXT_PUBLIC_FASTAPI_URL}/api/etl/run`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(etlRequest),
})
const data = await res.json()

// Lire le rapport MDX depuis Directus
if (data.report_mdx_id) {
  const report = await getReportMDX(data.report_mdx_id)
  console.log(report.content_mdx)
}
```

## Rapport MDX publie dans Directus

Le rapport MDX cree dans la collection `reports_mdx` contient :

- Tableau comparatif avant/apres (lignes, colonnes, taux nullite, doublons)
- Liste detaillee de toutes les transformations appliquees
- Statistiques descriptives apres nettoyage (mean, std, min, mediane, max)

L'ID retourne dans `report_mdx_id` permet a Next.js de lire le rapport via le SDK Directus et de le rendre avec le composant MDXRenderer.

## Limitations

Le Skill ne gere pas les sources SQL directes : il faut d'abord exporter en CSV ou Parquet avant de l'utiliser.

Les fichiers de plus de 2 GB ne sont pas optimises : le pipeline charge le dataset entier en memoire via pandas.

Le texte libre non structure (commentaires, descriptions longues) n'est pas traite par les transformations standards : les colonnes detectees comme texte sont automatiquement ignorees de l'encodage.

Les series temporelles complexes (avec saisonnalite, tendance, decomposition) ne sont pas gerees au-dela de la simple interpolation temporelle.

La modelisation dimensionnelle fonctionne mieux sur des datasets de plus de 500 lignes avec des colonnes categorielles bien distinctes.

Les suggestions Gemini necessitent une cle API valide configuree dans GEMINI_API_KEY : sans cle, le pipeline continue sans suggestions.

Le push vers Directus echoue silencieusement si DIRECTUS_TOKEN n'est pas configure : le pipeline complete son execution et retourne report_mdx_id=null.