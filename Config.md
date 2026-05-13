# CONFIG.md — Étape 0 : Setup Complet

**AI DATA SKILL SYSTEM** — Procédure pas à pas pour monter l'environnement de dev complet.

Stack : Next.js 14 + FastAPI + Pydantic + Directus SQLite + Gemini.

À la fin de ce document, tu auras trois services qui tournent en parallèle :

| Service | Port | URL |
|---------|------|-----|
| FastAPI Backend | 8000 | http://localhost:8000 |
| Next.js Frontend | 3000 | http://localhost:3000 |
| Directus CMS | 8055 | http://localhost:8055 |

---

## Pré-requis

Avant de commencer, vérifier les versions installées.

```bash
python --version    # >= 3.10
node --version      # >= 18
npm --version       # >= 9
git --version       # >= 2.30
```

Si une version manque, l'installer avant d'aller plus loin.

---

### Installation des pré-requis manquants

#### Linux / macOS

**Python >= 3.10**
```bash
# Ubuntu/Debian
sudo apt update && sudo apt install -y python3 python3-pip python3-venv

# macOS (Homebrew)
brew install python@3.10

# Vérifier
python3 --version
```

**Node.js >= 18**
```bash
# Via nvm (recommandé — Linux & macOS)
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
source ~/.bashrc        # Linux
source ~/.zshrc         # macOS
nvm install 18
nvm use 18

# Ubuntu/Debian sans nvm
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs

# macOS sans nvm
brew install node@18

# Vérifier
node --version
npm --version
```

**Git >= 2.30**
```bash
# Ubuntu/Debian
sudo apt update && sudo apt install -y git

# macOS
brew install git

# Vérifier
git --version
```

**Alias `python` si manquant**
```bash
# Si python --version échoue mais python3 fonctionne
sudo ln -s /usr/bin/python3 /usr/bin/python
```

---

#### Windows

**Python >= 3.10**
```powershell
# Via winget
winget install Python.Python.3.10

# Ou télécharger l'installeur sur https://www.python.org/downloads/
# Cocher "Add Python to PATH" pendant l'installation

# Vérifier (PowerShell)
python --version
```

**Node.js >= 18**
```powershell
# Via winget
winget install OpenJS.NodeJS.LTS

# Ou via nvm-windows
# Télécharger nvm-setup.exe sur https://github.com/coreybutler/nvm-windows/releases
nvm install 18
nvm use 18

# Vérifier
node --version
npm --version
```

**Git >= 2.30**
```powershell
# Via winget
winget install Git.Git

# Ou télécharger sur https://git-scm.com/download/win

# Vérifier
git --version
```

> **Note Windows** : utiliser **PowerShell 7+** ou **Git Bash** pour toutes les commandes du projet. L'invite CMD classique n'est pas supportée.

---

Après installation, relancer les vérifications avant de continuer :

```bash
python --version    # >= 3.10
node --version      # >= 18
npm --version       # >= 9
git --version       # >= 2.30
```

---

Obtenir une clé Gemini gratuite sur https://aistudio.google.com (Get API Key).


---

## Phase 0.1 — Initialisation du projet

```bash
cd ~/Documents
mkdir ai-data-skill-system
cd ai-data-skill-system

git init
git branch -M main
```

### Fichier `.gitignore` à la racine

Copier ce contenu dans `ai-data-skill-system/.gitignore`.

```gitignore
# =============================================================================
# .gitignore — AI DATA SKILL SYSTEM 2026
# =============================================================================

# ── Secrets et configuration locale ─────────────────────────────────────────
.env
.env.local
.env.*.local
*.key
*.pem

# ── Python ──────────────────────────────────────────────────────────────────
__pycache__/
*.py[cod]
*$py.class
*.so
venv/
env/
.venv/
.Python
*.egg-info/
.pytest_cache/
.coverage
htmlcov/
.tox/
.mypy_cache/
.ruff_cache/

# ── Node.js / Next.js ───────────────────────────────────────────────────────
node_modules/
.next/
out/
dist/
build/
npm-debug.log*
yarn-debug.log*
yarn-error.log*

# ── Directus ────────────────────────────────────────────────────────────────
directus/database/*.db
directus/database/*.db-journal
directus/uploads/
directus/extensions/

# ── Données lourdes et modèles ──────────────────────────────────────────────
backend/data/raw/*
backend/data/processed/*
backend/data/external/*
backend/models/*.pkl
backend/models/*.joblib
backend/outputs/*
!backend/data/raw/.gitkeep
!backend/data/processed/.gitkeep
!backend/data/external/.gitkeep
!backend/models/.gitkeep
!backend/outputs/.gitkeep

# ── Notebooks ──────────────────────────────────────────────────────────────
.ipynb_checkpoints/

# ── IDE ─────────────────────────────────────────────────────────────────────
.vscode/
.idea/
*.swp
.DS_Store
Thumbs.db

# ── Logs ────────────────────────────────────────────────────────────────────
*.log
logs/
```

---

## Phase 0.2 — Backend Python + FastAPI

### Initialisation du dossier backend

```bash
mkdir backend
cd backend

python -m venv venv
venv\Scripts\activate          # Windows PowerShell
# source venv/bin/activate         # Linux / Mac
```

### Fichier `backend/requirements.txt`

