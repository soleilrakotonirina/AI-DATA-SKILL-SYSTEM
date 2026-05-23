# API Guide — Visualization Skill

## Installation des dependances

```bash
cd backend
source .venv/bin/activate
pip install plotly>=5.22.0 matplotlib>=3.9.0 kaleido>=0.2.1 google-genai>=1.0.0 scipy
```

> `kaleido` est optionnel. Sans lui, seul le format HTML est disponible pour l'export.

---

## Variables d'environnement requis

```bash
# backend/.env
GEMINI_API_KEY=AIzaSy...       # Cle API Gemini — commentaires narratifs
DIRECTUS_URL=http://localhost:8055
DIRECTUS_TOKEN=votre_token_admin
```

---

## Ajouter le router au main.py FastAPI

```python
# backend/api/main.py
from api.routes.visualization import router as visualization_router
app.include_router(visualization_router, prefix="/api")
```

---

## Endpoint

### POST /api/visualization/eda

Lance le Visualization Skill complet : EDA, graphiques Plotly, commentaires Gemini,
rapport MDX. Stocke les resultats dans Directus.

---

## Format du Plan JSON (recu par scripts/main.py depuis executor.py)

```json
{
  "step": 2,
  "skill": "Visualization",
  "endpoint": "/api/visualization/eda",
  "params": {
    "session_id":          "user_42_2025-06-01_14-30-22",
    "dataset_path":        "data/processed/clean_data/core_data/clean_data.csv",
    "target_column":       null,
    "question":            null,
    "export_formats":      ["html", "png"],
    "output_dir":          "outputs/charts",
    "generate_report":     true,
    "gemini_comments":     true,
    "columns_to_include":  null
  }
}
```

### Description des parametres

| Parametre          | Type         | Defaut           | Description                                         |
|--------------------|--------------|------------------|-----------------------------------------------------|
| session_id         | string       | —                | ID de session Directus (obligatoire)                |
| dataset_path       | string       | —                | Chemin CSV/Excel propre, output ETL Skill           |
| target_column      | string\|null | null             | Colonne cible ML pour analyse supervisee            |
| question           | string\|null | null             | Question en langage naturel — filtre les graphiques |
| export_formats     | string[]     | ["html","png"]   | "html" et/ou "png" (kaleido requis pour png)        |
| output_dir         | string       | "outputs/charts" | Dossier de sortie des graphiques exportes           |
| generate_report    | boolean      | true             | Generer et pousser le rapport EDA MDX vers Directus |
| gemini_comments    | boolean      | true             | Commentaires narratifs Gemini par graphique         |
| columns_to_include | string[]\|null| null            | Colonnes a analyser. null = toutes                  |

---

## Exemples de plans JSON

### Exemple 1 — EDA simple (toutes les colonnes)

```json
{
  "step": 2,
  "skill": "Visualization",
  "endpoint": "/api/visualization/eda",
  "params": {
    "session_id":   "session_001",
    "dataset_path": "data/processed/exportations_madagascar/core_data/exportations_dirty.csv",
    "generate_report": true,
    "gemini_comments": false
  }
}
```

### Exemple 2 — EDA avec question analytique

```json
{
  "step": 2,
  "skill": "Visualization",
  "endpoint": "/api/visualization/eda",
  "params": {
    "session_id":   "session_002",
    "dataset_path": "data/processed/sales/core_data/sales.csv",
    "question":     "Quels produits generent le plus de revenus par region ?",
    "gemini_comments": true,
    "generate_report": true
  }
}
```

### Exemple 3 — EDA avec variable cible (ML supervise)

```json
{
  "step": 2,
  "skill": "Visualization",
  "endpoint": "/api/visualization/eda",
  "params": {
    "session_id":      "session_churn_003",
    "dataset_path":    "data/processed/clients/core_data/clients.csv",
    "target_column":   "churn",
    "question":        "Quelles variables distinguent le mieux les clients qui churnent ?",
    "export_formats":  ["html"],
    "gemini_comments": true,
    "generate_report": true
  }
}
```

---

## Format de VisualizationResponse

```json
{
  "skill":           "Visualization",
  "session_id":      "session_001",
  "status":          "success",
  "charts": [
    {
      "chart_id":           "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "title":              "Distribution de age",
      "chart_type":         "histogram",
      "columns_involved":   ["age"]
    },
    {
      "chart_id":           "b2c3d4e5-f6a7-8901-bcde-f12345678901",
      "title":              "Distribution de salaire",
      "chart_type":         "histogram",
      "columns_involved":   ["salaire"]
    }
  ],
  "stats": {
    "numeric_stats": {
      "age": {
        "mean": 35.2, "std": 10.1, "min": 18.0,
        "q25": 27.0, "q50": 35.0, "q75": 43.0,
        "max": 75.0, "skewness": 0.12, "kurtosis": -0.3,
        "null_count": 0, "null_pct": 0.0
      }
    },
    "categorical_stats": {
      "region": {
        "n_unique": 6,
        "null_count": 2,
        "null_pct": 0.5,
        "top_values": [
          {"value": "Analamanga", "count": 350, "pct": 25.0}
        ]
      }
    }
  },
  "eda_report_path": "outputs/rapport_eda/exportations_dirty/eda_report_exportations_dirty.md",
  "report_mdx_id":   "c3d4e5f6-a7b8-9012-cdef-123456789012",
  "charts_paths": {
    "Distribution de age": {
      "html": "outputs/charts/01_histogram_age.html",
      "png":  "outputs/charts/01_histogram_age.png"
    }
  },
  "gemini_comments": {
    "Distribution de age": "La distribution des ages presente une forme quasi-normale centree sur 35 ans avec une legere asymetrie positive. La majorite des clients sont entre 27 et 43 ans."
  },
  "errors": [],
  "error_message": null
}
```

