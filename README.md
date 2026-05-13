<div align="center">

# AI DATA SKILL SYSTEM

**Plateforme Data Science Augmentée par Intelligence Artificielle**

*De l'Excel brut au Data Scientist augmenté — pipelines intelligents, rapides et reproductibles.*

---

![Next.js](https://img.shields.io/badge/Next.js_14-000000?style=flat-square&logo=nextdotjs&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![Pydantic](https://img.shields.io/badge/Pydantic_v2-E92063?style=flat-square&logo=pydantic&logoColor=white)
![Gemini](https://img.shields.io/badge/Gemini_2.5_Flash-4285F4?style=flat-square&logo=google&logoColor=white)
![Directus](https://img.shields.io/badge/Directus-6644AA?style=flat-square&logo=directus&logoColor=white)
![Python](https://img.shields.io/badge/Python_3.10+-3776AB?style=flat-square&logo=python&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript_5-3178C6?style=flat-square&logo=typescript&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?style=flat-square&logo=sqlite&logoColor=white)

---

![React](https://img.shields.io/badge/React_18-61DAFB?style=flat-square&logo=react&logoColor=black)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-06B6D4?style=flat-square&logo=tailwindcss&logoColor=white)
![Plotly](https://img.shields.io/badge/Plotly.js-3F4F75?style=flat-square&logo=plotly&logoColor=white)
![scikit-learn](https://img.shields.io/badge/scikit--learn-F7931E?style=flat-square&logo=scikit-learn&logoColor=white)
![XGBoost](https://img.shields.io/badge/XGBoost-189AB4?style=flat-square&logo=data:image/png;base64,&logoColor=white)
![Pandas](https://img.shields.io/badge/Pandas-150458?style=flat-square&logo=pandas&logoColor=white)
![SHAP](https://img.shields.io/badge/SHAP-FF6B35?style=flat-square&logoColor=white)
![Pytest](https://img.shields.io/badge/Pytest-0A9EDC?style=flat-square&logo=pytest&logoColor=white)

---

[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](./LICENSE)
[![Version](https://img.shields.io/badge/version-1.0.0-teal?style=flat-square)]()
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen?style=flat-square)]()

</div>

---

## À faire — Prochaines étapes

- [ ] Enregistrer un demo GIF du workflow end-to-end
- [ ] Compléter les 7 fichiers `SKILL.md` (frontmatter YAML + instructions LLM)
- [ ] Couvrir `core/` de chaque Skill avec des tests pytest + coverage
- [ ] Déploiement Vercel (frontend) + Railway (backend + Directus) + CI/CD GitHub Actions
- [ ] Valider le pipeline complet sur 3 datasets (churn, iris, boston housing)
- [ ] Ajouter screenshots des 6 zones du dashboard dans ce README
- [ ] Documenter les variables d'environnement dans `.env.example`

---

## Vision

Travailler avec des données aujourd'hui oblige à jongler entre Excel, Python, Tableau et la documentation manuelle. Chaque étape est isolée, lente et dépendante d'une expertise élevée.

**AI DATA SKILL SYSTEM** résout ce problème en construisant une plateforme unifiée pilotée par Gemini qui automatise l'ensemble du workflow data de bout en bout — du dataset brut jusqu'au dashboard interactif déployé en ligne.

L'utilisateur pose une question en langage naturel, uploade un dataset, et le système orchestre, exécute, explique et présente les résultats dans un dashboard clair.

---

## Architecture en 3 services

```
USER
 │  (question en langage naturel + upload dataset)
 ▼
NEXT.JS FRONTEND (port 3000)     interface utilisateur React
 │  HTTP POST + SSE streaming
 ▼
FASTAPI BACKEND (port 8000)      API Python exposant les Skills + Pydantic
 │  router.py → planner.py → executor.py
 ▼
GEMINI ORCHESTRATOR              cerveau central
 │  plan d'exécution JSON
 ▼
SKILLS ENGINE                    séquencement dynamique
 │  ETL → Viz → Modeling → ML_Explanation → Prediction → Analysis
 ▼
DIRECTUS CMS (port 8055)         stockage MDX + charts + historique
 │  rapports MDX + Plotly JSON
 ▼
NEXT.JS DASHBOARD                rendu MDX + Plotly.js + métriques
 ▼
USER  ←  résultat final actionnable
```

---

## Principe fondamental — Skills autonomes

Chaque Skill est un module **100% indépendant** avec une séparation stricte entre `core/` (logique Python pure) et `scripts/` (interface orchestrateur).

```
backend/skills/etl_skill/         ← MODULE COMPLET ET AUTONOME
    │
    ├── core/                     ← FONDATION (logique métier pure)
    │   cleaner.py
    │   transformer.py
    │   validator.py
    │   exporter.py
    │
    ├── scripts/                  ← INTERFACE LLM (pont orchestrateur → core/)
    │   main.py                   ← point d'entrée appelé par executor.py
    │   logic.py                  ← orchestre les appels vers core/
    │   helpers.py                ← fonctions utilitaires internes
    │
    ├── examples/                 ← exemples standalone et configs
    │   example_usage.py
    │   sample_config.json
    │   expected_output.md
    │
    ├── SKILL.md                  ← documentation LLM (frontmatter YAML)
    └── api-guide.md              ← guide d'intégration FastAPI + TypeScript
```

**Hiérarchie unidirectionnelle des dépendances :**

```
backend/skills/*/core/            ← FONDATION (autonome, fonctionne seul)
    │
    └── backend/skills/*/scripts/         ← INTERFACE LLM (optionnelle)
            │
            └── backend/llm_orchestrator/   ← DÉCISION GEMINI (optionnelle)
```

---

## 📁 Structure du projet

```
ai-data-skill-system/
│
├── backend/                              FASTAPI BACKEND (Python)
│   ├── api/
│   │   main.py                           Point d'entrée FastAPI
│   │   └── routes/                       Endpoints REST par Skill
│   │       etl.py, visualization.py, modeling.py
│   │       explanation.py, prediction.py, analysis.py
│   │       execute.py, orchestrate.py, logs.py
│   │
│   ├── schemas/                          PYDANTIC SCHEMAS (inputs/outputs)
│   │   etl.py, visualization.py, modeling.py
│   │   explanation.py, prediction.py, analysis.py
│   │   execute.py, orchestrate.py
│   │
│   ├── llm_orchestrator/                 CERVEAU GEMINI
│   │   router.py, planner.py, executor.py, prompt_engine.py
│   │
│   ├── skills/                           7 SKILLS AUTONOMES
│   │   ├── etl_skill/
│   │   ├── visualization_skill/
│   │   ├── modeling_skill/
│   │   ├── prediction_skill/
│   │   ├── analysis_skill/
│   │   ├── ml_explanation_skill/
│   │   └── nextjs_builder_skill/
│   │
│   ├── src/utils/
│   │   logger.py, config.py, helpers.py
│   │   directus_client.py
│   │
│   ├── data/                             raw/, processed/, external/
│   ├── models/                           Modèles ML sérialisés (.pkl)
│   ├── outputs/                          Graphiques, rapports PDF, exports CSV
│   ├── tests/
│   ├── notebooks/
│   ├── requirements.txt
│   ├── .env
│   └── config.yaml
│
├── frontend/                             NEXT.JS FRONTEND (TypeScript)
│   ├── app/
│   │   layout.tsx, page.tsx
│   │   upload/page.tsx
│   │   eda/page.tsx
│   │   modeling/page.tsx
│   │   predictions/page.tsx
│   │   insights/page.tsx
│   │   terminal/page.tsx
│   │
│   ├── components/
│   │   DataTable.tsx, PlotlyChart.tsx, MetricCard.tsx
│   │   MDXRenderer.tsx, ChatInterface.tsx, PythonTerminal.tsx
│   │   ProgressPipeline.tsx, SidebarNav.tsx
│   │
│   ├── lib/
│   │   directus.ts, fastapi.ts
│   │   hooks/useSSE.ts, hooks/usePipeline.ts
│   │
│   ├── types/
│   ├── package.json
│   ├── next.config.ts
│   ├── tailwind.config.ts
│   └── tsconfig.json
│
├── directus/
│   ├── package.json
│   ├── .env
│   ├── snapshots/
│   ├── database/
│   └── uploads/
│
└── README.md
```

---

##  Les 7 Skills

| Skill | Rôle | Endpoint FastAPI | Livrable Directus |
|-------|------|------------------|-------------------|
| **ETL Skill** | Nettoyage et transformation des données | `POST /api/etl/run` | Rapport MDX ETL |
| **Visualization Skill** | Graphiques EDA et dashboards | `POST /api/visualization/eda` | Rapport EDA MDX + Plotly charts |
| **Modeling Skill** | Entraînement ML automatisé | `POST /api/modeling/train` | Model Card MDX + charts ROC/Confusion |
| **Prediction Skill** | Inférence batch et temps réel | `POST /api/prediction/run` | Fichier CSV prédictions |
| **ML Explanation Skill** | Interprétabilité SHAP | `POST /api/explanation/shap` | SHAP charts + rapport MDX |
| **Analysis Skill** | Insights business et synthèse | `POST /api/analysis/summary` | Rapport exécutif MDX |
| **NextJS Builder Skill** | Génération de composants UI | — | Composants React générés |

---

## Dashboard adaptatif Next.js — 6 zones

| Zone | Contenu | Affichage conditionnel |
|------|---------|------------------------|
| **Zone 0 — Header** | Nom dataset, statut pipeline SSE, progression | Toujours |
| **Zone 1 — KPI Cards** | Métriques avant/après ETL | Toujours |
| **Zone 2 — Graphiques EDA** | PlotlyChart Directus + commentaire MDX | ETL + Visualization actifs |
| **Zone 3 — Résultats ML** | MetricCard + confusion + ROC + SHAP | Modeling actif |
| **Zone 4 — Prédictions** | Formulaire RT + tableau batch + upload CSV | Prediction actif |
| **Zone 5 — Insights IA** | Rapport Analysis MDX + questions suggérées | Analysis actif |
| **Zone 6 — Terminal & Historique** | PythonTerminal SSE + sessions Directus | Toujours |

---

## Quick Start

### Prérequis

- Python >= 3.10
- Node.js >= 18
- Une clé API Gemini (gratuite sur https://aistudio.google.com)

### 1. Cloner le repo

```bash
git clone https://github.com/votre-username/ai-data-skill-system.git
cd ai-data-skill-system
```

### 2. Backend Python + FastAPI

```bash
cd backend
python -m venv venv
source venv/bin/activate              # Linux / Mac
venv\Scripts\activate                 # Windows

pip install -r requirements.txt

cp .env.example .env
# Éditer .env et renseigner GEMINI_API_KEY et DIRECTUS_TOKEN

uvicorn api.main:app --reload --port 8000
# Swagger auto-généré : http://localhost:8000/docs
```

### 3. Directus CMS

```bash
mkdir directus && cd directus
npm init directus-project@latest .
# Suivre l'assistant : email admin, mot de passe, base SQLite

npx directus start
# Accès : http://localhost:8055
```

Générer un token d'accès dans `Settings → Access Tokens`, puis le reporter dans `backend/.env` sur la ligne `DIRECTUS_TOKEN=`.

### 4. Frontend Next.js

```bash
cd frontend
npm install

cp .env.local.example .env.local
# Renseigner NEXT_PUBLIC_FASTAPI_URL et NEXT_PUBLIC_DIRECTUS_URL

npm run dev
# Ouvre http://localhost:3000
```

### 5. Vérification finale

Trois services doivent tourner en parallèle :

| Service | URL | Vérification |
|---------|-----|--------------|
| FastAPI | http://localhost:8000 | `/docs` accessible |
| Directus | http://localhost:8055 | Login admin fonctionnel |
| Next.js | http://localhost:3000 | Page d'accueil affichée |

### 6. Utiliser un Skill en mode standalone

```python
# Mode direct — core/ uniquement, sans orchestrateur
from skills.etl_skill.core.cleaner import load_dataset, remove_duplicates

df, metadata = load_dataset("data/raw/churn.csv")
df_clean, report = remove_duplicates(df)
print(f"Dataset : {df_clean.shape}")

# Mode LLM — via scripts/ appelé par l'orchestrateur
from skills.etl_skill.scripts.main import run_etl_skill

result = run_etl_skill({
    "dataset_path": "data/raw/churn.csv",
    "session_id": "session_001",
    "strategy_nulls": "impute",
    "normalize": True
})
print(result["report_mdx_id"])
```

---

## Stack technologique

### Frontend

| Technologie | Version | Usage |
|-------------|---------|-------|
| ![Next.js](https://img.shields.io/badge/-Next.js-000?logo=nextdotjs&logoColor=white&style=flat-square) | >= 14 | Framework React App Router |
| ![React](https://img.shields.io/badge/-React-61DAFB?logo=react&logoColor=black&style=flat-square) | 18 | Composants UI |
| ![TypeScript](https://img.shields.io/badge/-TypeScript-3178C6?logo=typescript&logoColor=white&style=flat-square) | >= 5 | Typage statique |
| ![Tailwind](https://img.shields.io/badge/-Tailwind-06B6D4?logo=tailwindcss&logoColor=white&style=flat-square) | >= 3 | Styles utilitaires |
| ![Plotly](https://img.shields.io/badge/-Plotly.js-3F4F75?logo=plotly&logoColor=white&style=flat-square) | 2 | Graphiques interactifs |
| `@directus/sdk` | latest | Client Directus |
| `MDX` | 3 | Rendu rapports Directus |
| `Zustand` | 4 | Gestion d'état global |

### Backend

| Technologie | Version | Usage |
|-------------|---------|-------|
| ![FastAPI](https://img.shields.io/badge/-FastAPI-009688?logo=fastapi&logoColor=white&style=flat-square) | >= 0.110 | API REST asynchrone |
| ![Pydantic](https://img.shields.io/badge/-Pydantic-E92063?logo=pydantic&logoColor=white&style=flat-square) | >= 2.7 | Validation des schémas |
| ![Pandas](https://img.shields.io/badge/-Pandas-150458?logo=pandas&logoColor=white&style=flat-square) | >= 2.2 | Manipulation des données |
| ![scikit-learn](https://img.shields.io/badge/-scikit--learn-F7931E?logo=scikitlearn&logoColor=white&style=flat-square) | >= 1.5 | Algorithmes ML |
| `XGBoost` | >= 2.0 | Gradient Boosting |
| `LightGBM` | >= 4.3 | Gradient Boosting rapide |
| `SHAP` | >= 0.44 | Interprétabilité ML |
| ![Plotly](https://img.shields.io/badge/-Plotly-3F4F75?logo=plotly&logoColor=white&style=flat-square) | >= 5.22 | Graphiques (export JSON) |
| `google-genai` | >= 1.0 | SDK Gemini officiel |
| ![Pytest](https://img.shields.io/badge/-pytest-0A9EDC?logo=pytest&logoColor=white&style=flat-square) | >= 8.2 | Tests unitaires |

### CMS

| Technologie | Version | Usage |
|-------------|---------|-------|
| ![Directus](https://img.shields.io/badge/-Directus-6644AA?logo=directus&logoColor=white&style=flat-square) | >= 10 | CMS stockage MDX + charts |
| ![SQLite](https://img.shields.io/badge/-SQLite-003B57?logo=sqlite&logoColor=white&style=flat-square) | 3 | Base de données (fichier .db) |
| ![Node.js](https://img.shields.io/badge/-Node.js-339933?logo=nodedotjs&logoColor=white&style=flat-square) | >= 18 | Runtime Directus |

---

## API Backend — Endpoints principaux

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `POST` | `/api/etl/run` | Lancer l'ETL Skill |
| `POST` | `/api/visualization/eda` | Lancer le Visualization Skill |
| `POST` | `/api/modeling/train` | Lancer le Modeling Skill |
| `POST` | `/api/explanation/shap` | Lancer le ML Explanation Skill |
| `POST` | `/api/prediction/run` | Lancer le Prediction Skill |
| `POST` | `/api/analysis/summary` | Lancer l'Analysis Skill |
| `POST` | `/api/execute` | Exécution Python arbitraire |
| `POST` | `/api/orchestrate` | Lancer l'orchestrateur Gemini complet |
| `GET` | `/api/orchestrate/stream` | SSE streaming avancement pipeline |
| `GET` | `/api/logs/stream` | SSE streaming logs d'exécution |
| `GET` | `/docs` | Documentation Swagger auto-générée |

---

## Lancer les tests

```bash
cd backend

# Tous les tests
pytest tests/ -v

# Tests d'un Skill spécifique
pytest tests/test_etl.py -v

# Tests avec couverture
pytest tests/ --cov=skills --cov=llm_orchestrator

# Tests des endpoints FastAPI (TestClient async)
pytest tests/test_endpoints.py -v
```

---

## 🗺️ Roadmap de build

| Étape | Nom | Livrable | Session |
|-------|-----|----------|---------|
| 0 | Setup & Configuration | Environnement complet fonctionnel | 3.1 |
| 1 | ETL Skill | Dataset propre + rapport MDX Directus + page Upload | 3.1 |
| 2 | Visualization Skill | Charts Plotly Directus + rapport EDA MDX + page EDA | 3.2 |
| 3 | Modeling Skill | Modèle ML + Model Card MDX + pages ML | 3.3 |
| 4 | Next.js App complète | Dashboard adaptatif 6 zones + terminal SSE | 3.2 → 3.4 |
| 5 | LLM Orchestrator | Orchestrateur Gemini fonctionnel + SSE | 3.4 |
| 6 | Skills complémentaires | SHAP + Prediction + Analysis | 3.3 |
| 7 | Pipeline End-to-End | Système intégré testé sur 3 datasets | 3.4 |
| 8 | Déploiement & Docs | Plateforme déployée Vercel + Railway v1.0.0 | 3.4 |

---

## Collections Directus

```
sessions          historique des sessions utilisateur
reports_mdx       rapports MDX (ETL, EDA, Model Card, Analysis, Explanation)
charts            visualisations Plotly JSON + PNG
pipeline_logs     logs d'exécution par Skill
user_profiles     profils utilisateurs et préférences
```

---

## Déploiement

### Frontend — Vercel

```bash
cd frontend
npx vercel --prod
# Renseigner NEXT_PUBLIC_FASTAPI_URL et NEXT_PUBLIC_DIRECTUS_URL
```

### Backend FastAPI — Railway / Render

```bash
# Procfile : uvicorn api.main:app --host 0.0.0.0 --port $PORT
# Renseigner GEMINI_API_KEY, DIRECTUS_URL, DIRECTUS_TOKEN
```

### Directus — Railway / Render

```bash
# Build command : npm install
# Start command : npx directus start
# Renseigner SECRET, DB_CLIENT, ADMIN_EMAIL, ADMIN_PASSWORD
```

### Tag de release

```bash
git tag -a v1.0.0 -m "AI DATA SKILL SYSTEM — Release 1.0.0"
git push origin v1.0.0
```

---

## 🤝 Contribuer — Ajouter un nouveau Skill

1. Construire `backend/skills/nouveau_skill/core/` avec la logique métier indépendante
2. Construire `backend/skills/nouveau_skill/scripts/main.py` comme point d'entrée orchestrateur
3. Rédiger `backend/skills/nouveau_skill/SKILL.md` avec frontmatter YAML et instructions
4. Rédiger `backend/skills/nouveau_skill/api-guide.md` avec schéma Pydantic et exemples
5. Construire `backend/schemas/nouveau_skill.py` avec les modèles Pydantic Request/Response
6. Construire `backend/api/routes/nouveau_skill.py` avec l'endpoint FastAPI
7. Ajouter les tests dans `backend/tests/test_nouveau_skill.py`
8. Enregistrer le Skill dans `backend/llm_orchestrator/planner.py`
9. Ajouter une page Next.js dans `frontend/app/nouveau_skill/page.tsx` si UI nécessaire

---

## 📜 Licence

MIT — libre d'utilisation, de modification et de distribution.

---

<div align="center">

*AI DATA SKILL SYSTEM v1.0.0*

*Stack : Next.js 14 · FastAPI · Pydantic · Directus MDX · Gemini 2.5 Flash*

</div>