Copier ce contenu dans `backend/requirements.txt`. Toutes les dépendances de toute la roadmap sont incluses.

```txt
# =============================================================================
# requirements.txt — AI DATA SKILL SYSTEM 2026
# Stack : Next.js 14 + FastAPI + Pydantic + Directus MDX + Gemini
# Compatible Python 3.10+
#
# INSTALLATION COMPLÈTE :
#   pip install -r requirements.txt
#
# VÉRIFICATION :
#   python -c "import fastapi, pydantic, pandas, numpy, sklearn, plotly, shap; print('OK')"
#
# DÉMARRAGE FASTAPI :
#   uvicorn api.main:app --reload --port 8000
#   Swagger : http://localhost:8000/docs
# =============================================================================


# ── ÉTAPE 0 — Setup de base : Manipulation des données ──────────────────────

# Manipulation des données tabulaires : read_csv, groupby, merge, pivot_table
pandas>=2.2.3

# Calcul numérique : arrays, percentile, clip, where, nan
numpy>=2.0.0

# Lecture/écriture fichiers Excel modernes (.xlsx, .xlsm)
openpyxl>=3.1.3

# Lecture des anciens fichiers Excel (.xls)
xlrd>=2.0.1

# Lecture de fichiers Parquet (format columnar haute performance)
pyarrow>=16.0.0

# Chargement des variables d'environnement depuis .env
python-dotenv>=1.0.1


# ── ÉTAPE 0 — FastAPI Backend (API REST exposant les Skills) ────────────────

# Framework API REST asynchrone moderne
fastapi>=0.110.0

# Serveur ASGI haute performance pour FastAPI
uvicorn>=0.29.0

# Validation des schémas inputs/outputs entre Next.js et Python
pydantic>=2.7.0

# Gestion des uploads de fichiers multipart
python-multipart>=0.0.9

# Client HTTP asynchrone (Directus + inter-Skills + TestClient FastAPI)
httpx>=0.27.0


# ── ÉTAPE 1 — ETL Skill (Nettoyage et transformation) ───────────────────────

# Gestion du déséquilibre de classes : SMOTE, RandomOverSampler
imbalanced-learn>=0.12.0

# Sérialisation des modèles ML et pipelines complets (.pkl / .joblib)
joblib>=1.4.0


# ── ÉTAPE 2 — Visualization Skill (Graphiques et EDA) ───────────────────────

# Graphiques interactifs : scatter, bar, histogram, heatmap, line, box
plotly>=5.22.0

# Graphiques statiques : SHAP plots, exports PNG pour rapports PDF
matplotlib>=3.9.0


# ── ÉTAPE 3 — Modeling Skill (Machine Learning) ─────────────────────────────

# Algorithmes ML et preprocessing : Pipeline, scalers, encoders, metrics, CV
scikit-learn>=1.5.0

# Gradient Boosting avancé : XGBClassifier, XGBRegressor
xgboost>=2.0.0

# Gradient Boosting rapide : LGBMClassifier, LGBMRegressor
lightgbm>=4.3.0

# Interprétabilité des modèles : SHAP values, summary plot, waterfall
shap>=0.44.0


# ── ÉTAPE 5 — LLM Orchestrator (Gemini) ─────────────────────────────────────

# SDK officiel Gemini (remplace google-generativeai déprécié depuis 2025)
google-genai>=1.0.0


# ── ÉTAPE 6 — Skills complémentaires ────────────────────────────────────────

# Génération de rapports PDF : Analysis Skill → rapport exécutif exportable
fpdf2>=2.7.9


# ── TESTS (recommandés pour chaque module produit) ──────────────────────────

# Framework de tests unitaires et d'intégration
pytest>=8.2.0

# Plugin pytest pour mesurer la couverture de code
pytest-cov>=5.0.0

# Plugin pytest pour tester du code asynchrone (FastAPI endpoints)
pytest-asyncio>=0.23.0
```

### Installation des dépendances

```bash
pip install --upgrade pip
pip install -r requirements.txt

# Vérification
python -c "import fastapi, pydantic, pandas, numpy, sklearn, plotly, shap, lightgbm, xgboost; print('Toutes les librairies sont installées')"
```

### Fichier `backend/api/main.py`

D'abord générer la structure du dossier api.

```bash
mkdir -p api/routes
touch api/__init__.py
touch api/routes/__init__.py
```

Puis copier ce contenu dans `backend/api/main.py`.

