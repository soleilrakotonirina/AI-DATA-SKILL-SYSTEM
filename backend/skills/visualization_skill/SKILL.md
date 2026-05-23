---
name: visualization-skill
description: Analyses a clean dataset and generates an intelligent BI dashboard with
  automatic KPIs, Power BI-style charts and a full MDX report. Classifies columns
  automatically (dimensions, measures, temporals, IDs, contacts, constants) and
  substitutes ID columns with their labels (id_cours -> nom_cours). Calls Gemini to
  plan coherent X/Y chart relations, falls back to local logic if quota exceeded.
  Stores Plotly JSON charts in Directus (collection charts) and publishes MDX report
  in Directus (collection reports_mdx). Adds an ID-to-label reference table on each
  chart that involves an identifier column. Use when the user asks for data
  visualization, EDA, exploratory analysis, correlation heatmap, distribution
  charts, KPIs, or automatic dashboard generation with Gemini narrative comments.
metadata:
  version: 2.0.0
  author: AI DATA SKILL SYSTEM
  endpoint: POST /api/visualization/eda
  pydantic_request: VisualizationRequest
  pydantic_response: VisualizationResponse
  directus_output: charts + reports_mdx
---

# Visualization Skill

## Description

Le Visualization Skill analyse le dataset propre produit par ETL Skill et genere
automatiquement un **dashboard BI intelligent** :

- **Classification automatique des colonnes** via `kpi_engine.py` : dimensions,
  mesures, temporelles, IDs, contacts, noms propres, constantes
- **Substitution ID → Libelle** : `id_cours` → `nom_cours`, `id_enseignant` →
  `nom_Enseignants` detectes automatiquement. L'ID reste reference interne mais
  n'apparait jamais dans les graphiques
- **Tableau de reference** a droite de chaque graphique impliquant un ID :
  `CRS001 : Comptabilite Generale`, `ENS005 : Martin Sophie`...
- **KPIs intelligents** calcules automatiquement
- **Plan de graphiques via Gemini** : choisit les meilleures relations X/Y.
  Fallback local intelligent si Gemini indisponible ou en quota
- **8 types de graphiques style Power BI** avec palette colorblind-friendly
- **Rotation automatique des cles Gemini** : bascule sur GEMINI_API_KEY_2,
  GEMINI_API_KEY_3... en cas de quota 429
- **Multi-fichiers** : fichier unique, dossier entier, ou pattern glob
- **Hierarchie de sortie** coherente avec ETL Skill

**Quand utiliser ce Skill** : quand l'utilisateur demande des graphiques, un
dashboard, une analyse exploratoire, des KPIs, la distribution des variables,
ou des insights automatiques sur un dataset.

**Endpoint FastAPI** : `POST /api/visualization/eda`

---

## Inputs

| Parametre          | Type         | Defaut           | Obligatoire | Description                                 |
|--------------------|--------------|------------------|-------------|---------------------------------------------|
| session_id         | str          | —                | Oui         | ID de session Directus                      |
| dataset_path       | str          | —                | Oui         | Chemin du dataset propre (output ETL Skill) |
| target_column      | str \| null  | null             | Non         | Colonne cible ML pour analyse supervisee    |
| question           | str \| null  | null             | Non         | Question analytique en langage naturel      |
| export_formats     | list[str]    | ["html", "png"]  | Non         | Formats d'export : html et/ou png          |
| output_dir         | str          | "outputs/charts" | Non         | Dossier de sortie (override auto-hierarchie)|
| generate_report    | bool         | true             | Non         | Generer et pousser le rapport EDA MDX       |
| gemini_comments    | bool         | true             | Non         | Activer Gemini (plan + commentaires)        |
| columns_to_include | list \| null | null             | Non         | Colonnes a analyser. null = toutes          |

---

## Outputs

