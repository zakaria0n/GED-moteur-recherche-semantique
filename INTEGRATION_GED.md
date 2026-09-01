# Moteur de recherche sémantique — Documentation d'intégration GED

**Version :** 1.0 — 30 août 2026
**Destinataires :** équipes IT de l'entreprise (intégration, exploitation) et décideurs projet
**Objet :** présenter le moteur de recherche sémantique développé pour la plateforme GED et décrire les modalités concrètes de son intégration dans la GED de production de l'entreprise.

---

## 1. Résumé à destination des décideurs

Les moteurs de recherche des GED du marché reposent majoritairement sur une recherche **lexicale par mots-clés** : ils trouvent les documents *contenant* les mots tapés, mais échouent dès que l'utilisateur formule sa demande avec d'autres termes (synonymes, vocabulaire métier différent, fautes de formulation).

Le moteur livré ici ajoute une **recherche sémantique** : il comprend le *sens* de la requête et retrouve les documents pertinents même sans mot-clé commun, tout en conservant la précision du lexical pour les recherches exactes (numéros de dossier, noms de formulaires, références).

**Bénéfices attendus :**
- moins de recherches infructueuses (l'utilisateur trouve même sans connaître le vocabulaire exact du document) ;
- moins de temps perdu à retrouver un document (extrait contextuel directement dans les résultats) ;
- un composant **autonome et léger** : aucune infrastructure externe (pas de service cloud, pas de base vectorielle dédiée), déployable sur un serveur interne, ce qui répond aux exigences de souveraineté et de confidentialité documentaire.

**État :** prototype fonctionnel et testé sur corpus réel (extraits, contrats, factures, documents scannés). Les performances mesurées et le plan de montée en charge vers 100 000 documents sont détaillés en section 8 et dans le rapport d'audit (`AUDIT.md`) joint au livrable.

---

## 2. Fonctionnement général

### 2.1 Principe

```
                         ┌──────────────────────────────────────────────────┐
                         │                BACKEND (FastAPI)                 │
                         │                                                  │
 Documents  ──────────►  │  1. Extraction du texte                          │
 (PDF, Word,             │     (PDF natif, OCR si scanné, Word,             │
 Excel, PPT,             │      Excel, PowerPoint, images)                  │
 images)                 │                                                  │
                         │  2. Découpage en passages (~900 caractères)      │
                         │                                                  │
                         │  3. Vectorisation sémantique (SBERT, 384 dim.)   │
                         │                                                  │
                         │  4. Indexation :  FAISS (sens)                   │
                         │                  + BM25 (mots-clés)              │
                         │                                                  │
 Requête utilisateur ──► │  5. Recherche hybride  :  FAISS + BM25           │
                         │     fusion des classements (RRF)                 │
                         │     + filtres (catégorie, type de fichier)       │
                         │                                                  │
              ◄───────── │  6. Résultats classés + extraits contextuels     │
   GED / Interface web    └──────────────────────────────────────────────────┘
```

### 2.2 Pourquoi une recherche « hybride » ?

| Composante | Rôle | Exemple |
|---|---|---|
| **Sémantique** (SBERT + FAISS) | comprend le sens de la requête | « fin de contrat » retrouve une **lettre de démission** |
| **Lexicale** (BM25) | précision sur les termes exacts | « RIB 2024-0117 » retrouve le document contenant exactement cette référence |
| **Fusion RRF** | combine les deux classements en un seul, stable et robuste | — |

Chaque document est découpé en **passages** d'environ 900 caractères : la recherche sémantique travaille au niveau du passage (bien plus précis que le document entier), puis les résultats sont **regroupés par document** avec leur meilleur extrait.

### 2.3 Formats de documents supportés

| Type | Formats | Traitement |
|---|---|---|
| PDF natif | `.pdf` | extraction directe du texte |
| PDF scanné | `.pdf` | **OCR automatique** (détection du cas + OCR en parallèle) |
| Word / Excel / PowerPoint | `.docx` `.xlsx` `.pptx` | extraction du texte |
| Images | `.png` `.jpg` `.jpeg` `.bmp` `.tiff` `.webp` `.gif` | OCR |

Un fichier sans texte exploitable est répertorié mais exclu de l'index (et signalé dans les logs).

---

## 3. Déploiement

### 3.1 Prérequis

| Élément | Exigence |
|---|---|
| OS | Windows ou Linux |
| Python | 3.11 ou 3.12 |
| Base de données | MariaDB ou MySQL 10.x (métadonnées et textes extraits) |
| CPU | 4 cœurs suffisent (le moteur fonctionne 100 % sur CPU, sans GPU) |
| RAM | 8 Go recommandés jusqu'à ~10 000 documents ; 16 Go au-delà (cf. § 8) |
| Disque | corpus + ~1,5 Ko d'index par passage indexé + textes extraits en base |
| Réseau | accès HTTP entre la GED et le service ; serveur SMTP optionnel (emails de vérification/réinitialisation) |

### 3.2 Installation

```bash
cd backend
pip install -r requirements.txt
```

Créer le fichier `backend/.env` :

```ini
# Base de données
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=semantic_search
DB_USER=ged_user
DB_PASSWORD=********

# Origine autorisée pour la démo web (CORS, séparées par des virgules)
CORS_ORIGINS=http://127.0.0.1:5500

# URL de base du portail (liens de vérification / réinitialisation email)
FRONTEND_BASE_URL=http://127.0.0.1:5500

# SMTP (emails de vérification et de réinitialisation de mot de passe)
SMTP_HOST=smtpentreprise.local
SMTP_PORT=587
SMTP_USER=no-reply@entreprise.ma
SMTP_PASSWORD=********
SMTP_FROM_EMAIL=no-reply@entreprise.ma
SMTP_FROM_NAME=GED

# OCR des documents scannés (true recommandé pour une GED)
OCR_ENABLED=true
OCR_WORKERS=4
```

Au premier démarrage, le service crée automatiquement le schéma de base, scanne le dossier de documents, extrait les textes et construit l'index. La recherche répond `503` (indexation en cours) tant que l'index n'est pas prêt — l'état est consultable en continu via `GET /health`.

```bash
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

### 3.3 Alimentation en documents (mode actuel)

Le moteur surveille un **dossier de documents** organisé en sous-dossiers par catégorie :

```
backend/data/pdfs/
├── Contrats/       ← chaque sous-dossier = une catégorie filtrable
├── Factures/
├── Salaires/
└── ...
```

- **Ajout / modification / suppression** d'un fichier dans l'arborescence, puis déclenchement de `POST /sync` (authentifié) : la synchronisation est **incrémentale** — seuls les fichiers ajoutés ou modifiés sont retraités, les vecteurs déjà calculés sont réutilisés.
- Une synchronisation est également lancée automatiquement au démarrage du service.

---

## 4. Authentification

Tous les endpoints (hors `/` et `/health`) exigent une session authentifiée. Deux mécanismes sont supportés, utiles selon le mode d'intégration :

1. **Cookie de session `ged_auth` (httpOnly)** — pour l'intégration navigateur (interface web GED). Posé automatiquement par le login.
2. **En-tête `Authorization: Bearer <token>`** — pour l'**intégration serveur-à-serveur** (backend GED → moteur). Le token est retourné dans la réponse du login.

Obtenir une session :

```http
POST /auth/login
Content-Type: application/json

{ "email": "service.ged@entreprise.ma", "password": "********" }
```

Réponse :

```json
{
  "message": "Connexion reussie",
  "token": "a1b2c3...",
  "expires_at": "2026-08-31T14:00:00",
  "user": { "id": 3, "email": "service.ged@entreprise.ma", "full_name": "Service GED" }
}
```

Durée de session : 24 h par défaut, 30 jours avec `remember_me: true`. Limite anti-abus : 5 tentatives de login par minute par IP.

> **Note pour la production :** pour l'intégration GED, il est recommandé de créer un compte de service dédié (ex. `service.ged@entreprise.ma`). La roadmap prévoit un mécanisme de clé d'API propre aux intégrations machine (§ 9).

---

## 5. Référence API

Base : `http://<hote>:8000` — spécification OpenAPI interactive auto-générée : `http://<hote>:8000/docs`.

| Méthode & route | Auth | Rôle |
|---|---|---|
| `POST /search` | ✔ | **Recherche** dans l'index (endpoint principal) |
| `GET /health` | — | État du service (index prêt ? sync en cours ? nb de documents) |
| `GET /` | — | Informations générales + liste des catégories |
| `GET /documents?limit=&offset=` | ✔ | Catalogue des documents indexés (paginé) |
| `GET /files/{chemin_relatif}` | ✔ | Téléchargement/consultation d'un document |
| `POST /sync` | ✔ | Synchronisation incrémentale du dossier de documents |
| `GET /metrics` | ✔ | Métriques de performance (latence P95/P99, erreurs, sync) |
| `POST /search/export` | ✔ | Export CSV des résultats d'une recherche |
| `POST /auth/login` / `logout` | — | Session |
| `POST /auth/register`, `/auth/verify-email`, `/auth/forgot-password`, `/auth/reset-password` | — | Gestion de comptes (utile en mode portail autonome) |

### 5.1 Recherche — `POST /search`

```http
POST /search
Authorization: Bearer <token>
Content-Type: application/json

{
  "query": "demande de congé annuel",
  "top_k": 5,
  "category": "Administratif",
  "file_type": ".pdf"
}
```

| Champ | Type | Obligatoire | Description |
|---|---|---|---|
| `query` | string | ✔ | Requête en langage naturel (français ou multilingue) |
| `top_k` | int | — (défaut 5) | Nombre maximum de résultats, entre 1 et 50 |
| `category` | string | — | Filtre par catégorie = nom du sous-dossier (liste via `GET /`) |
| `file_type` | string | — | Filtre par extension (`.pdf`, `.docx`, `.xlsx`, …) |

Réponse :

```json
{
  "query": "demande de congé annuel",
  "results_count": 2,
  "results": [
    {
      "path": "D:/ged/pdfs/Administratif/administratif_demande_conge_003.pdf",
      "relative_path": "Administratif/administratif_demande_conge_003.pdf",
      "file_name": "administratif_demande_conge_003.pdf",
      "file_type": ".pdf",
      "score": 0.612,
      "aggregated": 0.014234,
      "text_preview": "…Demande de congé annuel — Je soussigné, demande à bénéficier de mon congé annuel…"
    }
  ],
  "suggestions": []
}
```

**Exploitation des champs par l'interface GED :**

- `results[]` — liste classée par pertinence décroissante.
- `score` — similarité cosinus sémantique du meilleur passage (0–1). À afficher si besoin.
- `aggregated` — score global (fusion sémantique + lexicale). La pertinence *relative* entre résultats d'une même recherche se calcule en le normalisant sur le meilleur résultat (c'est ce que fait la démo web pour afficher un pourcentage).
- `text_preview` — extrait du passage le plus pertinent, prêt à afficher sous le titre du document.
- `relative_path` — identifiant du document pour l'API : à passer à `GET /files/{chemin}` pour ouvrir le document.
- `suggestions` — si 0 résultat, propositions de requêtes alternatives (mots de la requête qui, pris seuls, matchent) ; vide sinon.