```python
"""
api/main.py — Point d'entrée FastAPI du backend AI DATA SKILL SYSTEM.

Ce module expose l'API REST consommée par Next.js. Au démarrage, il charge
les variables d'environnement, configure CORS pour autoriser Next.js, et
enregistre les routes des Skills (vides à ce stade, ajoutées à chaque étape).

Lancement local :
    uvicorn api.main:app --reload --port 8000

Documentation auto-générée :
    http://localhost:8000/docs
"""

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv


# ── Chargement des variables d'environnement ──────────────────────────────
load_dotenv()


# ── Configuration du logging ──────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ── Cycle de vie de l'application ─────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Hook de démarrage et d'arrêt de l'application FastAPI."""
    logger.info("AI DATA SKILL SYSTEM — Backend FastAPI démarré")
    logger.info(f"Environnement : {os.getenv('APP_ENV', 'development')}")
    logger.info(f"Directus URL : {os.getenv('DIRECTUS_URL', 'non configuré')}")
    yield
    logger.info("AI DATA SKILL SYSTEM — Backend FastAPI arrêté")


# ── Instance FastAPI ──────────────────────────────────────────────────────
app = FastAPI(
    title="AI DATA SKILL SYSTEM API",
    description="Plateforme Data Science Augmentée par IA — Backend FastAPI",
    version="0.1.0",
    lifespan=lifespan,
)


# ── Configuration CORS pour autoriser Next.js ─────────────────────────────
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Endpoints de base ─────────────────────────────────────────────────────
@app.get("/")
async def root():
    """Endpoint racine de l'API. Confirme que le serveur tourne."""
    return {
        "service": "AI DATA SKILL SYSTEM API",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    """Health check pour les outils de monitoring et le déploiement."""
    return {
        "status": "healthy",
        "environment": os.getenv("APP_ENV", "development"),
        "directus_configured": bool(os.getenv("DIRECTUS_URL")),
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY")),
    }


# ── Enregistrement des routes des Skills ──────────────────────────────────
# Les routes seront ajoutées à chaque étape de la roadmap.
# Étape 1 : from api.routes import etl ; app.include_router(etl.router, prefix="/api")
# Étape 2 : from api.routes import visualization ; app.include_router(...)
# Étape 3 : from api.routes import modeling ; app.include_router(...)
```

---

## Phase 0.3 — Structure complète du backend

### Script bash `setup_backend_structure.sh`

À placer à la racine du projet `ai-data-skill-system/setup_backend_structure.sh`.

```bash
#!/bin/bash
# =============================================================================
# setup_backend_structure.sh
# Génère toute l'arborescence backend pour AI DATA SKILL SYSTEM.
# Lancement : bash setup_backend_structure.sh (depuis la racine du projet)
# =============================================================================

set -e

echo "Génération de la structure backend AI DATA SKILL SYSTEM..."

# ── Liste des 7 Skills ──────────────────────────────────────────────────
SKILLS=(
    "etl_skill"
    "visualization_skill"
    "modeling_skill"
    "prediction_skill"
    "analysis_skill"
    "ml_explanation_skill"
    "nextjs_builder_skill"
)

# ── Structure de chaque Skill ───────────────────────────────────────────
for skill in "${SKILLS[@]}"; do
    echo "  → Skill : $skill"
    mkdir -p "backend/skills/$skill/core"
    mkdir -p "backend/skills/$skill/scripts"
    mkdir -p "backend/skills/$skill/examples"

    # Fichiers obligatoires (vides au départ, remplis à chaque étape)
    touch "backend/skills/$skill/SKILL.md"
    touch "backend/skills/$skill/api-guide.md"
    touch "backend/skills/$skill/scripts/main.py"
    touch "backend/skills/$skill/scripts/logic.py"
    touch "backend/skills/$skill/scripts/helpers.py"
    touch "backend/skills/$skill/scripts/__init__.py"
    touch "backend/skills/$skill/core/__init__.py"
    touch "backend/skills/$skill/examples/example_usage.py"
    touch "backend/skills/$skill/examples/sample_config.json"
    touch "backend/skills/$skill/examples/expected_output.md"
    touch "backend/skills/$skill/__init__.py"
done

# ── API FastAPI ─────────────────────────────────────────────────────────
echo "  → API FastAPI"
mkdir -p backend/api/routes
touch backend/api/__init__.py
touch backend/api/routes/__init__.py

# ── Schemas Pydantic ────────────────────────────────────────────────────
echo "  → Schémas Pydantic"
mkdir -p backend/schemas
touch backend/schemas/__init__.py

# ── LLM Orchestrator ────────────────────────────────────────────────────
echo "  → LLM Orchestrator (Gemini)"
mkdir -p backend/llm_orchestrator
touch backend/llm_orchestrator/__init__.py
touch backend/llm_orchestrator/router.py
touch backend/llm_orchestrator/planner.py
touch backend/llm_orchestrator/executor.py
touch backend/llm_orchestrator/prompt_engine.py

# ── Utilitaires ─────────────────────────────────────────────────────────
echo "  → Utilitaires (src/utils)"
mkdir -p backend/src/utils
touch backend/src/__init__.py
touch backend/src/utils/__init__.py
touch backend/src/utils/logger.py
touch backend/src/utils/config.py
touch backend/src/utils/helpers.py
touch backend/src/utils/directus_client.py

# ── Données et sorties ──────────────────────────────────────────────────
echo "  → Dossiers de données et sorties"
mkdir -p backend/data/raw backend/data/processed backend/data/external
mkdir -p backend/models backend/outputs

touch backend/data/raw/.gitkeep
touch backend/data/processed/.gitkeep
touch backend/data/external/.gitkeep
touch backend/models/.gitkeep
touch backend/outputs/.gitkeep

# ── Tests ───────────────────────────────────────────────────────────────
echo "  → Tests unitaires"
mkdir -p backend/tests
touch backend/tests/__init__.py
touch backend/tests/test_etl.py
touch backend/tests/test_visualization.py
touch backend/tests/test_modeling.py
touch backend/tests/test_prediction.py
touch backend/tests/test_ml_explanation.py
touch backend/tests/test_analysis.py
touch backend/tests/test_endpoints.py
touch backend/tests/test_pydantic_schemas.py
touch backend/tests/test_directus_client.py

# ── Notebooks ───────────────────────────────────────────────────────────
echo "  → Notebooks Jupyter"
mkdir -p backend/notebooks
touch backend/notebooks/.gitkeep

echo ""
echo "Structure backend générée avec succès."
```

