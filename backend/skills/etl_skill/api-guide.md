# API Guide — ETL Skill

Guide d'integration complet pour appeler le ETL Skill depuis Next.js, depuis un autre Skill, ou en mode standalone.

## Sommaire

1. [Installation des dependances](#installation-des-dependances)
2. [Variables d'environnement](#variables-denvironnement)
3. [Format du plan JSON](#format-du-plan-json)
4. [3 exemples de plans JSON](#3-exemples-de-plans-json)
5. [Format de la reponse ETLResponse](#format-de-la-reponse-etlresponse)
6. [Appel depuis Next.js (TypeScript)](#appel-depuis-nextjs-typescript)
7. [Streaming SSE des logs](#streaming-sse-des-logs)
8. [Troubleshooting](#troubleshooting)

---

## Installation des dependances

Toutes les dependances sont listees dans `backend/requirements.txt`. Installation en une seule commande.

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Verification.

```bash
python -c "import fastapi, pydantic, pandas, numpy, sklearn, shap, plotly, httpx; print('OK')"
```

Dependances specifiques au ETL Skill :

| Librairie | Version | Role |
|-----------|---------|------|
| pandas | >= 2.2.3 | Manipulation des donnees |
| numpy | >= 2.0.0 | Calcul numerique |
| scikit-learn | >= 1.5.0 | LabelEncoder, OneHotEncoder, StandardScaler, MinMaxScaler |
| openpyxl | >= 3.1.3 | Lecture des fichiers Excel |
| pyarrow | >= 16.0.0 | Lecture des fichiers Parquet |
| pydantic | >= 2.7.0 | Validation des schemas |
| httpx | >= 0.27.0 | Client HTTP Directus |
| google-genai | >= 1.0.0 | SDK Gemini pour suggestions IA |
| fastapi | >= 0.110.0 | Endpoint POST /api/etl/run |

---

## Variables d'environnement

Configuration dans `backend/.env`. Voir `backend/.env.example` pour le template complet.

```bash
# Cle API Gemini (obtenue sur https://aistudio.google.com)
GEMINI_API_KEY=AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

# URL et token Directus (genere dans Settings > Access Tokens)
DIRECTUS_URL=http://localhost:8055
DIRECTUS_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Configuration FastAPI
FASTAPI_PORT=8000
CORS_ORIGINS=http://localhost:3000

# Configuration ETL (optionnelles, surchargees par ETLRequest)
ETL_NULL_THRESHOLD=0.5
ETL_NUMERIC_IMPUTATION=median
ETL_CATEGORICAL_IMPUTATION=mode
ETL_IQR_MULTIPLIER=1.5
```

---

## Format du plan JSON

Le plan JSON est recu par `scripts/main.py` depuis l'orchestrateur Gemini (`executor.py`). Structure exacte.

```json
{
  "step": 1,
  "skill": "ETL",
  "endpoint": "/api/etl/run",
  "params": {
    "session_id": "string (obligatoire)",
    "input_path": "string (obligatoire)",
    "missing_strategy": "auto | constant | drop",
    "fill_mode": "smart | constant",
    "outlier_action": "cap | remove | flag",
    "outlier_method": "iqr | zscore",
    "encode_method": "auto | label | onehot",
    "scale_method": "standard | minmax",
    "generate_script": true,
    "dimensional_modeling": false,
    "target_column": "string ou null",
    "columns_to_exclude": ["liste de colonnes a exclure"]
  }
}
```

### Description de chaque parametre

**session_id** : Identifiant unique cree dans Directus via `create_session()`. Permet de regrouper tous les rapports, charts et logs d'un meme pipeline.

**input_path** : Chemin relatif depuis la racine `backend/` du fichier source. Formats acceptes : `.csv`, `.tsv`, `.txt`, `.xlsx`, `.xlsm`, `.xls`, `.json`, `.parquet`.

**missing_strategy** :
- `auto` : imputation intelligente selon le type (mediane, mode, ffill)
- `constant` : valeurs fixes (0 pour numerique, "N/D" pour texte)
- `drop` : suppression des lignes avec valeurs manquantes

**fill_mode** :
- `smart` : strategie adaptee au type de colonne
- `constant` : remplissage par valeurs fixes uniquement

**outlier_action** :
- `cap` : valeurs hors bornes ramenees aux bornes
- `remove` : lignes contenant des outliers supprimees
- `flag` : ajout d'une colonne booleenne `{col}_is_outlier`

**outlier_method** :
- `iqr` : bornes Q1 - 1.5*IQR et Q3 + 1.5*IQR (recommande pour distributions asymetriques)
- `zscore` : valeurs avec |zscore| > 3 (recommande pour distributions normales)

**encode_method** :
- `auto` : LabelEncoder si cardinalite <= 10, sinon OneHotEncoder
- `label` : LabelEncoder force sur toutes les colonnes
- `onehot` : OneHotEncoder force sur toutes les colonnes

**scale_method** :
- `standard` : StandardScaler (moyenne 0, ecart-type 1)
- `minmax` : MinMaxScaler (intervalle [0, 1])

**generate_script** : Si `true`, un script Python autonome est genere dans `outputs/rapport_etl/{stem}/etl_script_{stem}.py`.

**dimensional_modeling** : Si `true`, le pipeline tente de construire un Star Schema avec table de faits et tables de dimensions.

**target_column** : Nom de la colonne cible ML. Elle est protegee : non encodee, non scalee, conservee dans son format original.

**columns_to_exclude** : Liste de colonnes a exclure de toutes les transformations (IDs personnalises, identifiants metier, etc.).

---

## 3 exemples de plans JSON

### Exemple 1 : CSV simple (parametres par defaut)

```json
{
  "step": 1,
  "skill": "ETL",
  "endpoint": "/api/etl/run",
  "params": {
    "session_id": "user_demo_2026-05-14",
    "input_path": "data/raw/customers.csv"
  }
}
```

### Exemple 2 : Excel avec modelisation dimensionnelle

```json
{
  "step": 1,
  "skill": "ETL",
  "endpoint": "/api/etl/run",
  "params": {
    "session_id": "user_42_2026-05-14",
    "input_path": "data/raw/sales_2025.xlsx",
    "missing_strategy": "auto",
    "fill_mode": "smart",
    "outlier_action": "cap",
    "outlier_method": "iqr",
    "encode_method": "auto",
    "scale_method": "standard",
    "generate_script": true,
    "dimensional_modeling": true,
    "target_column": null,
    "columns_to_exclude": ["transaction_id", "client_email"]
  }
}
```

### Exemple 3 : Cible ML avec exclusions et scaling minmax

```json
{
  "step": 1,
  "skill": "ETL",
  "endpoint": "/api/etl/run",
  "params": {
    "session_id": "ml_pipeline_churn_2026",
    "input_path": "data/raw/customers_churn.csv",
    "missing_strategy": "auto",
    "fill_mode": "smart",
    "outlier_action": "cap",
    "outlier_method": "iqr",
    "encode_method": "onehot",
    "scale_method": "minmax",
    "generate_script": true,
    "dimensional_modeling": false,
    "target_column": "churn",
    "columns_to_exclude": ["customer_id", "email", "phone"]
  }
}
```

---

## Format de la reponse ETLResponse

Structure JSON retournee par `POST /api/etl/run` (validee par Pydantic).

```json
{
  "skill": "ETL",
  "session_id": "user_42_2026-05-14",
  "status": "success",
  "rows_before": 210,
  "rows_after": 190,
  "cols_before": 9,
  "cols_after": 12,
  "nulls_removed": 45,
  "duplicates_removed": 10,
  "script_path": "outputs/rapport_etl/customers/etl_script_customers.py",
  "report_md_path": "outputs/rapport_etl/customers/etl_report_customers.md",
  "report_mdx_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "transformation_log": [
    {
      "etape": "load_dataset",
      "fonction": "load_dataset",
      "params": {"input_path": "data/raw/customers.csv"},
      "rows_before": 210,
      "rows_after": 210,
      "duration_ms": 87.3
    }
  ],
  "errors": [],
  "error_message": null
}
```

### Description de chaque cle

**skill** : Toujours `"ETL"` pour identifier le Skill source.

**session_id** : Echo de `params.session_id` pour traçabilite.

**status** :
- `"success"` : pipeline complet, aucune erreur critique
- `"error"` : echec critique (fichier introuvable, format non supporte)

**rows_before / rows_after** : Nombre de lignes avant et apres nettoyage.

**cols_before / cols_after** : Nombre de colonnes avant et apres (l'encodage OneHot peut augmenter le nombre de colonnes).

**nulls_removed** : Nombre total de valeurs manquantes traitees.

**duplicates_removed** : Nombre de lignes dupliquees supprimees.

**script_path** : Chemin du script Python reproductible si `generate_script=true`, sinon `null`.

**report_md_path** : Chemin du rapport Markdown local genere.

**report_mdx_id** : ID UUID du rapport MDX publie dans Directus. Permet a Next.js de lire le rapport via le SDK Directus.

**transformation_log** : Journal detaille de chaque etape executee avec timings.

**errors** : Liste des erreurs non bloquantes rencontrees pendant l'execution.

**error_message** : Message d'erreur critique si `status="error"`, sinon `null`.

---

## Appel depuis Next.js (TypeScript)

```typescript
// frontend/lib/fastapi.ts
import type { ETLRequest, ETLResponse } from '@/types/etl'

export async function runETL(request: ETLRequest): Promise<ETLResponse> {
  const response = await fetch(
    `${process.env.NEXT_PUBLIC_FASTAPI_URL}/api/etl/run`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    }
  )

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'ETL request failed')
  }

  return response.json()
}
```

```typescript
// frontend/lib/directus.ts
import { createDirectus, rest, readItems } from '@directus/sdk'

const directus = createDirectus(process.env.NEXT_PUBLIC_DIRECTUS_URL!).with(rest())

export async function getReportMDX(reportId: string) {
  const results = await directus.request(readItems('reports_mdx', {
    filter: { id: { _eq: reportId } },
  }))
  return results[0]
}
```

```typescript
// frontend/app/upload/page.tsx (extrait)
'use client'

import { useState } from 'react'
import { runETL } from '@/lib/fastapi'
import { getReportMDX } from '@/lib/directus'
import { MDXRenderer } from '@/components/MDXRenderer'

export default function UploadPage() {
  const [response, setResponse] = useState<any>(null)
  const [report, setReport] = useState<any>(null)

  async function handleSubmit(filepath: string) {
    const etlResponse = await runETL({
      session_id: `session_${Date.now()}`,
      input_path: filepath,
      missing_strategy: 'auto',
      fill_mode: 'smart',
      outlier_action: 'cap',
      generate_script: true,
      dimensional_modeling: false,
      target_column: null,
      columns_to_exclude: [],
    })
    setResponse(etlResponse)

    if (etlResponse.report_mdx_id) {
      const mdxReport = await getReportMDX(etlResponse.report_mdx_id)
      setReport(mdxReport)
    }
  }

  return (
    <div>
      {response && (
        <div>
          <p>Lignes : {response.rows_before} -> {response.rows_after}</p>
          <p>Nulls supprimes : {response.nulls_removed}</p>
          <p>Doublons : {response.duplicates_removed}</p>
        </div>
      )}
      {report && <MDXRenderer content={report.content_mdx} />}
    </div>
  )
}
```

---

## Streaming SSE des logs

Les logs d'execution sont diffuses en temps reel via Server-Sent Events depuis `GET /api/logs/stream?session_id={id}`.

```typescript
// frontend/lib/hooks/useSSE.ts
import { useEffect, useState } from 'react'

export function useSSE(url: string) {
  const [logs, setLogs] = useState<string[]>([])

  useEffect(() => {
    const eventSource = new EventSource(url)
    eventSource.onmessage = (e) => setLogs(prev => [...prev, e.data])
    eventSource.onerror = () => eventSource.close()
    return () => eventSource.close()
  }, [url])

  return { logs }
}
```

Utilisation dans un composant.

```typescript
const { logs } = useSSE(
  `${process.env.NEXT_PUBLIC_FASTAPI_URL}/api/logs/stream?session_id=${sessionId}`
)

return (
  <pre>
    {logs.map((line, i) => <div key={i}>{line}</div>)}
  </pre>
)
```

---

## Troubleshooting

### Erreur : `DIRECTUS_TOKEN non configure`

Le pipeline complete son execution mais `report_mdx_id` est `null`.

**Solution** : Generer un token admin dans Directus (Settings > Access Tokens) et le copier dans `backend/.env` sur la ligne `DIRECTUS_TOKEN=`. Redemarrer le serveur FastAPI.

### Erreur 404 : `Fichier introuvable`

Le chemin specifie dans `input_path` n'existe pas.

**Solution** : Verifier le chemin relatif depuis `backend/`. Exemple correct : `data/raw/customers.csv` (le fichier doit etre dans `backend/data/raw/customers.csv`).

### Erreur 422 : `Validation Pydantic echouee`

Les parametres envoyes ne respectent pas le schema ETLRequest.

**Solution** : Verifier que `session_id` et `input_path` sont presents et non vides. Verifier que les enums sont respectes (`missing_strategy` doit etre `auto`, `constant` ou `drop`).

### Pas de suggestions Gemini dans le rapport

`GEMINI_API_KEY` n'est pas configure ou la cle est invalide.

**Solution** : Obtenir une cle gratuite sur https://aistudio.google.com (Get API Key) et la coller dans `backend/.env` sur la ligne `GEMINI_API_KEY=`.

### Erreur : `Format non supporte`

L'extension du fichier n'est pas dans la liste des formats acceptes.

**Solution** : Formats acceptes : `.csv`, `.tsv`, `.txt`, `.xlsx`, `.xlsm`, `.xls`, `.json`, `.parquet`. Convertir le fichier au format CSV si necessaire.

### Le rapport MDX ne s'affiche pas dans Next.js

`report_mdx_id` est renseigne mais l'affichage echoue.

**Solution** : Verifier que le token Directus utilise cote Next.js (`DIRECTUS_TOKEN` dans `frontend/.env.local`) a les permissions de lecture sur la collection `reports_mdx`.

### Memoire saturee sur fichiers > 1 GB

Le pipeline charge le dataset entier en memoire.

**Solution** : Pre-decouper le fichier en chunks via pandas ou utiliser un format plus compact comme Parquet. Pour des fichiers tres volumineux, prevoir un Skill dedie au streaming (non disponible en v1.0).