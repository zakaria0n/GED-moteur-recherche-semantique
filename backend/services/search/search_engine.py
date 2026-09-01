"""Orchestration du moteur de recherche semantique.

Recherche hybride : similarite dense (SBERT + FAISS) fusionnee par RRF avec un
score lexical BM25. Le classement final agrege les meilleurs passages par
document, et un seuil de similarite ecarte les faux positifs.
"""

import hashlib
import time
from collections import OrderedDict, defaultdict
from pathlib import Path
import re

import numpy as np

from config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    OCR_ENABLED,
    PDFS_DIR,
    RELEVANCE_THRESHOLD,
    RRF_K,
)
from services.search.bm25 import BM25, tokenize
from services.search.embedder import (
    DEFAULT_MODEL_NAME,
    embed_query,
    embed_texts,
    load_embedding_model,
)
from services.search.text_extractor import (
    count_embedded_images,
    extract_text_from_excel,
    extract_text_from_gif,
    extract_text_from_image,
    extract_text_from_pdf,
    extract_text_from_powerpoint,
    extract_text_from_word,
    extract_text_with_ocr,
    has_raster_images,
    looks_garbled,
    merge_text_layers,
    ocr_images_parallel,
    ocr_pdf_images_only,
    ocr_pdf_pages,
    ocr_pdf_pages_parallel,
)
from services.search.vector_index import create_faiss_index, search_in_index


# ---------------------------------------------------------------------------
# Cache LRU des recherches
# ---------------------------------------------------------------------------
# Stocke les N dernieres requetes avec TTL. Les entrees expirees sont ignorees
# lors des hits. Hit/miss rate affiche dans les logs pour monitoring.
_SEARCH_CACHE_TTL = 300  # 5 minutes
_SEARCH_CACHE_MAX = 128  # nombre max d'entrees


class SearchCache:
    """Cache LRU avec TTL pour les resultats de recherche."""

    def __init__(self, max_size=_SEARCH_CACHE_MAX, ttl=_SEARCH_CACHE_TTL):
        self._cache: OrderedDict = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _make_key(query, top_k, category, file_type):
        raw = f"{query.strip().lower()}|{top_k}|{category or ''}|{file_type or ''}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def get(self, query, top_k, category, file_type):
        key = self._make_key(query, top_k, category, file_type)
        entry = self._cache.get(key)
        if entry is None:
            self._misses += 1
            return None
        if time.time() - entry["ts"] >= self._ttl:
            del self._cache[key]
            self._misses += 1
            return None
        # Remonter en fin d'ordre (MRU).
        self._cache.move_to_end(key)
        self._hits += 1
        return entry["results"]

    def put(self, query, top_k, category, file_type, results):
        key = self._make_key(query, top_k, category, file_type)
        if key in self._cache:
            del self._cache[key]
        elif len(self._cache) >= self._max_size:
            self._cache.popitem(last=False)
        self._cache[key] = {"results": results, "ts": time.time()}

    def stats(self):
        total = self._hits + self._misses
        rate = (self._hits / total * 100) if total else 0
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_pct": round(rate, 1),
            "size": len(self._cache),
            "max_size": self._max_size,
        }

    def clear(self):
        self._cache.clear()
        self._hits = 0
        self._misses = 0


_search_cache = SearchCache()


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"}
WORD_EXTENSIONS = {".docx"}
POWERPOINT_EXTENSIONS = {".pptx"}
EXCEL_EXTENSIONS = {".xlsx"}
SUPPORTED_EXTENSIONS = {".pdf", ".gif"} | IMAGE_EXTENSIONS | WORD_EXTENSIONS | POWERPOINT_EXTENSIONS | EXCEL_EXTENSIONS


def category_of(relative_path):
    """Renvoie la categorie (dossier top-level) d'un chemin relatif."""

    normalized = relative_path.replace("\\", "/")
    parts = normalized.split("/")
    return parts[0] if len(parts) > 1 else "_root"