### Exécution

```bash
# Depuis la racine ai-data-skill-system/
bash setup_backend_structure.sh
```

---

## Phase 0.4 — Variables d'environnement Backend

### Fichier `backend/.env.example`

Copier ce contenu dans `backend/.env.example`.

```bash
# =============================================================================
# .env.example — Configuration AI DATA SKILL SYSTEM 2026
# Stack : Next.js + FastAPI + Pydantic + Directus + Gemini
# =============================================================================
#
# UTILISATION :
#   1. Copier ce fichier : cp .env.example .env
#   2. Renseigner les valeurs ci-dessous
#   3. NE JAMAIS partager le fichier .env (clés secrètes)
# =============================================================================

# ── SECTION 1 — Données & Chemins ─────────────────────────────────────────
DATA_RAW_DIR=./data/raw
DATA_PROCESSED_DIR=./data/processed
DATA_EXTERNAL_DIR=./data/external
OUTPUTS_DIR=./outputs
MODELS_DIR=./models


# ── SECTION 2 — SDK Gemini (Orchestrateur IA) ─────────────────────────────

# Clé principale obligatoire (obtenir sur https://aistudio.google.com)
GEMINI_API_KEY=AIzaSy...RemplacerParVotreVraieCle

# Clés de rotation optionnelles (15 req/min par clé gratuite)
GEMINI_API_KEY_2=
# GEMINI_API_KEY_3=
# GEMINI_API_KEY_4=

# Modèle et paramètres
GEMINI_MODEL=gemini-2.5-flash
GEMINI_TEMPERATURE=0.2
GEMINI_MAX_TOKENS=1000
GEMINI_TIMEOUT=25


# ── SECTION 3 — Directus CMS (Stockage MDX) ───────────────────────────────

DIRECTUS_URL=http://localhost:8055

# Token admin à générer dans Directus (voir Phase 0.5)
DIRECTUS_TOKEN=RemplacerParVotreTokenAdminDirectus

# Identifiants admin (utilisés à l'init de Directus)
DIRECTUS_ADMIN_EMAIL=admin@aidataskill.local
DIRECTUS_ADMIN_PASSWORD=ChangerCeMotDePasse123


# ── SECTION 4 — FastAPI Backend ───────────────────────────────────────────

FASTAPI_PORT=8000
FASTAPI_HOST=127.0.0.1

# Origines CORS autorisées (URL de Next.js)
CORS_ORIGINS=http://localhost:3000


# ── SECTION 5 — ETL Skill ─────────────────────────────────────────────────

ETL_NULL_THRESHOLD=0.5
ETL_NUMERIC_IMPUTATION=median
ETL_CATEGORICAL_IMPUTATION=mode
ETL_IQR_MULTIPLIER=1.5
ETL_OUTLIER_STRATEGY=cap


# ── SECTION 6 — Modeling Skill ────────────────────────────────────────────

ML_TEST_SIZE=0.2
ML_CV_FOLDS=5
ML_RANDOM_STATE=42
ML_N_JOBS=-1
ML_AUTO_TUNING=true


# ── SECTION 7 — Environnement ─────────────────────────────────────────────

APP_ENV=development
LOG_LEVEL=INFO
DEBUG=false
```

### Génération du fichier `.env` réel

```bash
cd backend
cp .env.example .env
```

Ouvrir `backend/.env` dans un éditeur et renseigner trois valeurs critiques :

1. `GEMINI_API_KEY` avec la clé obtenue sur https://aistudio.google.com
2. `DIRECTUS_TOKEN` sera renseigné après la Phase 0.5
3. `DIRECTUS_ADMIN_PASSWORD` à changer pour un mot de passe fort

---

## Phase 0.5 — Directus CMS

### Initialisation

Depuis la racine du projet, dans un nouveau terminal.

```bash
mkdir directus && cd directus

npm init -y
npm install directus
```

Créer le fichier .env à la main. Copier ce contenu dans `directus/.env`.
```
KEY=$(node -e "console.log(require('crypto').randomBytes(32).toString('hex'))")
SECRET=$(node -e "console.log(require('crypto').randomBytes(32).toString('hex'))")

mkdir -p database

cat > .env << EOF
KEY="${KEY}"
SECRET="${SECRET}"

DB_CLIENT="sqlite3"
DB_FILENAME="./database/data.db"

ADMIN_EMAIL="admin@aidataskill.local"
ADMIN_PASSWORD="ChangerCeMotDePasse123"
EOF
```

### Démarrage

```bash
npx directus bootstrap

npx directus start
```

Sortie attendue.

```
✨ Server started at http://0.0.0.0:8055
```

Aller sur http://localhost:8055 et se connecter avec les identifiants admin.

### Création des 5 collections

Naviguer dans `Settings → Data Model → Create Collection`. Construire les 5 collections suivantes avec leurs champs exacts.

