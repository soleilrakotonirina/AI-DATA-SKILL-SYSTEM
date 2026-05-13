
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