def chunk_text(text: str) -> list[str]:
    """Decoupe un texte en passages d'environ CHUNK_SIZE caracteres."""

    text = text.strip()

    if len(text) <= CHUNK_SIZE:
        return [text] if text else []

    chunks = []
    start = 0

    while start < len(text):
        end = min(len(text), start + CHUNK_SIZE)

        # Couper de preference sur une fin de ligne pour ne pas hacher les mots.
        if end < len(text):
            newline = text.rfind("\n", end - (CHUNK_SIZE - CHUNK_OVERLAP), end)

            if newline > start:
                end = newline

        passage = text[start:end].strip()

        if passage:
            chunks.append(passage)

        if end >= len(text):
            break

        start = max(end - CHUNK_OVERLAP, start + 1)

    return chunks


def build_chunks(documents: list[dict]) -> list[dict]:
    """Associe chaque document a ses passages (alignes sur les vecteurs FAISS).

    Renvoie une liste [{document, text}] : l'index dans cette liste correspond
    a la position du vecteur dans FAISS.
    """

    chunks = []

    for document in documents:
        for passage in chunk_text(document["text"]):
            chunks.append({"document": document, "text": passage})

    return chunks


def is_supported_document(file_path: str | Path) -> bool:
    path = Path(file_path)
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def get_file_hash(file_path: str | Path) -> str:
    path = Path(file_path)
    hasher = hashlib.sha256()

    with path.open("rb") as file:
        while True:
            chunk = file.read(8192)

            if not chunk:
                break

            hasher.update(chunk)

    return hasher.hexdigest()


def build_document_metadata(file_path: str | Path, documents_dir: str | Path) -> dict:
    path = Path(file_path)
    stats = path.stat()

    return {
        "path": str(path),
        "relative_path": str(path.relative_to(documents_dir)),
        "file_name": path.name,
        "file_type": path.suffix.lower(),
        "modified_at": str(int(stats.st_mtime)),
        "content_hash": get_file_hash(path),
    }


def scan_documents_metadata(documents_dir=PDFS_DIR, compute_hash=True):
    """Liste les metadonnees des fichiers supportes.

    compute_hash=False fait un scan leger (mtime/taille, sans lire le
    contenu) utilise pour detecter rapidement les changements au demarrage.
    """

    documents_dir = Path(documents_dir)
    documents = []

    for path in sorted(documents_dir.rglob("*")):
        if not path.is_file():
            continue

        if not is_supported_document(path):
            continue

        if compute_hash:
            documents.append(build_document_metadata(path, documents_dir))
        else:
            stats = path.stat()
            documents.append(
                {
                    "relative_path": str(path.relative_to(documents_dir)),
                    "file_name": path.name,
                    "file_type": path.suffix.lower(),
                    "modified_at": str(int(stats.st_mtime)),
                    "size": stats.st_size,
                    "content_hash": None,
                }
            )

    return documents