**Codes d'erreur :**

| Code | Signification |
|---|---|
| 400 | `top_k` hors bornes ou paramètre invalide |
| 401 | session absente/expirée |
| 429 | trop de requêtes (rate limiting auth) |
| 503 | index pas encore prêt (indexation initiale) — réessayer après `GET /health` → `index_loaded: true` |
| 500 | erreur interne (détail dans les logs serveur) |

### 5.2 Santé du service — `GET /health` (sans authentification)

```json
{
  "api": "ok",
  "index_loaded": true,
  "sync_running": false,
  "documents_indexed": 158,
  "categories_count": 9,
  "last_sync_message": "Synchronisation terminee - 158 documents indexes"
}
```

À utiliser pour : sonde de supervision (load balancer / Nagios / Zabbix), attente de disponibilité après déploiement, affichage d'un bandeau « indexation en cours » côté GED.

### 5.3 Synchronisation — `POST /sync`

Déclenche la détection des changements du dossier de documents (ajouts, modifications, suppressions) et met l'index à jour **incrémentalement**. Répond `409` si une synchronisation est déjà en cours. À planifier (cron/tâche planifiée GED) après chaque injection de documents, ou périodiquement (ex. toutes les 5 min).

---

## 6. Scénarios d'intégration dans votre GED