#### Collection 1 — `sessions`
* Rôle : Représente une exécution complète du pipeline IA — du moment où l'utilisateur lance une analyse jusqu'à la fin.
  
```
Collection name   : sessions
Primary key field : id (UUID, generate on create)

Champs :
- user_id          (String)
- dataset_name     (String) 
- started_at       (Datetime, default : CURRENT_TIMESTAMP) 
- ended_at         (Datetime, nullable) 
- skills_used      (JSON) 
- status           (Dropdown : running, success, error → default : running)
- duration_ms      (Integer, nullable) 
```

| Champ | Utilité concrète |
|---|---|
| `user_id` | Qui a lancé l'analyse: ID de l'utilisateur (email ou UUID) |
| `dataset_name` | Quel dataset traité: Nom du dataset analysé (ex: "titanic.csv") |
| `started_at` | Quand l'analyse a été lancée: Timestamp de début de session,  auto-rempli |
| `ended_at` | Quand l'analyse a été terminée: Timestamp de fin de session, rempli à la fin du pipeline, null si encore en cours |
| `skills_used` | Quels Skills ont été utilisés: Liste des Skills exécutés dans cette session (ex: ["ETL", "Visualization", "Modeling"]) |
| `status` | Statut global de la session: "running" tant que le pipeline n'est pas terminé, "success" si tout s'est bien passé, "error" si une erreur a interrompu le pipeline |
| `duration_ms` | Durée totale de la session en millisecondes: Calculé à la fin du pipeline (ended_at - started_at), null si encore en cours |


#### Collection 2 — `reports_mdx`

```
Collection name   : reports_mdx
Primary key field : id (UUID, generate on create)

Champs :
- session_id       (Relationship M2O → sessions)
- type             (Dropdown : etl, eda, model_card, analysis, explanation)
- title            (String)
- content_mdx      (Markdown/MDX)
- created_at       (Datetime, default : CURRENT_TIMESTAMP)
```


| Champ | Utilité concrète |
|---|---|
| `session_id` | Relie le rapport à sa session parente |
| `type` | Catégorie du rapport : `etl` (nettoyage), `eda` (exploration: Exploratory Data Analysis), `model_card` (fiche modèle), `analysis` (analyse), `explanation` (explication) |
| `title` | Titre du rapport affiché: "Rapport d'EDA", "Fiche Modèle XGBoost", etc. |
| `content_mdx` | Contenu du rapport au format MDX généré par LLM: texte enrichi + graphiques intégrés |
| `created_at` | Quand ce rapport a été produit |

#### Collection 3 — `charts`

```
Collection name   : charts
Primary key field : id (UUID, generate on create)

Champs :
- session_id       (Relationship M2O → sessions)
- title            (String)
- chart_type       (String : histogram, boxplot, heatmap, roc, confusion, shap)
- plotly_json      (JSON)
- png_file         (File, nullable, relation vers directus_files)
- created_at       (Datetime, default : CURRENT_TIMESTAMP)
```