def extract_text_from_document(file_path, use_ocr_for_pdf=True):
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        text = extract_text_from_pdf(path)

        # OCR conditionnel : 3 cas decides en < 50 ms.
        #
        # Cas A — PDF vectoriel pur (texte extractible, pas d'images raster) :
        #   SKIP OCR. Le texte est deja la, pas d'images a OCRiser.
        #   → 0 ms (vs ~2 min avant).
        #
        # Cas B — PDF mixte (texte + images raster) :
        #   Pass 1 uniquement (OCR des images raster dedupliees).
        #   → ~2 s (vs ~2 min avant).
        #
        # Cas C — PDF scanne (pas de texte extractible) :
        #   Pass 1 + Pass 2 (OCR complet parallele).
        #   → ~2 min (necessaire).
        if use_ocr_for_pdf:
            # OCR conditionnel : on evite l'OCR inutile pour les PDFs
            # qui ont deja du texte extractible et pas d'images raster.
            #
            # Filtre rapide (< 50 ms) : detecte les images raster > 200x200 px.
            pdf_has_images = has_raster_images(path)

            if not text or looks_garbled(text):
                # Cas C : texte absent ou illisible → OCR complet necessaire.
                # (PDFs scannés : les pages entières sont en raster mais
                # get_images() ne les voit pas → on OCR quand meme.)
                image_text = ""
                try:
                    image_text = ocr_pdf_images_only(path)
                except Exception:
                    pass

                try:
                    full_ocr = ocr_pdf_pages_parallel(path)
                except Exception:
                    full_ocr = ""

                if full_ocr:
                    image_text = full_ocr

                if image_text:
                    merged = merge_text_layers(text, image_text)
                    if merged != text:
                        print(f"[INDEX] OCR complet pour: {path.name} (+{len(merged) - len(text)} chars)")
                    return merged

                return text

            if pdf_has_images:
                # Cas B : texte present + images raster → Pass 1 uniquement.
                # Le texte extractible est garde, on ajoute le texte des images
                # (logos, cachets, signatures).
                try:
                    image_text = ocr_pdf_images_only(path)
                except Exception:
                    image_text = ""

                if image_text:
                    merged = merge_text_layers(text, image_text)
                    if merged != text:
                        print(f"[INDEX] OCR images pour: {path.name} (+{len(merged) - len(text)} chars)")
                    return merged

            # Cas A : texte present, pas d'images raster → SKIP OCR.
            return text

        # Pas d'OCR : on renvoie le texte extractible tel quel.
        return text

    if suffix in WORD_EXTENSIONS:
        return extract_text_from_word(path)

    if suffix in POWERPOINT_EXTENSIONS:
        return extract_text_from_powerpoint(path)

    if suffix in EXCEL_EXTENSIONS:
        return extract_text_from_excel(path)

    if suffix in IMAGE_EXTENSIONS:
        return extract_text_from_image(path)

    if suffix == ".gif":
        return extract_text_from_gif(path)

    raise ValueError(f"Type de fichier non supporte : {suffix}")


def _build_shard(documents, model, chunks=None, vectors=None):
    """Construit un shard : index FAISS + passages + vecteurs pour une categorie.

    chunks/vectors permettent de reutiliser des passages et vecteurs deja
    calcules (sync incrementale) : seuls les fichiers nouveaux ou modifies
    sont alors embeddes, pas tout le shard.
    Le BM25 est global (construit a partir de tous les shards) pour preserver
    le classement hybride dense+lexical identique a un index unique.
    """

    if chunks is None:
        chunks = build_chunks(documents)

    if vectors is None:
        vectors = embed_texts([chunk["text"] for chunk in chunks], model)

    index = create_faiss_index(vectors)

    return {
        "documents": documents,
        "chunks": chunks,
        "chunk_vectors": [np.asarray(vector, dtype="float32") for vector in vectors],
        "index": index,
    }


def _build_shards(documents, model):
    """Regroupe les documents par categorie et construit un shard par categorie.

    Renvoie (shards, all_chunks, shard_chunk_start, bm25) :
      - shards : {cat: shard_dict} pour la recherche FAISS par categorie ;
      - all_chunks : liste plate de tous les passages (ordre = categories triees) ;
      - shard_chunk_start : {cat: index_de_debut} dans all_chunks ;
      - bm25 : BM25 global sur all_chunks (IDF fiable, classement hybride identique
        a un index unique ; c'est la cle pour que la recherche cross-shards
        reproduise exactement le comportement d'avant le sharding).
    """

    shards = {}
    all_chunks = []
    shard_chunk_start = {}
    by_category = defaultdict(list)

    for document in documents:
        by_category[category_of(document["relative_path"])].append(document)

    for category_name in sorted(by_category.keys()):
        category_documents = by_category[category_name]
        shard_chunk_start[category_name] = len(all_chunks)
        shard = _build_shard(category_documents, model)
        shards[category_name] = shard
        all_chunks.extend(shard["chunks"])

    bm25 = BM25([tokenize(chunk["text"]) for chunk in all_chunks])

    return shards, all_chunks, shard_chunk_start, bm25


