# Backend — Moteur de recherche sémantique GED

Documentation technique du backend, destinée aux développeurs. Pour la documentation d'intégration destinée à l'entreprise, voir [`../INTEGRATION_GED.md`](../INTEGRATION_GED.md). Pour l'audit de performance et le plan d'action, voir [`../AUDIT.md`](../AUDIT.md).

---

## 1. Vue d'ensemble

API FastAPI exposant un moteur de **recherche hybride** (sémantique SBERT + FAISS, lexical BM25, fusion RRF) sur un corpus de documents (PDF, Word, Excel, PowerPoint, images) stocké dans `data/pdfs/`, avec :

- authentification par sessions (cookie httpOnly + Bearer) ;
- synchronisation incrémentale dossier ↔ index ↔ base ;
- OCR automatique des documents scannés ;
- cache LRU des recherches, métriques de latence, logs rotatifs.

**Stack :** Python 3.11+, FastAPI, FAISS (cpu), sentence-transformers, MariaDB/MySQL (SQL brut, sans ORM), RapidOCR (ONNX).

---

## 2. Démarrage rapide

```bash
# Prérequis : MySQL/MariaDB actif sur 127.0.0.1:3306 (XAMPP), Python 3.11+
cd backend
pip install -r requirements.txt

# Configurer .env (voir section 10) puis :
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Au premier lancement : création automatique de la base + des tables, indexation du corpus (plusieurs minutes si OCR), puis la recherche devient disponible (`/health` → `index_loaded: true`). Aux lancements suivants : **chargement de l'index existant (~7 s), aucune réindexation** sauf fichiers modifiés.

| Commande | Rôle |
|---|---|
| `python -m uvicorn app:app --host 127.0.0.1 --port 8000` | lancer l'API |
| `python -m pytest tests/ -q` | suite de tests unitaires |
| `python tests/benchmark_search.py` | benchmark indexation + latence + cache |
| `python -m ruff check .` | lint (config dans `pyproject.toml`) |

---

## 3. Architecture en couches

```
app.py                     FastAPI : lifespan, CORS, middleware de log, routeurs
  │
  ├── controllers/         Routes HTTP (une par domaine), aucune logique métier
  │     ├── auth.py        /auth/*  : inscription, login, sessions, mots de passe
  │     └── documents.py   /search, /sync, /documents, /files, /health, /metrics
  │
  ├── middleware/auth.py   Dépendance get_current_user (cookie httpOnly → Bearer)
  ├── models/auth.py       Schémas Pydantic des requêtes
  │
  ├── services/            Logique métier pure (pas de Request/Response ici)
  │     ├── search/
  │     │    ├── search_engine.py    Pipeline complet + recherche hybride + cache
  │     │    ├── text_extractor.py   Extraction texte (PDF/Office/images/OCR)
  │     │    ├── embedder.py         SBERT (modèle singleton par nom)
  │     │    ├── vector_index.py     FAISS : création, recherche, persistance shards
  │     │    └── bm25.py             BM25 Okapi en Python pur + tokenizer FR
  │     ├── sync_service.py         Détection changements + sync incrémentale
  │     ├── state.py                État partagé (engine) + verrou de swap
  │     └── auth.py                 Hachage, tokens, validation mot de passe
  │
  ├── repositories/        Accès SQL brut (mysql-connector, pool de connexions)
  │     ├── connection.py  Pool + context manager get_connection()
  │     ├── setup.py       CREATE DATABASE + CREATE TABLE au démarrage
  │     ├── documents.py   CRUD documents (+ schema)
  │     └── users.py       Users, sessions, tokens (+ schemas)
  │
  ├── config/              __init__.py : chemins + paramètres (.env) ; ratelimit.py
  ├── shared/              logger (rotatif), metrics (latence P95/P99), serialization
  ├── clients/email.py     Envoi SMTP (vérification email, reset password)
  ├── data/pdfs/           CORPUS : un sous-dossier = une catégorie
  ├── data/index/          INDEX persistant : shards FAISS + meta + manifeste
  └── tests/               pytest + benchmark + simulations d'audit
```

**Règle de dépendance :** `controllers → services → repositories → config`. Les services ne connaissent jamais HTTP ; les repositories ne contiennent aucune logique métier.

---

## 4. Le moteur de recherche

### 4.1 Pipeline d'indexation (`build_search_engine`)

```
fichier → extraction texte → découpage en passages → embedding SBERT → index FAISS par catégorie
```

1. **Extraction** (`text_extractor.py`) — pypdf pour le texte natif ; OCR conditionnel en 3 cas : (A) texte extractible sans images raster → pas d'OCR ; (B) texte + images raster → OCR des images dédupliquées ; (C) texte absent ou illisible (`looks_garbled`) → OCR complet parallèle des pages (rendu pypdfium2 200 dpi → RapidOCR, `OCR_WORKERS` threads).
2. **Découpage** (`chunk_text`) — passages de `CHUNK_SIZE` caractères avec recouvrement `CHUNK_OVERLAP`, coupure de préférence en fin de ligne.
3. **Embedding** (`embedder.py`) — `paraphrase-multilingual-MiniLM-L12-v2` (384 dims, normalisés L2), modèle mis en cache (singleton par nom).
4. **Sharding FAISS** (`vector_index.py`) — un index par catégorie (dossier de premier niveau) : `IndexHNSWFlat` (M=32, efSearch=64) si ≥ 2×M vecteurs, sinon `IndexFlatIP` exact. Cosinus = produit scalaire sur vecteurs normalisés.

### 4.2 Recherche hybride (`search_documents`)

```
requête ─┬─ embed_query → FAISS (par shard) ──→ rangs denses
         ├─ tokenize → BM25 global ──────────→ rangs lexicaux
         └─ fusion RRF : score = Σ 1/(60 + rang)
              + boost ×2 si termes exacts dans le passage
              + injection des passages exacts non récupérés
              ↓
      agrégation par document (moyenne des 3 meilleurs passages)
              + boost ×3 si le document contient les termes exacts
              ↓
      seuil cosinus (RELEVANCE_THRESHOLD) sauf match lexical exact
      → filtres file_type / category → top_k résultats
```

- Le **BM25 est global** (sur tous les passages de tous les shards) pour garder un IDF fiable et un classement identique à un index unique.
- **Cache LRU** (`SearchCache`) : clé sha256 de `(requête, top_k, catégorie, type)`, TTL 5 min, 128 entrées, stats sur `/search/cache-stats`. Invalide à chaque synchronisation.
- `_generate_suggestions` : si 0 résultat, essaie les termes seuls puis par paires pour proposer des requêtes alternatives.

### 4.3 Paramètres moteur (`config/__init__.py`)

| Variable (env) | Défaut | Rôle |
|---|---|---|
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | 900 / 150 | taille et recouvrement des passages (chars) |
| `RELEVANCE_THRESHOLD` | 0.30 | cosinus minimal du meilleur passage (anti faux positifs) |
| `RRF_K` | 60 | constante de la fusion Reciprocal Rank Fusion |
| `FAISS_INDEX_TYPE` | hnsw | `hnsw` (approximatif, rapide) ou `flat` (exact) |
| `HNSW_M` / `HNSW_EF_SEARCH` | 32 / 64 | qualité/vitesse HNSW (recall ↑ si efSearch ↑) |
| `OCR_ENABLED` / `OCR_WORKERS` | false / 4 | OCR des scannés + parallélisme |

⚠️ Changer `CHUNK_SIZE`/`CHUNK_OVERLAP` modifie l'alignement passages↔vecteurs : forcer une reconstruction complète (supprimer `data/index/`) puis `/sync`.

---

## 5. Persistance de l'index (`data/index/`)

| Fichier | Contenu |
|---|---|
| `documents_<Catégorie>.faiss` | index FAISS du shard (vecteurs normalisés) |
| `documents_<Catégorie>.faiss.meta.json` | `chunk_relative_paths` (**un chemin par passage**, donc doublons possibles) + `model_name` |
| `shards.json` | manifeste : liste des catégories + nom du modèle |

Le rechargement au démarrage (`build_engine_from_saved_state`) : lit le manifeste → pour chaque shard, FAISS + meta → **déduplique** les chemins pour reconstruire les documents uniques depuis la base → re-découpe les textes et **vérifie l'alignement exact** (même séquence passage→document que la meta) → reconstruit les vecteurs cachés (`reconstruct_n`) et le BM25 global. Tout écart ⇒ retour `None` ⇒ reconstruction complète propre. `documents.faiss` à la racine est un vestige de l'avant-sharding (inutilisé).

---

## 6. Synchronisation (`sync_service.py`)

**Au démarrage** (thread de fond, `/search` répond 503 tant que non prêt) :
1. `build_engine_from_saved_state()` — recharge l'index persistant si cohérent ;
2. `run_sync()` — `detect_document_changes()` : scan léger du dossier (mtime sans hash) vs base ; seuls les fichiers dont le mtime a changé sont relus pour recalculer le SHA-256 ;
3. si changements → `apply_incremental_sync()` : seuls les **shards touchés** sont reconstruits, en **réutilisant les vecteurs des passages inchangés** (seuls les fichiers ajoutés/modifiés sont extraits et embeddés) ; le moteur neuf est swapé atomiquement sous `search_state_lock` ; cache de recherche invalidé ; shards sauvegardés.

**Via `POST /sync`** (authentifié) : même chemin, synchrone ; 409 si déjà en cours. Le swap atomique garantit qu'une recherche concurrente ne voit jamais un état à moitié mis à jour.

---

## 7. Base de données

Créée automatiquement au démarrage (`utf8mb4`). Pool de connexions (`DB_POOL_SIZE`, défaut 5). **Toute écriture doit faire `conn.commit()`** (autocommit désactivé).

| Table | Rôle |
|---|---|
| `documents` | catalogue : chemins, type, mtime, `content_hash` (SHA-256), `extracted_text` (LONGTEXT). Clé unique `relative_path`. |
| `users` | comptes : nom, email unique, `password_hash` (bcrypt), `is_email_verified` |
| `user_sessions` | sessions : `token_hash` (le token brut n'est jamais stocké), expiration, remember_me |
| `email_verification_tokens` / `password_reset_tokens` | tokens hachés avec expiration (24 h / 1 h) |

> Les tables `search_history` et `document_access_history` présentes en base ne sont plus utilisées par le code (vestiges) — l'historique de recherche est côté client (localStorage).

---

## 8. API

Spec interactive : `http://127.0.0.1:8000/docs` (OpenAPI). Auth : cookie `ged_auth` (httpOnly) **ou** `Authorization: Bearer <token>` — le fallback Bearer est indispensable quand le front est servi d'un autre site (ex. `localhost:5500` → `127.0.0.1:8000`, cookies SameSite).

| Route | Auth | Description |
|---|---|---|
| `POST /auth/register` (5/min) | — | Création de compte + email de vérification |
| `GET /auth/verify-email?token=` | — | Validation de l'email |
| `POST /auth/login` (5/min) | — | Session : pose le cookie + renvoie `token`, `expires_at` |
| `POST /auth/logout` | ✔ | Fermeture de session |
| `GET /auth/me` | ✔ | Utilisateur courant |
| `PUT /auth/profile` / `PUT /auth/change-password` / `POST /auth/forgot-password` / `POST /auth/reset-password` / `DELETE /auth/delete-account` | ✔/— | Gestion du compte |
| `POST /search` | ✔ | Recherche hybride : `query`, `top_k` (1–50), `category`, `file_type` |
| `GET /search/cache-stats` / `POST /search/export` | ✔ | Stats du cache / export CSV des résultats |
| `GET /documents?limit=&offset=` | ✔ | Catalogue paginé |
| `GET /files/{chemin_relatif}` | ✔ | Fichier (protection path traversal) |
| `POST /sync` | ✔ | Sync incrémentale (409 si en cours) |
| `GET /health` | — | Sonde : index prêt, sync en cours, nb documents |
| `GET /metrics` | ✔ | Latence recherche (moy/P95/P99), erreurs, sync |
| `GET /` , `GET /dashboard/summary` | —/✔ | Infos moteur / résumé tableau de bord |

Erreurs : 400 paramètre invalide · 401 session absente/expiree · 403 email non vérifié · 409 sync en cours · 429 rate limit · 503 index pas prêt.

---

## 9. Sécurité

Mots de passe bcrypt + validation de robustesse ; sessions par token haché SHA-256 (révocables serveur) ; cookie httpOnly avec `COOKIE_SECURE`/`COOKIE_SAMESITE` configurables ; protection path traversal sur `/files` ; rate limiting slowapi (login, register, forgot-password) ; CORS limité à `CORS_ORIGINS` ; identifiant SQL validé par regex dans `setup.py` ; logs rotatifs (2 Mo × 5) dans `logs/backend.log`.

---

## 10. Configuration `.env`

```ini
DB_HOST=127.0.0.1        DB_PORT=3306
DB_NAME=semantic_search  DB_USER=root       DB_PASSWORD=...
DB_POOL_SIZE=5
CORS_ORIGINS=http://127.0.0.1:5500,http://localhost:5500
FRONTEND_BASE_URL=http://127.0.0.1:5500     # liens vérification/reset
SESSION_COOKIE_NAME=ged_auth  COOKIE_SECURE=false  COOKIE_SAMESITE=lax
SMTP_HOST=  SMTP_PORT=587  SMTP_USER=  SMTP_PASSWORD=  SMTP_FROM_EMAIL=  SMTP_FROM_NAME=ged
OCR_ENABLED=true  OCR_WORKERS=4
FAISS_INDEX_TYPE=hnsw  HNSW_M=32  HNSW_EF_SEARCH=64
```

---

## 11. Tests

| Fichier | Couverture |
|---|---|
| `test_bm25.py` | tokenizer (stopwords FR, accents) + classement BM25 |
| `test_embedder.py` | embedding requête/textes, erreurs |
| `test_vector_index.py` | création/recherche/persistance FAISS |
| `test_text_extractor.py` | extraction PDF/Office/images, détection OCR |
| `test_search_engine.py` / `test_search_top1.py` | pipeline, filtres, seuil, cache |
| `test_api_integration.py` | endpoints via TestClient |
| `benchmark_search.py` | indexation, latence avg/P95/P99, hit-rate cache |
| `audit_scale_sim.py` / `audit_inverted_index_sim.py` | simulations de charge 10k–100k docs (audit) |

---

## 12. Conventions de code

- Code, commentaires et logs **en français sans accents** ; format ruff (ligne 120, isort first-party : `config, services, repositories, middleware, shared, models`) ;
- SQL brut paramétré (jamais de f-string SQL) ; écritures toujours committées ;
- état du moteur : ne jamais muter `search_state["engine"]` en place — construire un dict neuf puis swap sous `search_state_lock` ;
- secrets uniquement dans `.env` (jamais commité).

## 13. Limitations connues

Voir [`../AUDIT.md`](../AUDIT.md) pour le détail chiffré : BM25 sans index inversé et scans complets du corpus (latence ~2–3 s/requête à 100k docs — optimisation mesurée à ~100× disponible en phase 2), mémoire du BM25 à l'échelle, ingestion couplée au dossier local (API d'ingestion push à prévoir pour la GED cible), `/sync` synchrone.
