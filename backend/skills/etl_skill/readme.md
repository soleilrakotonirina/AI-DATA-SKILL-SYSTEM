# AI DATA SKILL SYSTEM — Etape 1 : ETL Skill

> **Session 3.1** | Construction du premier Skill du pipeline | Stack v2.0

---

## Objectif de cette etape

Construire le **premier Skill** du systeme : un module autonome de **nettoyage et transformation** des datasets bruts, qui sert de fondation a tous les Skills suivants (Visualization, Modeling, Analysis).

A l'issue de cette etape, le projet dispose de :
- Un endpoint FastAPI **POST /api/etl/run** valide par Pydantic v2
- Un pipeline ETL complet en **16 etapes** orchestrees par async/await
- Une publication automatique du **rapport MDX dans Directus** (collection `reports_mdx`)
- Une couverture **40+ tests unitaires** incluant FastAPI TestClient et mocks Directus/Gemini
- Un **script Python reproductible** genere automatiquement, executable sur tout nouveau dataset du meme format

Le pipeline transforme un dataset brut (CSV, Excel, JSON, Parquet) en dataset propre, audit complet, et rapport narratif lisible dans le dashboard Next.js.

---

## Stack technique de cette etape

| Composant | Technologie | Role |
|-----------|-------------|------|
| Backend | FastAPI 0.110+ | Endpoint POST /api/etl/run |
| Validation | Pydantic v2 | ETLRequest et ETLResponse |
| CMS | Directus 10+ | Stockage du rapport MDX |
| DB Directus | SQLite 3 | Base zero installation (fichier .db local) |
| IA | Gemini 2.5 Flash | Suggestions de transformations |
| Manipulation | pandas 2.2+, numpy 2.0+ | Nettoyage et transformation |
| ML preprocessing | scikit-learn 1.5+ | LabelEncoder, OneHotEncoder, StandardScaler |
| Tests | pytest 8+, pytest-asyncio | 40+ tests unitaires + endpoint |

---

## Demarrage rapide

### Pre-requis

```bash
python --version    # >= 3.10
node --version      # >= 18
npm --version       # >= 9
```

Cle Gemini gratuite a obtenir sur https://aistudio.google.com (Get API Key).

### 1. Backend FastAPI

```bash
cd backend
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
cp .env.example .env
# Renseigner GEMINI_API_KEY, DIRECTUS_URL, DIRECTUS_TOKEN
uvicorn api.main:app --reload --port 8000
```

Documentation interactive : http://localhost:8000/docs

### 2. Directus (Node.js natif + SQLite)

```bash
cd directus
npm init directus-project@latest .
npx directus start
```

Interface admin : http://localhost:8055

Creer les 5 collections (sessions, reports_mdx, charts, pipeline_logs, user_profiles) via l'interface, ou appliquer le snapshot.

```bash
npx directus schema apply ./snapshots/schema.json
```

Generer un token admin dans Settings > Access Tokens et le copier dans `backend/.env`.

### 3. Frontend Next.js

```bash
cd frontend
npm install
npm run dev
```

Interface : http://localhost:3000

### 4. Lancer le test de connexion

```bash
cd backend
source .venv/bin/activate
python tests/test_setup.py
```

Sortie attendue : `[OK] FastAPI` + `[OK] Directus Ping` + `[OK] Directus Auth` + `[OK] Next.js`.

---

## Structure du ETL Skill