### Mode A — Recherche déléguée (disponible dès aujourd'hui)

La GED conserve sa gestion documentaire existante et **délègue la recherche** au moteur :

1. un job planifié (ou un export nocturne) dépose/copie les documents de la GED dans l'arborescence `data/pdfs/<Catégorie>/` ;
2. la GED appelle `POST /sync` ;
3. les utilisateurs cherchent depuis l'interface GED : le backend GED appelle `POST /search` (Bearer) et met en forme les résultats ;
4. l'ouverture du document se fait soit via `GET /files/{relative_path}` (le moteur sert le fichier), soit par l'URL propre de la GED (en reliant `file_name`/métadonnées à l'identifiant GED).

**Effort :** quelques jours. **Aucune modification du moteur.** C'est le mode recommandé pour une première mise en production.

### Mode B — Portail autonome (disponible aujourd'hui)

Le livrable inclut une interface web complète (login, recherche, historique, profil). Utilisable en démonstration ou pour des équipes qui n'ont pas encore de GED — l'entreprise peut l'évaluer telle quelle.

### Mode C — Intégration profonde par API d'ingestion (roadmap, § 9)

Pour une intégration native, la GED poussera chaque document au moteur au moment de son versement (`POST /documents/{id}` + contenu), sans dossier partagé ni `POST /sync` global, avec l'identifiant GED comme clé stable du document. **Ce mode nécessite une évolution du moteur** (API d'ingestion + identifiants externes) décrite dans le plan d'action de l'audit. Il constitue l'objectif d'intégration cible.

