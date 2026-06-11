<div align="center">

# AI DATA SKILL SYSTEM

**Plateforme Data Science Augmentée par Intelligence Artificielle**

*De l'Excel brut au Data Scientist augmenté — pipelines intelligents, rapides et reproductibles.*

---

![Open WebUI](https://img.shields.io/badge/Open_WebUI-black?style=flat-square)
![FastMCP](https://img.shields.io/badge/MCP_FastMCP-4285F4?style=flat-square&logo=python&logoColor=white)
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

## Architecture Nouvelle Génération (Open WebUI + MCP)

```text
USER
 │  (upload fichiers + requêtes en langage naturel)
 ▼
OPEN WEBUI (port 8080)           Interface Chat unifiée & orchestration IA
 │  appels d'outils (Tool Calling) via MCP
 ▼
SERVEURS MCP (FastMCP)           Bridges contextuels intelligents
 │  - ETL MCP Server (port 8001)
 │  - Viz MCP Server (port 8002)
 ▼
SKILLS ENGINE (Python)           Modules d'intelligence autonomes
 │  ETL → Viz → Modeling → ML_Explanation → Prediction → Analysis
 │  (Méta-skills : createur-de-competence, calculateur-tva, etc.)
 ▼
FILE SERVER (port 8090)          Service de fichiers HTTP pour Open WebUI
 │  stockage et liens de téléchargements
 ▼
NEXT.JS DASHBOARD & DIRECTUS     Dashboard optionnel / Stockage persistant
 │
USER  ←  résultat (fichiers nettoyés, graphes, rapports)
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

```text
ai-data-skill-system/
│
├── Open-WebUI/                           INTERFACE AGENTIQUE (Chat & Tools)
│   ├── .venv/
│   └── docker-compose.yml / runtime
│
├── backend/                              SERVEURS & INTELLIGENCE (Python)
│   ├── mcp/                              SERVEURS FAST_MCP (Outils pour LLM)
│   │   ├── etl_mcp/
│   │   └── viz_mcp/
│   │
│   ├── skills/                           ÉCOSYSTÈME DES COMPÉTENCES AUTONOMES
│   │   ├── etl_skill/
│   │   ├── visualization_skill/
│   │   ├── modeling_skill/
│   │   ├── calculateur-tva-madagascar/
│   │   └── createur-de-competence/
│   │
│   ├── api/                              FASTAPI (Endpoints Historiques)
│   │   └── main.py
│   │
│   ├── llm_orchestrator/                 CERVEAU GEMINI (Workflow classique)
│   │
│   ├── file_server.py                    Serveur HTTP pour Open WebUI (port 8090)
│   ├── data/                             raw/, processed/, uploads/
│   ├── requirements.txt
│   └── .env
│
├── frontend/                             NEXT.JS FRONTEND (Dashboard Optionnel)
│   ├── app/
│   └── components/
│
├── directus/                             CMS DIRECTUS (Stockage Optionnel)
│   ├── database/
│   └── uploads/
│
└── README.md
```

---

##  L'Écosystème des Skills

La plateforme s'enrichit dynamiquement via un système de **Skills autonomes**. 

| Skill / Composant | Rôle | Interface / Exposition |
|-------------------|------|------------------------|
| **ETL Skill** | Nettoyage automatisé et préparation de données | MCP (`etl_auto`, `get_download_links`) |
| **Visualization Skill** | Génération de graphiques EDA via LLM | MCP |
| **Modeling Skill** | Entraînement ML automatisé | API FastAPI |
| **Explanation Skill** | Interprétabilité SHAP | API FastAPI |
| **Prediction Skill** | Inférence sur nouveaux datasets | API FastAPI |
| **Analysis Skill** | Synthèse et insights business | API FastAPI |
| **Méta-Skill Créateur** | `createur-de-competence` pour créer d'autres skills | Autonome / CLI |
| **Skills Métier** | ex: `calculateur-tva-madagascar` | Autonome / LLM |

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
- Open WebUI installé localement ou via Docker
- Une clé API Gemini (gratuite sur https://aistudio.google.com)

### 1. Cloner le repo & Initialiser l'environnement

```bash
git clone https://github.com/votre-username/ai-data-skill-system.git
cd ai-data-skill-system/backend

# Utilisation recommandée de 'uv' pour la rapidité
uv venv
source .venv/bin/activate              # Linux / Mac
.venv\Scripts\activate                 # Windows

uv pip install -r requirements.txt

cp .env.example .env
# Éditer .env et renseigner GEMINI_API_KEY et les autres clés
```

### 2. Démarrer les Serveurs MCP & Fichiers (Nouvelle Architecture)

```bash
# Terminal 1 - ETL MCP Server (Port 8001)
uv run --env-file .env python mcp/etl_mcp/server.py

# Terminal 2 - Serveur de Fichiers (Port 8090)
uv run --env-file .env python file_server.py
```

### 3. Configurer Open WebUI (Interface Chat)

1. Lancer [Open WebUI](https://docs.openwebui.com/) (ex: via Docker).
2. Ajouter le serveur MCP : Allez dans `Settings > Admin Settings > External Connections > MCP Servers`. 
   - Ajoutez : `http://host.docker.internal:8001/mcp` (ou l'URL locale appropriée).
3. Ouvrez un chat avec votre modèle (ex: Gemini 2.5 Flash), uploadez un dataset, et demandez en langage naturel : *"Nettoie ce fichier et prépare un modèle de données en étoile"*.

### 4. Directus CMS & Frontend Next.js (Optionnel - Architecture Historique)

Si vous souhaitez utiliser le dashboard Next.js classique au lieu d'Open WebUI :
1. Lancez Directus CMS (`npx directus start` sur le port 8055) et configurez les tokens.
2. Lancez le client Next.js (`npm run dev` sur le port 3000).
3. Lancez FastAPI root (`uvicorn api.main:app --reload`).

---

## Stack technologique

### Intelligence Artificielle & Orchestration

| Technologie | Usage |
|-------------|-------|
| ![Open WebUI](https://img.shields.io/badge/-Open_WebUI-000?style=flat-square) | Interface Agentique Principale & Chat |
| ![MCP](https://img.shields.io/badge/-Model_Context_Protocol-4285F4?style=flat-square) | FastMCP pour l'exposition des outils au LLM |
| `google-genai` | SDK Gemini officiel |

### Backend Data & Skills

| Technologie | Version | Usage |
|-------------|---------|-------|
| ![FastAPI](https://img.shields.io/badge/-FastAPI-009688?logo=fastapi&logoColor=white&style=flat-square) | >= 0.110 | Serveurs MCP et Webhooks |
| ![Pandas](https://img.shields.io/badge/-Pandas-150458?logo=pandas&logoColor=white&style=flat-square) | >= 2.2 | Manipulation des données |
| ![scikit-learn](https://img.shields.io/badge/-scikit--learn-F7931E?logo=scikitlearn&logoColor=white&style=flat-square) | >= 1.5 | Algorithmes ML et preprocessing |
| `XGBoost` / `LightGBM` | >= 2.0 | Modélisation prédictive performante |
| `SHAP` | >= 0.44 | Interprétabilité ML |

### CMS (Dashboard Classique)

| Technologie | Version | Usage |
|-------------|---------|-------|
| ![Directus](https://img.shields.io/badge/-Directus-6644AA?logo=directus&logoColor=white&style=flat-square) | >= 10 | CMS stockage MDX + charts |

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

*Stack : Open WebUI · MCP (FastMCP) · FastAPI · Gemini 2.5 Flash · Directus MDX · Next.js 14*

</div>