def build_search_engine(documents_dir: str | Path = PDFS_DIR, model_name: str | None = None, model=None, use_ocr_for_pdf: bool = OCR_ENABLED) -> dict:
    """Construit le moteur a partir du dossier de documents.

    Renvoie un dictionnaire contenant le modele, l'index FAISS, le BM25, et
    les listes catalogue/documents/chunks (voir sync_service).
    """

    documents_dir = Path(documents_dir)

    if not documents_dir.exists():
        raise FileNotFoundError("Dossier de documents introuvable")

    print(f"[INDEX] Debut de l'indexation dans: {documents_dir}")
    print(f"[INDEX] OCR PDF active: {use_ocr_for_pdf}")

    if model is None:
        model = load_embedding_model(model_name) if model_name else load_embedding_model()

    catalog = []
    indexed_count = 0
    # Cache du texte extrait par hash de contenu : deux fichiers identiques
    # (doublons) ne sont extraits/OCR/embbeddes qu'une seule fois.
    extracted_by_hash = {}

    for path in sorted(documents_dir.rglob("*")):
        if not path.is_file():
            continue

        if not is_supported_document(path):
            continue

        print(f"[INDEX] Traitement du document: {path.name}")

        metadata = build_document_metadata(path, documents_dir)
        content_hash = metadata["content_hash"]

        if content_hash in extracted_by_hash:
            text = extracted_by_hash[content_hash]
        else:
            try:
                text = extract_text_from_document(path, use_ocr_for_pdf=use_ocr_for_pdf)
            except ValueError as exc:
                print(f"[INDEX] Extraction impossible ({exc}): {path.name}")
                text = ""

            extracted_by_hash[content_hash] = text or ""

        metadata["text"] = text or ""
        catalog.append(metadata)

        if text:
            indexed_count += 1
            print(f"[INDEX] Document indexe: {path.name} ({indexed_count})")
        else:
            print(f"[INDEX] Document sans texte exploitable: {path.name}")

    documents = [document for document in catalog if document["text"]]

    if not documents:
        raise ValueError("Aucun document exploitable n'a ete trouve")

    shards, all_chunks, shard_chunk_start, bm25 = _build_shards(documents, model)

    ignored_count = len(catalog) - len(documents)
    print(
        f"[INDEX] Fin de l'indexation: {len(documents)} documents indexes "
        f"({len(shards)} categories: {', '.join(sorted(shards.keys()))}), "
        f"{ignored_count} ignores (sans texte)."
    )

    return {
        "model": model,
        "catalog": catalog,
        "shards": shards,
        "categories": sorted(shards.keys()),
        "all_chunks": all_chunks,
        "shard_chunk_start": shard_chunk_start,
        "bm25": bm25,
    }


def _generate_suggestions(query, engine, top_k=3):
    """Genere des suggestions quand la recherche principale renvoie 0 resultat.

    Essaie chaque terme individuellement et retourne les meilleurs resultats
    en tant que suggestions pour aider l'utilisateur a affiner sa recherche.
    """
    terms = [term for term in re.split(r"\W+", query.lower()) if len(term) > 1]

    if not terms:
        return []

    # Essayer chaque terme individuellement, trier par score descendant.
    term_results = []
    for term in terms:
        try:
            results = search_documents(term, engine, top_k=1, category=None, file_type=None)
            if results:
                best = results[0]
                term_results.append({
                    "term": term,
                    "file_name": best["file_name"],
                    "relative_path": best["relative_path"],
                    "score": best["score"],
                })
        except Exception:
            continue

    # Aussi essayer des paires de termes si >= 2 termes.
    if len(terms) >= 2:
        for i in range(len(terms)):
            for j in range(i + 1, len(terms)):
                pair = f"{terms[i]} {terms[j]}"
                try:
                    results = search_documents(pair, engine, top_k=1, category=None, file_type=None)
                    if results:
                        best = results[0]
                        term_results.append({
                            "term": pair,
                            "file_name": best["file_name"],
                            "relative_path": best["relative_path"],
                            "score": best["score"],
                        })
                except Exception:
                    continue

    # Dedupliquer par terme et trier par score.
    seen = set()
    unique = []
    for item in sorted(term_results, key=lambda x: x["score"], reverse=True):
        if item["term"] not in seen:
            seen.add(item["term"])
            unique.append(item)

    return unique[:top_k]