Le ETL Skill suit la **separation core/ scripts/ examples/** definie dans le system prompt v2.0.

```
backend/
├── schemas/
│   └── etl.py                 ETLRequest et ETLResponse (Pydantic v2)
│
├── src/utils/
│   └── directus_client.py     Client HTTP async pour Directus
│
├── api/routes/
│   └── etl.py                 Endpoint POST /api/etl/run
│
├── skills/etl_skill/
│   ├── SKILL.md               Documentation LLM (frontmatter YAML)
│   ├── api-guide.md           Guide integration FastAPI + TypeScript
│   │
│   ├── core/                  Logique Python pure (testable seule)
│   │   ├── cleaner.py             Chargement multi-format + nettoyage
│   │   ├── transformer.py         Encodage, scaling, outliers, features
│   │   ├── normalizer.py           Normalisation schema + types + metriques
│   │   ├── star_schema.py         Construction d'un schema en etoile pour ML
│   │   ├── validator.py           Rapports qualite + integrite
│   │   └── exporter.py            Sauvegarde + rapport + script ETL
│   │
│   ├── scripts/               Interface orchestrateur
│   │   ├── main.py                Point d'entree pour executor.py + CLI
│   │   ├── logic.py               Pipeline async en 16 etapes
│   │   └── helpers.py             Utilitaires partages
│   │
│   └── examples/
│       ├── example_usage.py       Exemple complet avec dataset synthetique
│       ├── sample_config.json     Plan JSON d'exemple
│       └── expected_output.md     Description des sorties attendues
│
└── tests/
    └── test_etl.py            40+ tests unitaires + endpoint FastAPI
```

### Separation core/ vs scripts/

| Dossier | Role | Connaissance du systeme IA |
|---------|------|----------------------------|
| `core/` | Logique metier pure (pandas, sklearn) | Aucune. Testable seul, importable depuis n'importe ou. |
| `scripts/` | Pont entre orchestrateur et core | Connait l'ETLRequest, Directus, le push MDX, l'async/await. |

### Flux d'execution

```
Next.js
   │
   │  POST /api/etl/run avec ETLRequest JSON
   ▼
FastAPI api/routes/etl.py
   │
   │  Validation Pydantic automatique (422 si invalide)
   ▼
skills/etl_skill/scripts/logic.py
   │
   │  16 etapes orchestrees, appels async vers Directus
   ▼
skills/etl_skill/core/ (cleaner, transformer, validator, exporter)
   │
   │  Logique Python pure, retourne dataframes et metriques
   ▼
src/utils/directus_client.py
   │
   │  push_report_mdx() → Directus collection reports_mdx
   ▼
ETLResponse Pydantic
   │
   │  Retour HTTP 200 avec report_mdx_id
   ▼
Next.js getReportMDX(id) → MDXRenderer
```

---

## Tester le ETL Skill

### Via Swagger UI

Ouvrir http://localhost:8000/docs, deplier `POST /api/etl/run`, cliquer sur "Try it out", coller le JSON.

```json
{
  "session_id": "test_session_001",
  "input_path": "data/raw/customers.csv",
  "missing_strategy": "auto",
  "fill_mode": "smart",
  "outlier_action": "cap",
  "generate_script": true,
  "target_column": "churn",
  "columns_to_exclude": ["customer_id"]
}
```

### Via CLI (mode standalone)

```bash
cd backend
source venv/bin/activate

# Avec un plan JSON complet
uv run python -m skills.etl_skill.scripts.main --plan skills/etl_skill/examples/sample_config.json

# Avec juste un fichier (autres params par defaut)

uv run --env-file .env python -m skills.etl_skill.scripts.main   --input data/raw/Donnees_Universitaires.csv   --session-id session_star_report

# Avec URL (exemple avec API dummyjson)
uv run --env-file .env python -m skills.etl_skill.scripts.main --url "https://dummyjson.com/products?limit=30&skip=0" --session-id session_dummyjson_test

```

### Via l'exemple Python

```bash
uv run --env-file .env python -m skills.etl_skill.examples.example_usage
```

Cet exemple cree un dataset synthetique avec des problemes de qualite, execute le pipeline complet (Directus mocke), et affiche le rapport comparatif avant/apres.

### Via Next.js

Aller sur http://localhost:3000/upload, uploader un fichier CSV, observer le rapport MDX se generer en direct.

### Via les tests

```bash
cd backend
uv run --env-file .env  pytest tests/test_etl.py -v
uv run --env-file .env pytest tests/test_etl.py --cov=skills/etl_skill --cov-report=term-missing
```

Resultat attendu : **40+ tests passent**, couverture > 85%.

---

## Fichiers produits par cette etape

| Fichier | Type | Role |
|---------|------|------|
| `backend/schemas/etl.py` | Python | ETLRequest et ETLResponse Pydantic v2 |
| `backend/src/utils/directus_client.py` | Python | Client HTTP async Directus |
| `backend/api/routes/etl.py` | Python | Endpoint POST /api/etl/run |
| `backend/skills/etl_skill/core/cleaner.py` | Python | Chargement et nettoyage |
| `backend/skills/etl_skill/core/transformer.py` | Python | Encodage, scaling, outliers, features |
| `backend/skills/etl_skill/core/validator.py` | Python | Rapports qualite, integrite |
| `backend/skills/etl_skill/core/exporter.py` | Python | Sauvegarde, rapport, script ETL |
| `backend/skills/etl_skill/scripts/main.py` | Python | Point d'entree + CLI |
| `backend/skills/etl_skill/scripts/logic.py` | Python | Pipeline async en 16 etapes |
| `backend/skills/etl_skill/scripts/helpers.py` | Python | Utilitaires partages |
| `backend/skills/etl_skill/SKILL.md` | Markdown | Documentation LLM (frontmatter YAML) |
| `backend/skills/etl_skill/api-guide.md` | Markdown | Guide integration FastAPI + TypeScript |
| `backend/skills/etl_skill/examples/example_usage.py` | Python | Exemple complet |
| `backend/skills/etl_skill/examples/sample_config.json` | JSON | Plan JSON d'exemple |
| `backend/skills/etl_skill/examples/expected_output.md` | Markdown | Description sorties attendues |
| `backend/tests/test_etl.py` | Python | 40+ tests unitaires |

**Total : 16 fichiers** soit environ **4000 lignes de code Python et Markdown**.

---

## Variables d'environnement necessaires

Configuration dans `backend/.env`. Voir `backend/.env.example` pour le template complet.

| Variable | Obligatoire | Description |
|----------|-------------|-------------|
| GEMINI_API_KEY | Recommande | Cle API Gemini pour suggestions IA |
| DIRECTUS_URL | Oui | URL du serveur Directus (par defaut http://localhost:8055) |
| DIRECTUS_TOKEN | Oui | Token admin Directus pour publier les rapports |
| FASTAPI_PORT | Non | Port d'ecoute FastAPI (defaut 8000) |
| CORS_ORIGINS | Non | URL Next.js autorisees (defaut http://localhost:3000) |
| ETL_NULL_THRESHOLD | Non | Seuil de nullite pour suppression colonne (defaut 0.5) |
| ETL_IQR_MULTIPLIER | Non | Multiplicateur IQR pour outliers (defaut 1.5) |
| LOG_LEVEL | Non | Niveau de logging (defaut INFO) |

Cote Next.js, configuration dans `frontend/.env.local`.

| Variable | Description |
|----------|-------------|
| NEXT_PUBLIC_FASTAPI_URL | URL du backend (http://localhost:8000) |
| NEXT_PUBLIC_DIRECTUS_URL | URL de Directus (http://localhost:8055) |
| DIRECTUS_TOKEN | Token read-only Directus pour les Server Components |

---

## Validation de l'Etape 1

Avant de passer a l'Etape 2, verifier que les 7 points suivants sont valides.

```
[ ] Tous les fichiers de la liste sont presents et complets
[ ] FastAPI demarre sans erreur sur le port 8000
[ ] Swagger /docs affiche bien POST /api/etl/run
[ ] Directus tourne sur le port 8055 avec les 5 collections creees
[ ] Token Directus configure dans backend/.env
[ ] Tests passent : pytest tests/test_etl.py -v (40+ tests OK)
[ ] Exemple execute sans erreur : python -m skills.etl_skill.examples.example_usage
```

Quand les 7 cases sont cochees, l'Etape 1 est validee.

---

## Prochaine etape

**Etape 2 — Visualization Skill (Session 2.2)**

Le Visualization Skill consomme l'output du ETL Skill (`df_clean` + `report_mdx_id` Directus) et produit :
- Charts Plotly JSON publies dans Directus (collection `charts`)
- Rapport EDA MDX detaille publie dans Directus (collection `reports_mdx`)
- Page Next.js `/eda/` avec composants PlotlyChart et MDXRenderer

Endpoint attendu : `POST /api/visualization/eda` valide par `VisualizationRequest` Pydantic, retournant un `VisualizationResponse` avec la liste des `chart_id` Directus et le `report_mdx_id` EDA.

---

## References

- [Anthropic Skills Documentation](https://docs.anthropic.com/claude/docs/skills)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Pydantic v2 Documentation](https://docs.pydantic.dev/latest/)
- [Directus REST API](https://docs.directus.io/reference/introduction.html)
- [Gemini API google-genai SDK](https://ai.google.dev/gemini-api/docs)
- [pandas Documentation](https://pandas.pydata.org/docs/)
- [scikit-learn Preprocessing](https://scikit-learn.org/stable/modules/preprocessing.html)