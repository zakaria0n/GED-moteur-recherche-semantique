"""Configuration simple du backend.

Ce fichier centralise les chemins locaux et les constantes de configuration.
"""

import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
PDFS_DIR = DATA_DIR / "pdfs"
INDEX_DIR = DATA_DIR / "index"
FAISS_INDEX_PATH = INDEX_DIR / "documents.faiss"
LOG_DIR = BASE_DIR / "logs"

# --- Parametres du moteur de recherche semantique ---
# Decoupage des textes en passages. Le modele SBERT tronque a ~128 tokens
# (~900 caracteres) : on utilise des passages plus grands qu'avant pour
# capturer plus de contexte et produire de meilleurs embeddings.
CHUNK_SIZE = 900
CHUNK_OVERLAP = 150
# Similarite cosinus minimale (sur le meilleur passage dense) pour qu'un
# document soit considere comme pertinent. En dessous -> aucun resultat.
RELEVANCE_THRESHOLD = 0.30
# Constante de la fusion RRF (Reciprocal Rank Fusion) entre dense et BM25.
RRF_K = 60
# Type d'index FAISS : "hnsw" (recherche approximative sous-lineaire, rapide a
# grande echelle) ou "flat" (exact, lineaire). HNSW ne necessite pas d'entrainement.
FAISS_INDEX_TYPE = os.getenv("FAISS_INDEX_TYPE", "hnsw")
# Parametres HNSW (qualite/perf) : M = nb de voisins par noeud, efSearch = profondeur
# de la recherche (>= au top_k vise). Plus eleve = meilleur rappel, un peu plus lent.
HNSW_M = int(os.getenv("HNSW_M", "32"))
HNSW_EF_SEARCH = int(os.getenv("HNSW_EF_SEARCH", "64"))

# OCR des PDF : desactive par defaut. L'OCR est tres lent (ordres de grandeur plus
# lent que l'extraction de texte) ; l'activer sur un gros corpus ralentit l'indexation.
OCR_ENABLED = os.getenv("OCR_ENABLED", "false").lower() in ("1", "true", "yes")
# Nombre de threads pour l'OCR parallele (RapidOCR/ONNX libere le GIL).
OCR_WORKERS = int(os.getenv("OCR_WORKERS", "4"))


DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_NAME = os.getenv("DB_NAME", "semantic_search")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

# Cookie de session (httpOnly, non lisible par le JS -> reduit le risque XSS).
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "ged_auth")
# True obligatoire en production (HTTPS). False autorise le dev en http local.
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() in ("1", "true", "yes")
# Politique SameSite du cookie. "lax" suffit si front et back sont sur le meme site
# (ex: localhost, ou meme domaine en prod). "none" est REQUISE si le front et le back
# sont sur des sous-domaines differents (ex: app.entreprise.com + api.entreprise.com)
# et doit alors etre combinee a COOKIE_SECURE=true.
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax")

# Taille du pool de connexions MariaDB/MySQL (evite d'ouvrir une connexion par requete).
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))

FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://127.0.0.1:5500")
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "ged")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "no-reply@ged.local")

EMAIL_VERIFICATION_HOURS = 24
PASSWORD_RESET_HOURS = 1
SESSION_HOURS = 24
REMEMBER_ME_DAYS = 30