| Cle              | Type          | Description                                     | Destination          |
|------------------|---------------|-------------------------------------------------|----------------------|
| skill            | str           | "Visualization"                                 | —                    |
| session_id       | str           | ID de session                                   | —                    |
| status           | str           | "success" ou "error"                            | —                    |
| charts           | ChartResult[] | Liste avec chart_ids Directus                   | Directus charts      |
| stats            | dict          | KPIs + distributions + stats mesures + evolution| —                    |
| eda_report_path  | str \| null   | Chemin local du rapport MDX genere              | —                    |
| report_mdx_id    | str \| null   | ID du rapport MDX dans Directus                 | Directus reports_mdx |
| charts_paths     | dict          | {title: {html: path, png: path}}                | Local                |
| gemini_comments  | dict          | {title: commentaire_gemini}                     | —                    |
| errors           | list[str]     | Erreurs non bloquantes                          | —                    |

---

## Workflow — 11 etapes

1.  **Chargement** : `_load_dataset()` charge CSV/Excel/JSON/Parquet en DataFrame
2.  **Calcul chemins** : hierarchie `outputs/charts/{groupe}/{stem}/` et
    `outputs/rapport_eda/{groupe}/{stem}/` extraite depuis le chemin ETL
3.  **Analyse** : `analyser_et_planifier()` orchestre classification + planification
    - `classifier_colonnes()` → entites / mesures / temporelles / exclues
    - `detecter_mappings_id_label()` → {id_cours: nom_cours, id_enseignant: nom_Enseignants}
    - `calculer_kpis()` → KPIs intelligents
    - Appel Gemini → plan JSON (type, x, y, color, titre, ordre_x...)
    - Si quota → `plan_graphiques_local()` fallback local intelligent
    - `_appliquer_mappings_id()` → substitue IDs par libelles dans le plan
4.  **Graphiques** : `build_intelligent_charts()` genere les figures Plotly
    - `_ajouter_reference_ids()` ajoute un tableau ID→Libelle a droite si besoin
5.  **Correlation** : `compute_correlation_matrix()` identifie les paires |r| > 0.8
6.  **Commentaires** : `get_gemini_chart_comment()` genere 2-3 phrases par graphique
7.  **Resume** : `get_gemini_eda_summary()` produit 4-6 points cles executifs
8.  **Export** : `export_all_charts()` sauvegarde HTML + PNG dans la hierarchie
9.  **Push charts** : `serialize_chart_json()` + `push_chart()` → Directus `charts`
10. **Rapport MDX** : `generate_mdx_report()` assemble le rapport complet
    (frontmatter, score_global, KPIs, stats, distributions, evolution, graphiques)
11. **Push MDX** : `push_report_mdx()` → Directus `reports_mdx`

---

## Types de graphiques

| Type          | Quand l'utiliser                             | Exemple concret                         |
|---------------|----------------------------------------------|-----------------------------------------|
| `donut`       | Dimension 2-5 valeurs                        | Repartition par sexe (M/F)              |
| `bar` count   | Dimension <= 20 valeurs, axe Y = count       | Inscriptions par niveau_etude           |
| `bar` mesure  | Dimension x mesure agregee (mean/sum)        | Salaire moyen par grade enseignant      |
| `stacked_bar` | 2 dimensions croisees, Y = count             | Niveau d'etude x statut par sexe        |
| `boxplot`     | Dimension x mesure, distribution complete    | Credits ECTS par niveau_etude           |
| `line`        | Temporelle ou ordonnee x count ou mesure     | Evolution des inscriptions par annee    |
| `heatmap`     | 2 dimensions <= 8 valeurs chacune x count    | Specialisation x specialite enseignant  |
| `scatter`     | 2 mesures numeriques                         | credits_ects vs volume_horaire          |

**A eviter** : graphiques 3D, double axe Y, pie charts > 6 categories,
ID brut comme axe X (automatiquement remplace par libelle).

---

## Classification automatique des colonnes (kpi_engine.py)

| Categorie       | Criteres de detection                           | Traitement                        |
|-----------------|-------------------------------------------------|-----------------------------------|
| **Entites**     | Texte analytique, cardinalite 2-60              | Axe X ou couleur des graphiques   |
| **Mesures**     | Numerique reel, variance > 0, non-ID            | Axe Y des graphiques              |
| **Temporelles** | Annee (1900-2100), mots-cles date/annee         | Axe X des line charts             |
| **IDs**         | Commence par id_, finit par _id, sequentiel     | Exclu — remplace par libelle      |
| **Contacts**    | email, telephone, mobile, portable              | Exclu automatiquement             |
| **Constantes**  | < 2 valeurs uniques                             | Exclu automatiquement             |
| **Noms propres**| nom, prenom, firstname, lastname                | Exclu des axes graphiques         |