| Champ | Utilité concrète |
|---|---|
| `session_id` | Relie le rapport à sa session |
| `title` | Titre du graphique affiché: "Distribution de l'âge", "Matrice de confusion", etc. |
| `chart_type` | Type de graphique pour le rendu frontend: histogram, boxplot, heatmap, roc, confusion, shap, etc. |
| `plotly_json` | Données du graphique au format JSON exporté par plotly (pour rendu interactif dans Next.js) |
| `png_file` | Fichier image statique du graphique (optionnel, utilisé pour les graphiques SHAP complexes qui ne s'intègrent pas bien en JSON) - Relation vers `directus_files` → image statique pour exports PDF |
| `created_at` | Quand ce graphique a été produit |

#### Collection 4 — `pipeline_logs`

```
Collection name   : pipeline_logs
Primary key field : id (UUID, generate on create)

Champs :
- session_id       (Relationship M2O → sessions)
- skill            (String)
- action           (String)
- status           (Dropdown : running, success, error)
- message          (Text)
- timestamp        (Datetime, default : CURRENT_TIMESTAMP)
```

| Champ | Utilité concrète |
|---|---|
| `session_id` | Relie le rapport à sa session parente |
| `skill` | Quel Skill est en cours d'exécution: "ETL", "Visualization", "Modeling", etc. |
| `action` | Quelle action précise est en cours: "Chargement du dataset" `"load_csv"`, "Nettoyage des valeurs manquantes"  `"remove_nulls"`, "Entraînement du modèle XGBoost" `"train_model"`, etc. |
| `status` | Statut de cette action : "running" tant que l'action n'est pas terminée, "success" si elle s'est bien passée, "error" si une erreur a interrompu cette action |
| `message` | Détails supplémentaires sur l'action  : messages d'erreur, métriques intermédiaires, etc. |
| `timestamp` | Quand cette action a été loggée |   
#### Collection 5 — `user_profiles`

```
Collection name   : user_profiles
Primary key field : id (UUID, generate on create)

Champs :
- user_id          (String, unique)
- sessions_count   (Integer, default : 0)
- last_active      (Datetime, default : CURRENT_TIMESTAMP)
- preferences      (JSON, default : {})
```

### Génération du token admin

Aller dans `Users → Access Tokens → Create Token`.

```
Name        : fastapi-backend-token
Expiration  : Never (ou 1 year)
Role        : Admin
```

Copier le token long (30+ caractères) et le coller dans `backend/.env` ligne `DIRECTUS_TOKEN=`.

### Export du snapshot de schéma (versionnable Git)

```bash
# Depuis le dossier directus/
mkdir -p snapshots
npx directus schema snapshot ./snapshots/schema.json
```

Le fichier `directus/snapshots/schema.json` est versionnable. Pour réappliquer le schéma sur un nouvel environnement, lancer `npx directus schema apply ./snapshots/schema.json`.

---

## Phase 0.6 — Frontend Next.js

### Initialisation Next.js

Depuis la racine du projet, dans un troisième terminal.

```bash
npx create-next-app@latest frontend --typescript --tailwind --app --eslint --no-src-dir --import-alias "@/*"
```

Réponses à l'assistant.

```
Would you like to use Turbopack for next dev? → No
Customize the default import alias?           → No (default @/*)
```

### Fichier `frontend/package.json`

REMPLACER intégralement le `package.json` généré par Next.js par ce contenu. Toutes les dépendances du projet sont incluses.

```json
{
  "name": "ai-data-skill-system-frontend",
  "version": "0.1.0",
  "private": true,
  "description": "Frontend Next.js 14 pour AI DATA SKILL SYSTEM — Plateforme Data Science Augmentée par IA",
  "scripts": {
    "dev": "next dev -p 3000",
    "build": "next build",
    "start": "next start -p 3000",
    "lint": "next lint",
    "type-check": "tsc --noEmit"
  },
  "dependencies": {
    "next": "14.2.18",
    "react": "18.3.1",
    "react-dom": "18.3.1",
    "@directus/sdk": "^17.0.2",
    "plotly.js": "^2.35.2",
    "react-plotly.js": "^2.6.0",
    "@mdx-js/react": "^3.1.0",
    "next-mdx-remote": "^5.0.0",
    "lucide-react": "^0.460.0",
    "recharts": "^2.13.3",
    "zustand": "^5.0.1"
  },
  "devDependencies": {
    "typescript": "^5.6.3",
    "@types/node": "^20.17.6",
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@types/plotly.js": "^2.33.4",
    "@types/react-plotly.js": "^2.6.3",
    "eslint": "^8.57.1",
    "eslint-config-next": "14.2.18",
    "tailwindcss": "^3.4.14",
    "postcss": "^8.4.49",
    "autoprefixer": "^10.4.20"
  }
}
```

### Installation des dépendances en une seule commande

```bash
cd frontend
rm -rf node_modules package-lock.json    # nettoyer le install initial de create-next-app
npm install
```

Toutes les librairies du projet sont installées en un seul `npm install`.

#### Fix 1 — `next.config.mjs`
```bash
cat > next.config.mjs << 'EOF'
/** @type {import('next').NextConfig} */
const nextConfig = {
  /* config options here */
};
export default nextConfig;
EOF
```

#### Fix 2 — `postcss.config.mjs` (syntaxe v3)
```bash
cat > postcss.config.mjs << 'EOF'
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
EOF
```

#### Fix 3 — `tailwind.config.js` (syntaxe v3)
```bash
rm -f tailwind.config.ts

cat > tailwind.config.js << 'EOF'
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
EOF
```


#### Fix 4 — `app/globals.css` (syntaxe v3)
```bash
cat > app/globals.css << 'EOF'
@tailwind base;
@tailwind components;
@tailwind utilities;
EOF
```

#### Fix 5 — `app/layout.tsx` (sans Google Fonts — pas d'accès réseau en dev local)
```bash
cat > app/layout.tsx << 'EOF'
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Data Skill System",
  description: "Plateforme Data Science Augmentée par IA",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}
EOF
```


### Vérification

```bash
# Lister les dépendances installées
npm list --depth=0
```

Tu dois voir `@directus/sdk`, `plotly.js`, `react-plotly.js`, `@mdx-js/react`, `next-mdx-remote`, `lucide-react`, `recharts`, `zustand` dans la liste.

### Vérification finale
```bash
npm run dev
# Attendu :
#  ▲ Next.js 14.2.18
#  ✓ Ready in ~5s
#  ✓ Compiled /

---

## Phase 0.7 — Variables d'environnement Frontend

### Fichier `frontend/.env.local.example`

Copier ce contenu dans `frontend/.env.local.example`.

```bash
# =============================================================================
# .env.local.example — Frontend Next.js AI DATA SKILL SYSTEM
# =============================================================================
#
# UTILISATION :
#   1. Copier ce fichier : cp .env.local.example .env.local
#   2. Renseigner les valeurs ci-dessous
#
# Variables préfixées NEXT_PUBLIC_ : exposées au navigateur
# Variables sans préfixe : côté serveur uniquement (Server Components, API Routes)
# =============================================================================

# ── URL du backend FastAPI ────────────────────────────────────────────────
# Dev local       : http://localhost:8000
# Production      : URL Railway/Render
NEXT_PUBLIC_FASTAPI_URL=http://localhost:8000


# ── URL du CMS Directus ───────────────────────────────────────────────────
# Dev local       : http://localhost:8055
# Production      : URL Railway/Render
NEXT_PUBLIC_DIRECTUS_URL=http://localhost:8055


# ── Token Directus (côté serveur uniquement) ──────────────────────────────
# Utilisé par les Server Components Next.js pour lire les rapports MDX.
# Générer un token "read-only" dans Directus pour le frontend.
DIRECTUS_TOKEN=RemplacerParVotreTokenReadOnlyDirectus
```

### Génération du fichier `.env.local` réel

```bash
cd frontend
cp .env.local.example .env.local
```

Renseigner `DIRECTUS_TOKEN` avec le même token généré à la Phase 0.5 (ou un token read-only séparé pour plus de sécurité).

---

## Phase 0.8 — Test de connexion des 3 services

### Fichier `backend/tests/test_setup.py`

Copier ce contenu dans `backend/tests/test_setup.py`.

```python
"""
backend/tests/test_setup.py — Test de connexion des 3 services.

Vérifie que :
  1. FastAPI répond sur le port 8000
  2. Directus répond sur le port 8055 et accepte le token
  3. Les 5 collections Directus sont bien construites
  4. Next.js répond sur le port 3000

À lancer après avoir démarré les 3 services en parallèle :
    python tests/test_setup.py
"""

import os
import sys
import httpx
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


FASTAPI_URL = f"http://localhost:{os.getenv('FASTAPI_PORT', '8000')}"
DIRECTUS_URL = os.getenv("DIRECTUS_URL", "http://localhost:8055")
NEXTJS_URL = "http://localhost:3000"
DIRECTUS_TOKEN = os.getenv("DIRECTUS_TOKEN")


def test_fastapi_health() -> bool:
    """Test 1 : FastAPI répond sur /health."""
    logger.info(f"Test FastAPI : {FASTAPI_URL}/health")
    try:
        response = httpx.get(f"{FASTAPI_URL}/health", timeout=5)
        response.raise_for_status()
        data = response.json()
        logger.info(f"  OK — Status : {data.get('status')}")
        logger.info(f"  Environment : {data.get('environment')}")
        logger.info(f"  Directus configuré : {data.get('directus_configured')}")
        logger.info(f"  Gemini configuré : {data.get('gemini_configured')}")
        return True
    except httpx.ConnectError:
        logger.error(f"  ECHEC — FastAPI ne répond pas")
        logger.error(f"  Démarrer : uvicorn api.main:app --reload --port 8000")
        return False
    except Exception as e:
        logger.error(f"  ECHEC — {e}")
        return False


def test_directus_ping() -> bool:
    """Test 2 : Directus répond sur /server/ping."""
    logger.info(f"Test Directus : {DIRECTUS_URL}/server/ping")
    try:
        response = httpx.get(f"{DIRECTUS_URL}/server/ping", timeout=5)
        response.raise_for_status()
        logger.info(f"  OK — Directus répond")
        return True
    except httpx.ConnectError:
        logger.error(f"  ECHEC — Directus ne répond pas")
        logger.error(f"  Démarrer : cd directus && npx directus start")
        return False
    except Exception as e:
        logger.error(f"  ECHEC — {e}")
        return False


def test_directus_auth() -> bool:
    """Test 3 : Le token Directus est valide et les 5 collections existent."""
    logger.info(f"Test Directus auth : {DIRECTUS_URL}/collections")
    if not DIRECTUS_TOKEN or DIRECTUS_TOKEN.startswith("Remplacer"):
        logger.error(f"  ECHEC — DIRECTUS_TOKEN non configuré dans .env")
        return False
    try:
        response = httpx.get(
            f"{DIRECTUS_URL}/collections",
            headers={"Authorization": f"Bearer {DIRECTUS_TOKEN}"},
            timeout=5,
        )
        response.raise_for_status()
        collections = response.json().get("data", [])
        user_collections = [
            c["collection"] for c in collections
            if not c["collection"].startswith("directus_")
        ]
        logger.info(f"  OK — Token valide")
        logger.info(f"  Collections utilisateur : {user_collections}")

        expected = {"sessions", "reports_mdx", "charts", "pipeline_logs"}
        missing = expected - set(user_collections)
        if missing:
            logger.warning(f"  ATTENTION — Collections manquantes : {missing}")
            logger.warning(f"  Les construire dans http://localhost:8055/admin/settings/data-model")
            return False
        return True
    except httpx.HTTPStatusError as e:
        logger.error(f"  ECHEC — Token invalide ou permissions insuffisantes : {e.response.status_code}")
        return False
    except Exception as e:
        logger.error(f"  ECHEC — {e}")
        return False


def test_nextjs_response() -> bool:
    """Test 4 : Next.js répond sur la racine."""
    logger.info(f"Test Next.js : {NEXTJS_URL}")
    try:
        response = httpx.get(NEXTJS_URL, timeout=5)
        response.raise_for_status()
        logger.info(f"  OK — Next.js répond")
        return True
    except httpx.ConnectError:
        logger.error(f"  ECHEC — Next.js ne répond pas")
        logger.error(f"  Démarrer : cd frontend && npm run dev")
        return False
    except Exception as e:
        logger.error(f"  ECHEC — {e}")
        return False


def main():
    """Lance les 4 tests et affiche le résumé."""
    logger.info("=" * 70)
    logger.info("AI DATA SKILL SYSTEM — Test de connexion des 3 services")
    logger.info("=" * 70)

    results = {
        "FastAPI Backend (8000)": test_fastapi_health(),
        "Directus Ping (8055)": test_directus_ping(),
        "Directus Auth + Collections": test_directus_auth(),
        "Next.js Frontend (3000)": test_nextjs_response(),
    }

    logger.info("=" * 70)
    logger.info("Résumé")
    logger.info("=" * 70)
    for service, ok in results.items():
        status = "OK" if ok else "ECHEC"
        logger.info(f"  [{status}] {service}")

    all_ok = all(results.values())
    if all_ok:
        logger.info("")
        logger.info("Les 3 services tournent et communiquent correctement.")
        logger.info("Étape 0 validée. Passe à l'Étape 1 (ETL Skill).")
        sys.exit(0)
    else:
        logger.error("")
        logger.error("Certains services ne répondent pas. Corriger avant de continuer.")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

### Démarrage des 3 services en parallèle

Ouvrir 3 terminaux distincts.

**Terminal 1 — Directus**

```bash
cd directus
npx directus start
```

**Terminal 2 — FastAPI Backend**

```bash
cd backend
source venv/bin/activate
uvicorn api.main:app --reload --port 8000
```

**Terminal 3 — Next.js Frontend**

```bash
cd frontend
npm run dev
```

### Lancement du test

**Terminal 4 — Test de connexion**

```bash
cd backend
source venv/bin/activate
python tests/test_setup.py
```

### Sortie attendue

```
======================================================================
AI DATA SKILL SYSTEM — Test de connexion des 3 services
======================================================================
INFO | Test FastAPI : http://localhost:8000/health
INFO |   OK — Status : healthy
INFO |   Environment : development
INFO |   Directus configuré : True
INFO |   Gemini configuré : True
INFO | Test Directus : http://localhost:8055/server/ping
INFO |   OK — Directus répond
INFO | Test Directus auth : http://localhost:8055/collections
INFO |   OK — Token valide
INFO |   Collections utilisateur : ['sessions', 'reports_mdx', 'charts', 'pipeline_logs', 'user_profiles']
INFO | Test Next.js : http://localhost:3000
INFO |   OK — Next.js répond
======================================================================
Résumé
======================================================================
  [OK] FastAPI Backend (8000)
  [OK] Directus Ping (8055)
  [OK] Directus Auth + Collections
  [OK] Next.js Frontend (3000)

Les 3 services tournent et communiquent correctement.
Étape 0 validée. Passe à l'Étape 1 (ETL Skill).
```

---

## Validation Finale de l'Étape 0

Cocher chaque case avant de passer à l'Étape 1.

```
[ ] Racine ai-data-skill-system/ initialisée avec git init
[ ] .gitignore copié à la racine
[ ] Backend venv créé et activé
[ ] requirements.txt rempli et installé via pip install -r requirements.txt
[ ] api/main.py rempli dans backend/api/main.py
[ ] Script setup_backend_structure.sh exécuté
[ ] .env.example rempli dans backend/
[ ] .env généré et 3 valeurs critiques renseignées (Gemini, Directus URL, Directus token)
[ ] Directus initialisé via npm init directus-project
[ ] 5 collections Directus créées (sessions, reports_mdx, charts, pipeline_logs, user_profiles)
[ ] Token admin Directus généré et reporté dans backend/.env
[ ] Snapshot du schéma exporté : directus/snapshots/schema.json
[ ] Next.js initialisé via create-next-app dans frontend/
[ ] package.json remplacé par la version complète (avec toutes les dépendances)
[ ] npm install exécuté dans frontend/ (toutes les dépendances en une commande)
[ ] .env.local rempli dans frontend/
[ ] test_setup.py rempli dans backend/tests/
[ ] Les 3 services démarrent sans erreur
[ ] python tests/test_setup.py affiche 4 OK
```

---

## Récapitulatif des chemins de fichiers

| Fichier | Chemin dans le projet |
|---------|------------------------|
| `.gitignore` | `ai-data-skill-system/.gitignore` |
| `requirements.txt` | `backend/requirements.txt` |
| `api/main.py` | `backend/api/main.py` |
| `setup_backend_structure.sh` | racine puis à supprimer après usage |
| `.env.example` | `backend/.env.example` |
| `.env` | `backend/.env` (jamais commité) |
| `package.json` | `frontend/package.json` |
| `.env.local.example` | `frontend/.env.local.example` |
| `.env.local` | `frontend/.env.local` (jamais commité) |
| `test_setup.py` | `backend/tests/test_setup.py` |
| `schema.json` | `directus/snapshots/schema.json` |

---

## Procédure de démarrage quotidien (après le setup initial)

Une fois l'Étape 0 finalisée, redémarrer le projet est simple. Ouvrir 3 terminaux.

```bash
# Terminal 1
cd directus && npx directus start

# Terminal 2
cd backend && source venv/bin/activate && uvicorn api.main:app --reload --port 8000

# Terminal 3
cd frontend && npm run dev
```

Aller sur http://localhost:3000 pour utiliser l'application.

---

*config.md — Étape 0 du projet AI DATA SKILL SYSTEM — Version 1.0*