### Description des cles de reponse

| Cle             | Type      | Description                                                    |
|-----------------|-----------|----------------------------------------------------------------|
| skill           | string    | Toujours "Visualization"                                       |
| session_id      | string    | ID de session                                                  |
| status          | string    | "success" ou "error"                                           |
| charts          | array     | Liste ChartResult avec chart_ids Directus                      |
| stats           | object    | Statistiques EDA (numeric_stats + categorical_stats)           |
| eda_report_path | string    | Chemin local du fichier MDX                                    |
| report_mdx_id   | string    | UUID Directus du rapport MDX — utiliser pour MDXRenderer.tsx   |
| charts_paths    | object    | Chemins locaux HTML/PNG par titre de graphique                 |
| gemini_comments | object    | Commentaires narratifs par titre de graphique                  |
| errors          | array     | Erreurs non bloquantes (ex: chart Directus non pousse)         |

---

## Appel depuis Next.js (TypeScript)

```typescript
// frontend/lib/fastapi.ts

export interface ChartResult {
  chart_id:          string
  title:             string
  chart_type:        string
  columns_involved:  string[]
}

export interface VisualizationResponse {
  skill:             string
  session_id:        string
  status:            'success' | 'error'
  charts:            ChartResult[]
  stats:             Record<string, unknown>
  eda_report_path:   string | null
  report_mdx_id:     string | null
  charts_paths:      Record<string, Record<string, string>>
  gemini_comments:   Record<string, string>
  errors:            string[]
  error_message:     string | null
}

export async function runVisualization(
  sessionId: string,
  datasetPath: string,
  options?: {
    targetColumn?: string
    question?: string
    geminiComments?: boolean
  }
): Promise<VisualizationResponse> {
  const res = await fetch(
    `${process.env.NEXT_PUBLIC_FASTAPI_URL}/api/visualization/eda`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id:      sessionId,
        dataset_path:    datasetPath,
        target_column:   options?.targetColumn ?? null,
        question:        options?.question ?? null,
        gemini_comments: options?.geminiComments ?? true,
        generate_report: true,
        export_formats:  ['html', 'png'],
      }),
    }
  )
  if (!res.ok) {
    throw new Error(`Visualization Skill erreur : ${res.status}`)
  }
  return res.json()
}
```

```typescript
// Utilisation dans app/eda/page.tsx
const vizData = await runVisualization(
  sessionId,
  etlResponse.dataset_path,
  { question: userQuestion }
)

// Rendre les graphiques depuis Directus
for (const chart of vizData.charts) {
  // <PlotlyChart chartId={chart.chart_id} title={chart.title} />
}

// Rendre le rapport MDX depuis Directus
// <MDXRenderer reportId={vizData.report_mdx_id} />
```

---

## Streaming SSE des logs

```typescript
// frontend/app/eda/page.tsx
const { logs } = useSSE(
  `${process.env.NEXT_PUBLIC_FASTAPI_URL}/api/logs/stream?session_id=${sessionId}`
)
```

---

## CLI (tests et developpement)

```bash
# EDA simple
uv run --env-file .env python -m skills.visualization_skill.scripts.main \
  --input data/processed/exportations_madagascar/core_data/exportations_dirty.csv \
  --session-id test_viz_001

# EDA avec question et variable cible
uv run --env-file .env python -m skills.visualization_skill.scripts.main \
  --input data/processed/clients/core_data/clients.csv \
  --target churn \
  --question "Quelles variables distinguent le mieux les churners ?" \
  --session-id test_viz_002

# Sans commentaires Gemini (plus rapide)
uv run --env-file .env python -m skills.visualization_skill.scripts.main \
  --input data/processed/clean.csv \
  --no-gemini \
  --session-id test_viz_003
```

---

## Troubleshooting

### kaleido absent pour PNG

```bash
pip install kaleido
# Si version speciale requise :
pip install kaleido==0.2.1
```

### Erreurs API Gemini

- Verifier `GEMINI_API_KEY` dans `.env`
- Utiliser `--no-gemini` pour tester sans Gemini
- Les erreurs Gemini sont non bloquantes : le pipeline continue sans commentaires

### chart_ids Directus vides

- Verifier que `DIRECTUS_TOKEN` et `DIRECTUS_URL` sont dans `.env`
- Lancer avec `uv run --env-file .env` pour charger le `.env`
- Verifier que les collections `charts` et `reports_mdx` existent dans Directus

### Timeout sur grands datasets

- Utiliser `columns_to_include` pour limiter les colonnes analysees
- Desactiver `generate_report=false` et `gemini_comments=false` pour un test rapide