---

## Substitution ID → Libelle

Detection automatique des paires referentiel (meme cardinalite) :

```
id_cours      (20 val.) → nom_cours       (20 val.) ✓ score=4
id_enseignant (12 val.) → nom_Enseignants (12 val.) ✓ score=4
id_etudiant   (168 val.)→ pas de libelle a cardinalite egale  ✗
```

Tous les graphiques affichent `Comptabilite Generale` au lieu de `CRS001`.
Un **tableau de reference** apparait automatiquement a droite :

```
📋 Id Cours
CRS001 : Comptabilite Generale
CRS002 : Analyse Financiere
CRS003 : Management Strategique
...
```

---

## Hierarchie de sortie

Coherente avec la hierarchie ETL Skill :

```
ETL input  : data/processed/Donnees_Universitaires/mapping_tables/xxx.csv
             └─ groupe = "Donnees_Universitaires", stem = "xxx"

Viz output :
  outputs/charts/Donnees_Universitaires/xxx/
    ├── 01_donut_statut.html
    ├── 01_donut_statut.png
    ├── 02_bar_niveau_etude.html
    └── ...

  outputs/rapport_eda/Donnees_Universitaires/xxx/
    └── eda_report_xxx.md
```

---

## Rapport MDX genere

```markdown
---
title: Rapport EDA — {dataset_name}
date: {date}
score_global: {0-100}
---

## Resume Executif
<KeyPoints>
- {points Gemini ou automatiques}
</KeyPoints>

## KPI Principaux
| 📚 Total Inscriptions | 353   |
| ✅ Taux de Validation | 21.0% |
| 💰 Salaire Moyen      | 60 324,96 |

## Statistiques Numeriques
## Statistiques Categorielles   ← toutes les dimensions
## Evolution Temporelle         ← colonnes temporelles
## Graphiques EDA               ← avec <ChartEmbed> et commentaires
## Conclusions et Recommandations
```

---

## Capabilities

- 8 types de graphiques style Power BI : donut, bar count, bar mesure,
  stacked_bar, boxplot, line, heatmap, scatter
- Palette colorblind-friendly : #0078D4, #107C10, #A80000, #FFB900, #8764B8
- Couleurs semantiques automatiques : statut (vert=Valide, bleu=En cours,
  orange=Inscrit, rouge=Abandonne), sexe (bleu=M, rouge=F)
- Substitution automatique ID → Libelle dans tous les graphiques
- Tableau de reference ID → Libelle a droite de chaque graphique concerne
- Rotation automatique des cles Gemini (GEMINI_API_KEY → _2 → _3... → _20)
- Fallback local intelligent si Gemini indisponible
- KPIs intelligents : count, nunique, mean, sum, pct_value=XXX
- Score global du dataset (0-100) calcule sur completude + volume + richesse
- Export HTML autonome (include_plotlyjs='cdn') + PNG (kaleido)
- Rapport MDX complet avec score_global, KPIs, distributions, evolution temporelle
- Multi-fichiers : fichier unique / dossier entier / pattern glob
- Hierarchie de sortie coherente avec ETL Skill

---

## Fichiers core/

| Fichier                | Lignes | Responsabilite                                                         |
|------------------------|--------|------------------------------------------------------------------------|
| `kpi_engine.py`        | 609    | Classification colonnes, detection mappings ID→Libelle, calcul KPIs, plan local |
| `eda.py`               | 190    | Correlation Pearson, stats descriptives, analyse cible, patterns       |
| `charts.py`            | 875    | 8 types de graphiques Plotly style Power BI                            |
| `dashboard_builder.py` | 513    | Plan Gemini + fallback + substitution IDs + reference tableau          |
| `exporter.py`          | 561    | Export HTML/PNG, serialisation JSON, rapport MDX complet               |