---

## 7. Exemple d'intégration côté GED (pseudo-code)

```python
# --- Backend GED : appel au moteur de recherche ---
ENGINE = "http://moteur-ged.interne:8000"

def login():
    r = http.post(f"{ENGINE}/auth/login",
                  json={"email": SERVICE_ACCOUNT, "password": SERVICE_PASSWORD})
    r.raise_for_status()
    return r.json()["token"]          # à renouveler selon expires_at / 401

def search(query, top_k=5, category=None, file_type=None):
    body = {"query": query, "top_k": top_k}
    if category:  body["category"]  = category
    if file_type: body["file_type"] = file_type
    r = http.post(f"{ENGINE}/search", json=body,
                  headers={"Authorization": f"Bearer {token}"}, timeout=10)
    r.raise_for_status()
    return r.json()["results"]

# Côté interface GED : afficher file_name, text_preview (HTML-échappé),
# et relier chaque résultat à l'ouverture du document dans la GED.
```

---

## 8. Performances mesurées et montée en charge

**Mesures sur corpus de démonstration** (158 documents, 447 passages, 9 catégories, CPU seul) :

| Indicateur | Valeur |
|---|---|
| Latence d'une recherche | **21–27 ms** |
| Cache (requêtes identiques, 5 min) | réponse instantanée |
| Synchronisation incrémentale | proportionnelle aux seuls fichiers changés |
| Mémoire du service | ~1,1 Go (dont modèle sémantique) |

