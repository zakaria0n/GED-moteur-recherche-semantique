# GED — Moteur de recherche sémantique

Plateforme de Gestion Électronique de Documents (GED) avec **moteur de recherche hybride** : sémantique (SBERT + FAISS, comprend le *sens* des requêtes) et lexical (BM25, précision sur les termes exacts), fusionnés par RRF — avec OCR automatique des documents scannés.

## Contenu du projet

| Dossier / fichier | Rôle |
|---|---|
| `backend/` | API FastAPI : moteur de recherche, indexation, authentification (voir `backend/README.md`) |
| `frontend/` | Interface web statique (HTML/CSS/JS, sans framework) |
| `INTEGRATION_GED.md` | **Documentation d'intégration** — déploiement, API, scénarios d'intégration dans une GED existante |
| `AUDIT.md` | Audit technique chiffré : performances, montée en charge, plan d'action |
| `projet.md` | Fiche descriptive du sujet |

## Démarrage rapide

```bash
# 1. MySQL/MariaDB actif sur 127.0.0.1:3306 (XAMPP)

# 2. Backend — terminal 1
cd backend
pip install -r requirements.txt
copy .env.example .env        # puis renseigner les valeurs (Windows)
python -m uvicorn app:app --host 127.0.0.1 --port 8000

# 3. Frontend — terminal 2
cd frontend
python -m http.server 5500 --bind 127.0.0.1

# 4. Ouvrir http://localhost:5500  (API docs : http://127.0.0.1:8000/docs)
```

Documents à indexer : déposer les fichiers dans `backend/data/pdfs/<Catégorie>/` puis `POST /sync` (l'indexation initiale tourne automatiquement au premier démarrage ; les suivantes chargent l'index existant en quelques secondes).