## Fichiers scripts/

| Fichier      | Lignes | Responsabilite                                                              |
|--------------|--------|-----------------------------------------------------------------------------|
| `main.py`    | 235    | CLI multi-fichiers (fichier/dossier/glob) + executor.py entry point         |
| `logic.py`   | 362    | Pipeline 11 etapes, hierarchie sorties, passage mappings_id aux charts      |
| `helpers.py` | 133    | build_chart_stats_summary, sanitize_filename, get_plotly_color_palette      |

---

## Exemple Python

```python
import asyncio
from schemas.visualization import VisualizationRequest
from skills.visualization_skill.scripts.logic import run_visualization_pipeline

request = VisualizationRequest(
    session_id="demo_session",
    dataset_path="data/processed/Donnees_Universitaires/mapping_tables/Donnees_Universitaires_JOINTE.csv",
    target_column=None,
    question="Quelles specialisations ont le meilleur taux de validation ?",
    export_formats=["html", "png"],
    generate_report=True,
    gemini_comments=True,
)

response = asyncio.run(run_visualization_pipeline(request))
print(f"Charts generees  : {len(response.charts)}")
print(f"KPIs calcules    : {len(response.stats.get('kpis_principaux', []))}")
print(f"report_mdx_id    : {response.report_mdx_id}")
print(f"Source plan      : {response.stats.get('source_plan')}")
for chart in response.charts:
    print(f"  [{chart.chart_type:12s}] {chart.title}")
```

## Exemple TypeScript Next.js

```typescript
// 1. Lancer le Visualization Skill via FastAPI
const res = await fetch(
  `${process.env.NEXT_PUBLIC_FASTAPI_URL}/api/visualization/eda`,
  {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id:      sessionId,
      dataset_path:    etlResponse.dataset_path,
      question:        userQuestion,
      gemini_comments: true,
      generate_report: true,
    }),
  }
)
const data = await res.json()
// data.stats.kpis_principaux  → KPIs pour le dashboard
// data.stats.source_plan      → "gemini" ou "local"

// 2. Rendre chaque graphique depuis Directus
for (const chart of data.charts) {
  // <PlotlyChart chartId={chart.chart_id} title={chart.title} />
}

// 3. Rendre le rapport MDX depuis Directus
// <MDXRenderer reportId={data.report_mdx_id} />
```

## Exemple CLI

```bash
# Fichier unique
uv run --env-file .env python -m skills.visualization_skill.scripts.main \
  --input data/processed/Donnees_Universitaires/mapping_tables/Donnees_Universitaires_JOINTE.csv \
  --session-id session_viz_jointe

# Dossier entier (tous les CSV/Excel/Parquet en recursif)
uv run --env-file .env python -m skills.visualization_skill.scripts.main \
  --input data/processed/Donnees_Universitaires/ \
  --session-id session_viz_all

# Glob — seulement les core_data
uv run --env-file .env python -m skills.visualization_skill.scripts.main \
  --input "data/processed/Donnees_Universitaires/core_data/*" \
  --session-id session_viz_core

# Sans Gemini (fallback local, plus rapide, pas de quota)
uv run --env-file .env python -m skills.visualization_skill.scripts.main \
  --input data/processed/Donnees_Universitaires/mapping_tables/Donnees_Universitaires_JOINTE.csv \
  --session-id session_viz_local \
  --no-gemini
```

---

## Limitations

- Graphiques 3D non supportes.
- Datasets > 500 000 lignes : sampling recommande avant d'appeler ce Skill.
- Cartes geo (choropleth, mapbox) non incluses dans cette version.
- Export PNG necessite kaleido (`pip install kaleido`). Sans kaleido : HTML uniquement.
- Commentaires Gemini et plan Gemini necessitent au moins une GEMINI_API_KEY dans `.env`.
- Sans aucune cle Gemini, le plan utilise automatiquement le fallback local.
- Directus optionnel : si indisponible, les graphiques sont exportes localement
  et le rapport MDX est sauvegarde dans `outputs/rapport_eda/`.