**Montée en charge estimée (mesures de simulation jointes à l'audit) :**

| Taille corpus | Latence attendue (l'état actuel) | Verdict |
|---|---|---|
| ≤ 10 000 documents | < 300 ms | ✅ utilisable en production |
| 50 000 documents | ~1 s | ⚠️ acceptable avec cache, à optimiser |
| 100 000 documents | 2–3 s | ❌ nécessite la phase d'optimisation (index inversé BM25) prévue au plan d'action |

L'audit (`AUDIT.md`) chiffre précisément ces limites et l'optimisation identifiée (mesurée en prototype : **partie lexicale ~100× plus rapide**, objectif < 50 ms/requête à 100 000 documents). L'indexation initiale d'un gros corpus est une opération de fond (OCR des scannés) : elle se planifie hors heures ouvrées et/ou en deux passes (texte natif d'abord, OCR en arrière-plan).

---

## 9. Plan d'intégration proposé

| Phase | Contenu | Résultat |
|---|---|---|
| **P1 — Pilote (aujourd'hui)** | Déploiement du moteur (§ 3), alimentation par export GED + `POST /sync` (Mode A), évaluation par les utilisateurs métier sur un périmètre réel (un service, une typologie documentaire) | Retour utilisateur + validation de la pertinence |
| **P2 — Optimisation 100k** | Phase 1-2 du plan d'action de l'audit (correction rechargement au démarrage, index inversé BM25, suppression des scans complets) | Moteur dimensionnable à 100 000+ documents |
| **P3 — Intégration native** | API d'ingestion push par identifiant GED, clé d'API service, versionnage `/v1`, filtres métadonnées (Mode C) | Le moteur devient un composant de la GED, sans dossier partagé |
| **P4 — Industrialisation** | Jeu de requêtes de test annotées (nDCG/MRR) pour piloter la qualité, supervision (les métriques sont déjà exposées), sauvegarde/restauration de l'index | Qualité mesurée et maîtrisée dans la durée |

---

## 10. Sécurité

- **Authentification obligatoire** sur la recherche et les documents ; mots de passe hachés (bcrypt) ; sessions révocables côté serveur.
- **Cookie httpOnly** (non lisible par JavaScript → limite le vol de session par XSS), options `Secure`/`SameSite` configurables pour HTTPS en production.
- **Protection path traversal** sur la route de téléchargement des fichiers.
- **Rate limiting** sur les endpoints sensibles (login, mots de passe).
- **CORS restreint** aux origines déclarées ; **journalisation** de chaque requête (méthode, chemin, statut, durée, utilisateur).
- Déploiement cible : réseau interne, HTTPS en frontal (reverse proxy), secrets uniquement dans `.env` (hors gestion de version).

## 11. Glossaire

| Terme | Définition simple |
|---|---|
| **Embedding / vectorisation** | représentation numérique du *sens* d'un texte (un vecteur de 384 nombres) ; deux textes de sens proche ont des vecteurs proches |
| **SBERT** | modèle de langage qui produit ces vecteurs (multilingue, fonctionne sur CPU) |
| **FAISS** | bibliothèque qui recherche les vecteurs les plus proches, très rapidement |
| **BM25** | algorithme lexical classique de recherche par mots-clés, pondéré par la rareté des termes |
| **RRF (Reciprocal Rank Fusion)** | méthode standard pour fusionner plusieurs classements (sémantique + lexical) en un seul |
| **OCR** | reconnaissance de caractères sur image — rend searchable un document scanné |
| **Passage (chunk)** | fragment de document (~900 caractères) servant d'unité de recherche |
| **RRF / seuil de pertinence** | score minimal en dessous duquel un résultat est jugé non pertinent et écarté |

---

*Documents joints : `AUDIT.md` (audit technique complet et plan d'action chiffré), `projet.md` (fiche descriptive du sujet), benchmarks reproductibles dans `backend/tests/`.*