def build_text_preview(text: str, query: str, max_length: int = 240) -> str:
    """Extrait un extrait centré sur le passage le plus pertinent."""

    if not text:
        return ""

    terms = [term for term in re.split(r"\W+", query.lower()) if len(term) > 1]

    if not terms:
        return text[:max_length]

    lower_text = text.lower()
    positions = [lower_text.find(term) for term in terms]
    positions = [position for position in positions if position != -1]

    if not positions:
        return text[:max_length]

    start = max(0, min(positions) - 90)
    end = min(len(text), start + max_length)

    snippet = text[start:end].strip()

    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""

    return f"{prefix}{snippet}{suffix}"


def search_documents(query: str, engine: dict, top_k: int = 5, threshold: float | None = None, category: str | None = None, file_type: str | None = None) -> list[dict]:
    """Recherche hybride (dense + BM25) avec agregation par document.

    - similarite dense via FAISS (cosinus) : recherche par shard (rapide) ;
    - score lexical BM25 global (IDF fiable sur tout le corpus) ;
    - fusion RRF des deux classements au niveau global ;
    - par document : moyenne de ses 3 meilleurs passages fusionnes ;
    - seuil de similarite cosinus (threshold) pour ecarter les faux positifs ;
    - cache LRU : requete identique = reponse instantanee (TTL 5 min) ;
    - filtre file_type :applique apres le classement (ex: ".pdf").

    Sharded : si category est specifiee, seuls les shards de cette categorie sont
    interroges pour la partie dense ; le BM25 reste global. Sinon tous les shards.
    Le classement final est identique a un index unique grace au BM25 global.
    """

    # --- Cache LRU ---
    cached = _search_cache.get(query, top_k, category, file_type)
    if cached is not None:
        return cached

    if threshold is None:
        threshold = RELEVANCE_THRESHOLD

    all_chunks = engine.get("all_chunks", [])
    number_of_chunks = len(all_chunks)

    if number_of_chunks == 0:
        return []

    model = engine["model"]
    bm25 = engine.get("bm25")
    query_vector = embed_query(query, model)

    fetch_k = min(number_of_chunks, max(top_k * 4, 40))

    # --- Dense retrieval : par shard, on projette les indices locaux vers le
    # index global (all_chunks) grace a shard_chunk_start. ---
    dense_cosine = {}
    dense_rank = {}
    shard_chunk_start = engine.get("shard_chunk_start", {})

    shards = engine.get("shards", {})
    target_cats = [category] if category else list(shards.keys())

    for cat in target_cats:
        shard = shards.get(cat)
        if shard is None:
            continue

        start = shard_chunk_start.get(cat, 0)
        shard_chunks_count = len(shard["chunks"])

        if shard_chunks_count == 0:
            continue

        local_fetch = min(shard_chunks_count, max(top_k * 4, 40))
        local_positions, local_scores = search_in_index(shard["index"], query_vector, top_k=local_fetch)

        for local_pos, local_score in zip(local_positions, local_scores):
            if local_pos == -1:
                continue

            global_idx = start + local_pos
            dense_cosine[global_idx] = float(local_score)

        # Rang global : on collecte tous les scores et on re-classe pour
        # obtenir le rang dense reel parmi les chunks recuperes.
    # Re-classement dense global (parmi les chunks recoltes de tous les shards cibles).
    sorted_global = sorted(dense_cosine.keys(), key=lambda i: dense_cosine[i], reverse=True)
    for rank, idx in enumerate(sorted_global):
        dense_rank[idx] = rank + 1

    # --- BM25 global : meme IDF que l'ancien index unique. ---
    bm25_rank = {}
    bm25_scores = None
    lexical_ref = 0.0

    if bm25 is not None:
        query_token_list = tokenize(query)
        bm25_scores = bm25.get_scores(query_token_list)
        bm25_order = sorted(range(number_of_chunks), key=lambda i: bm25_scores[i], reverse=True)[:fetch_k]
        bm25_rank = {i: rank + 1 for rank, i in enumerate(bm25_order)}

        # Reference de normalisation lexicale : le MEILLEUR score BM25 observe
        # pour cette requete. Le maximum theorique (somme des idf x (k1+1),
        # atteint seulement si chaque terme est repete a l'infini dans un meme
        # passage) est inatteignable en pratique et ecrasait artificiellement
        # le signal lexical (pourcentages affiches de 5 a 10 % pour des
        # correspondances exactes). Normalisation par l'observe = le meilleur
        # match lexical de la requete vaut 1.0.
        observed_max = max(bm25_scores) if bm25_scores else 0.0
        lexical_ref = observed_max

    # --- Fusion RRF globale (identique a l'ancien index combine). ---
    # Boost lexical : les chunks contenant le terme exact de la requete
    # recoivent un multiplicateur pour contrer la penalite des documents
    # longs (type contrat complet avec un seul mot-cle pertinent).
    query_lower = query.lower()
    query_terms = [term for term in re.split(r"\W+", query_lower) if len(term) > 1]
    exact_boost = 2.0

    fused = {}

    for i in range(number_of_chunks):
        value = 0.0

        if i in dense_rank:
            value += 1.0 / (RRF_K + dense_rank[i])

        if i in bm25_rank:
            value += 1.0 / (RRF_K + bm25_rank[i])

        # Boost si la requete complete (ou tous les termes) apparait
        # litteralement dans le texte du chunk.
        if value > 0:
            chunk_text_lower = all_chunks[i]["text"].lower()
            has_exact = query_lower in chunk_text_lower or all(
                term in chunk_text_lower for term in query_terms
            )
            if has_exact:
                value *= exact_boost

            fused[i] = value

    # --- Injection des chunks exacts absents de fused. ---
    # Certains chunks contenant le terme exact peuvent ne pas apparaitre
    # dans les top-k dense OU BM25 (document long ou mot-cle rare).
    # On les injecte avec un score minimal garanti pour qu'ils puissent
    # contribuer au score agrégé du document.
    injection_score = 1.0 / (RRF_K + fetch_k) * exact_boost

    for i in range(number_of_chunks):
        if i in fused:
            continue

        chunk_lower = all_chunks[i]["text"].lower()
        has_exact = query_lower in chunk_lower or (
            query_terms and all(term in chunk_lower for term in query_terms)
        )
        if has_exact:
            fused[i] = injection_score

    # Agrege les passages par document (moyenne des 3 meilleurs fusionnes).
    # Pour chaque passage on garde : score fusionne, index, cosinus dense,
    # score BM25 normalise (0-1) par le maximum theorique de la requete.
    document_items = defaultdict(list)

    for i, value in fused.items():
        relative_path = all_chunks[i]["document"]["relative_path"]
        lexical_norm = (bm25_scores[i] / lexical_ref) if lexical_ref > 0 else 0.0
        document_items[relative_path].append((value, i, dense_cosine.get(i, 0.0), lexical_norm))

    # --- Boost document : detection du terme exact au niveau document. ---
    # Un document contenant le terme exact de la requete recoit un bonus
    # pour contrer la penalite des documents longs (contrat complet avec
    # un seul mot-cle pertinent noye dans le bruit).
    document_has_exact = {}

    for relative_path, items in document_items.items():
        has_exact = False
        for _, idx, _, _ in items:
            chunk_lower = all_chunks[idx]["text"].lower()
            if query_lower in chunk_lower or all(term in chunk_lower for term in query_terms):
                has_exact = True
                break
        document_has_exact[relative_path] = has_exact

    ranked_documents = []

    for relative_path, items in document_items.items():
        items.sort(key=lambda entry: entry[0], reverse=True)
        top_items = items[:3]

        # Si le document contient le terme exact, s'assurer qu'au moins
        # un chunk exact est dans l'ensemble agrégé (sinon le boost ne
        # s'applique pas et le document est pénalisé).
        if document_has_exact.get(relative_path):
            has_exact_in_top3 = False
            for _, idx, _, _ in top_items:
                chunk_lower = all_chunks[idx]["text"].lower()
                if query_lower in chunk_lower or all(
                    term in chunk_lower for term in query_terms
                ):
                    has_exact_in_top3 = True
                    break
            if not has_exact_in_top3:
                # Trouver le meilleur chunk exact du document.
                best_exact = max(
                    (entry for entry in items if all_chunks[entry[1]]["text"].lower().find(query_lower) != -1),
                    key=lambda e: e[0],
                    default=None,
                )
                if best_exact is not None:
                    top_items = list(top_items) + [best_exact]

        aggregated = sum(entry[0] for entry in top_items) / len(top_items)
        best_cosine = max(entry[2] for entry in top_items)
        best_lexical = max(entry[3] for entry in top_items)

        # Pourcentage de pertinence affiche, a partir de deux signaux :
        #   - cosinus SBERT du meilleur passage, CALIBRE sur la plage utile
        #     du modele : en pratique 0.1 = aucun lien, 0.75 = quasi
        #     paraphrase (le cosinus brut ne depasse presque jamais 0.75,
        #     meme pour deux textes quasi identiques — l'afficher x100
        #     sous-noterait les correspondances, ex : cos 0.63 = 63 %) ;
        #   - score BM25 du meilleur passage, normalise par le meilleur
        #     score observe de la requete (le meilleur match lexical = 100 %).
        # Les deux signaux sont moyennes a parts egales.
        cosine_signal = min(1.0, max(0.0, (best_cosine - 0.1) / 0.65))

        signals = [cosine_signal]

        if lexical_ref > 0:
            signals.append(min(1.0, max(0.0, best_lexical)))

        relevance_pct = round(100.0 * sum(signals) / len(signals), 1)

        # Correspondance exacte = plancher de 90 % : un document qui contient
        # litteralement les termes de la requete est une reponse directe,
        # quel que soit le cosinus du modele sur ce passage.
        if document_has_exact.get(relative_path):
            relevance_pct = max(relevance_pct, 90.0)

        # Boost x3 si le document contient le terme exact (classement).
        if document_has_exact.get(relative_path):
            aggregated *= 3.0

        representative = all_chunks[top_items[0][1]]
        # La pertinence est portee PAR DOCUMENT dans le tuple : sans cela la
        # variable d'iteration fuirait dans la boucle de construction des
        # resultats (tous les resultats heriteraient de la pertinence du
        # dernier document agrege).
        ranked_documents.append((aggregated, best_cosine, representative, relevance_pct))

    ranked_documents.sort(key=lambda entry: entry[0], reverse=True)

    results = []

    for aggregated, best_cosine, chunk, relevance_pct in ranked_documents:
        document = chunk["document"]
        relative_path = document["relative_path"]

        # Appliquer le seuil de similarite, sauf pour les documents
        # contenant le terme exact (match lexical garanti).
        if not document_has_exact.get(relative_path) and best_cosine < threshold:
            continue

        # Filtre par type de fichier (applique apres le classement, pas sur le scoring).
        if file_type and document["file_type"] != file_type:
            continue

        # Filtre par categorie (post-agregation) : les resultats BM25/injection
        # globale peuvent inclure des documents hors categorie cible.
        if category:
            doc_cat = relative_path.replace("\\", "/").split("/")[0] if "/" in relative_path.replace("\\", "/") else "_root"
            if doc_cat != category:
                continue

        results.append(
            {
                "path": document["path"],
                "relative_path": document["relative_path"],
                "file_name": document["file_name"],
                "file_type": document["file_type"],
                "score": best_cosine,
                "aggregated": aggregated,
                "relevance": relevance_pct,
                "text_preview": build_text_preview(chunk["text"], query),
            }
        )

        if len(results) >= top_k:
            break

    # Stocker dans le cache LRU.
    _search_cache.put(query, top_k, category, file_type, results)

    return results
