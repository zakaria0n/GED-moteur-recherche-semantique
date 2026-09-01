"""Synchronisation documents <-> index FAISS <-> base de donnees.

Contient toute la logique metier de detection des changements et de
(re)construction de l'index, executee au demarrage ou via /sync.

Sharding : chaque categorie (dossier top-level) a son propre index FAISS.
La mise a jour est INCREMENTALE : seuls les shards modifies sont reconstruits.
Les vecteurs deja calcules sont caches en memoire (shard["chunk_vectors"]) et
reutilises, ce qui evite de re-embedder tout le corpus.
"""

import threading
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from config import INDEX_DIR, OCR_ENABLED, PDFS_DIR
from shared import logger
from shared.metrics import record_sync, set_documents_indexed
from repositories.documents import (
    delete_documents_not_in,
    get_all_documents,
    get_indexed_documents_metadata,
    upsert_documents,
)
from services.search.bm25 import BM25, tokenize
from services.search.embedder import DEFAULT_MODEL_NAME, load_embedding_model
from services.search.vector_index import (
    delete_shard_files,
    load_shard_index,
    load_shards_manifest,
    save_shard_index,
    save_shards_manifest,
    search_in_index,
)
from services.search.search_engine import (
    _build_shard,
    _search_cache,
    build_chunks,
    build_document_metadata,
    build_search_engine,
    category_of,
    embed_texts,
    extract_text_from_document,
    get_file_hash,
    scan_documents_metadata,
)
from services.state import search_state, search_state_lock


def _save_engine_shards(engine, model_name=DEFAULT_MODEL_NAME):
    """Sauvegarde tous les shards de l'engine (index + manifest)."""

    for category, shard in engine["shards"].items():
        save_shard_index(
            shard["index"],
            INDEX_DIR,
            category,
            [chunk["document"]["relative_path"] for chunk in shard["chunks"]],
            model_name,
        )

    save_shards_manifest(INDEX_DIR, model_name, engine["categories"])


def _total_documents(engine):
    return sum(len(shard["documents"]) for shard in engine["shards"].values())


def _total_chunks(engine):
    return sum(len(shard["chunks"]) for shard in engine["shards"].values())


def _assemble_engine(model, catalog, shards):
    """Construit le dict engine complet a partir des shards.

    Les shards ne contiennent PAS de bm25 (c'est un index global).
    Cette fonction construit la liste plate all_chunks, le mapping
    shard_chunk_start, et le BM25 global — identique a build_search_engine.
    """

    all_chunks = []
    shard_chunk_start = {}

    for category_name in sorted(shards.keys()):
        shard_chunk_start[category_name] = len(all_chunks)
        all_chunks.extend(shards[category_name]["chunks"])

    bm25 = BM25([tokenize(chunk["text"]) for chunk in all_chunks]) if all_chunks else None

    return {
        "model": model,
        "catalog": catalog,
        "shards": shards,
        "categories": sorted(shards.keys()),
        "all_chunks": all_chunks,
        "shard_chunk_start": shard_chunk_start,
        "bm25": bm25,
    }


def build_and_store_engine(model=None, use_ocr_for_pdf=OCR_ENABLED):
    start = time.perf_counter()

    engine = build_search_engine(
        documents_dir=PDFS_DIR,
        model=model,
        use_ocr_for_pdf=use_ocr_for_pdf,
    )

    # Sauvegarde les shards (index FAISS par categorie + manifeste).
    _save_engine_shards(engine)

    upsert_documents(engine["catalog"])
    delete_documents_not_in([document["relative_path"] for document in engine["catalog"]])

    ignored_count = len(engine["catalog"]) - sum(
        len(shard["documents"]) for shard in engine["shards"].values()
    )

    if ignored_count:
        logger.warning(
            "sync",
            f"{ignored_count} fichier(s) supporte(s) sans texte exploitable "
            "(non indexes dans FAISS).",
        )

    with search_state_lock:
        search_state["engine"] = engine

    duration_ms = (time.perf_counter() - start) * 1000
    total = _total_documents(engine)
    set_documents_indexed(total)
    record_sync("complete", total, duration_ms)

    return engine


def _rebuild_shard_incremental(shard, removed_paths, changed_entries, model, catalog_by_path):
    """Reconstruit un shard en retirant les fichiers retires et en ajoutant les nouveaux.

    Les vecteurs des fichiers non modifies sont conserves (pas de re-embed).
    """

    chunks = shard["chunks"]
    vectors = shard.get("chunk_vectors") or []
    documents = shard["documents"]

    # 1. Retrait des passages/vecteurs/documents retires.
    kept_chunks = []
    kept_vectors = []

    for chunk, vector in zip(chunks, vectors):
        if chunk["document"]["relative_path"] in removed_paths:
            continue
        kept_chunks.append(chunk)
        kept_vectors.append(vector)

    kept_documents = [d for d in documents if d["relative_path"] not in removed_paths]

    # 2. Extraction + embedding UNIQUEMENT des fichiers ajoutes/modifies (pas encore dans le shard).
    new_chunks = []
    new_vectors = []

    for relative_path, metadata in changed_entries.items():
        if metadata["text"]:
            doc_chunks = build_chunks([metadata])
            doc_vectors = embed_texts([chunk["text"] for chunk in doc_chunks], model)

            for chunk, vector in zip(doc_chunks, doc_vectors):
                new_chunks.append(chunk)
                new_vectors.append(np.asarray(vector, dtype="float32"))

            kept_documents.append(metadata)

    all_chunks = kept_chunks + new_chunks
    all_vectors = kept_vectors + new_vectors

    if not all_chunks:
        return None

    # 3. Reconstruction de l'index FAISS en reutilisant les vecteurs conserves
    # (pas de re-embed des fichiers inchanges du shard). La liste des documents
    # du shard reste unique (un entree par fichier, pas par passage).
    new_shard = _build_shard(kept_documents, model, chunks=all_chunks, vectors=all_vectors)

    return new_shard


def apply_incremental_sync(changes, model):
    """Met a jour les shards modifies sans re-traiter tout le corpus.

    - seuls les shards contenant des fichiers ajoutes/modifies/supprimes sont
      reconstruits ; les shards inchanges sont conserves tels quels ;
    - le moteur est reconstitue dans un dict NEUF puis swap atomiquement sous
      verrou (une recherche concurrente ne voit jamais un etat a moitie mis a jour).
    """

    engine = search_state["engine"]

    if engine is None:
        return build_and_store_engine(model=model)

    added = changes.get("added", [])
    updated = changes.get("updated", [])
    deleted = changes.get("deleted", [])

    removed_paths = set(deleted) | set(updated)
    changed_paths = sorted(set(added) | set(updated))

    # Extraction + metadonnees des fichiers ajoutes/modifies.
    changed_entries = {}
    catalog = list(engine["catalog"])
    catalog_by_path = {d["relative_path"]: d for d in catalog}

    for relative_path in changed_paths:
        file_path = Path(PDFS_DIR) / relative_path

        try:
            text = extract_text_from_document(file_path, use_ocr_for_pdf=OCR_ENABLED)
        except ValueError as exc:
            logger.warning("sync", f"Extraction impossible ({exc}): {relative_path}")
            text = ""

        metadata = build_document_metadata(file_path, PDFS_DIR)
        metadata["text"] = text or ""
        changed_entries[relative_path] = metadata
        catalog_by_path[relative_path] = metadata

    # Suppressions du catalogue.
    for path in deleted:
        catalog_by_path.pop(path, None)

    catalog = list(catalog_by_path.values())

    # Regroupe les changements par categorie (shard a reconstruire).
    changed_categories = set(category_of(p) for p in removed_paths | set(changed_paths))

    new_shards = {}

    for cat, shard in engine["shards"].items():
        if cat not in changed_categories:
            new_shards[cat] = shard
            continue

        cat_removed = {p for p in removed_paths if category_of(p) == cat}
        cat_changed = {p: changed_entries[p] for p in changed_paths if category_of(p) == cat and p in changed_entries}

        new_shard = _rebuild_shard_incremental(shard, cat_removed, cat_changed, model, catalog_by_path)

        if new_shard is not None:
            new_shards[cat] = new_shard

            save_shard_index(
                new_shard["index"],
                INDEX_DIR,
                cat,
                [chunk["document"]["relative_path"] for chunk in new_shard["chunks"]],
                DEFAULT_MODEL_NAME,
            )
        else:
            delete_shard_files(INDEX_DIR, cat)

    # Nouvelles categories (fichiers ajoutes dans un dossier non encore indexe).
    for cat in changed_categories:
        if cat in new_shards:
            continue

        cat_documents = [
            catalog_by_path[p]
            for p in changed_paths
            if category_of(p) == cat and p in changed_entries and changed_entries[p]["text"]
        ]

        if cat_documents:
            new_shards[cat] = _build_shard(cat_documents, model)

            save_shard_index(
                new_shards[cat]["index"],
                INDEX_DIR,
                cat,
                [chunk["document"]["relative_path"] for chunk in new_shards[cat]["chunks"]],
                DEFAULT_MODEL_NAME,
            )

    new_engine = _assemble_engine(engine["model"], catalog, new_shards)

    save_shards_manifest(INDEX_DIR, DEFAULT_MODEL_NAME, new_engine["categories"])

    # Invalider le cache des recherches : les resultats precedents ne
    # reflètent plus le nouvel index.
    _search_cache.clear()

    logger.info(
        "sync",
        f"Fichiers re-indexes/re-embeddes: {len(changed_paths)} "
        f"(ajoutes: {len(added)}, modifies: {len(updated)}, supprimes: {len(deleted)}). "
        f"Index final: {_total_documents(new_engine)} documents, "
        f"{len(new_engine['categories'])} categories.",
    )

    upsert_documents(catalog)
    delete_documents_not_in([document["relative_path"] for document in catalog])

    with search_state_lock:
        search_state["engine"] = new_engine

    set_documents_indexed(_total_documents(new_engine))

    return new_engine


def detect_document_changes():
    """Compare le contenu actuel du dossier avec la base.

    Scan leger d'abord (mtime, sans lire le contenu) : seul un fichier dont la
    date a change est relu en entier pour recalculer son hash SHA-256. On
    evite ainsi de hasher tous les fichiers a chaque demarrage.
    """

    current_light = scan_documents_metadata(PDFS_DIR, compute_hash=False)
    indexed_documents = get_indexed_documents_metadata()
    indexed_map = {document["relative_path"]: document for document in indexed_documents}

    current_documents = []

    for metadata in current_light:
        indexed_document = indexed_map.get(metadata["relative_path"])

        if indexed_document and indexed_document["modified_at"] == metadata["modified_at"]:
            # mtime identique : contenu suppose identique, on reutilise le hash base.
            metadata["content_hash"] = indexed_document["content_hash"]
        else:
            # mtime change (ou nouveau) : on relit le fichier pour hasher.
            metadata["content_hash"] = get_file_hash(Path(PDFS_DIR) / metadata["relative_path"])

        current_documents.append(metadata)

    current_map = {document["relative_path"]: document for document in current_documents}

    added = []
    updated = []
    deleted = []

    for relative_path, document in current_map.items():
        indexed_document = indexed_map.get(relative_path)

        if indexed_document is None:
            added.append(relative_path)
            continue

        if document["content_hash"] != indexed_document["content_hash"]:
            updated.append(relative_path)

    for relative_path in indexed_map:
        if relative_path not in current_map:
            deleted.append(relative_path)

    return {
        "current_documents": current_documents,
        "added": added,
        "updated": updated,
        "deleted": deleted,
    }


def run_sync(model=None):
    start = time.perf_counter()

    try:
        if search_state["engine"] is None:
            logger.info("sync", "Aucun index en memoire. Construction complete en cours...")
            engine = build_and_store_engine(model=model)

            logger.success("sync", f"Index pret avec {_total_documents(engine)} documents.")

            return {
                "message": "Synchronisation terminee",
                "rebuild_performed": True,
                "documents_indexed": _total_documents(engine),
                "added": [],
                "updated": [],
                "deleted": [],
            }

        logger.info("sync", "Verification des changements en cours...")
        changes = detect_document_changes()

        rebuild_needed = bool(changes["added"] or changes["updated"] or changes["deleted"])

        logger.info(
            "sync",
            "Changements detectes - "
            f"ajoutes: {len(changes['added'])}, "
            f"modifies: {len(changes['updated'])}, "
            f"supprimes: {len(changes['deleted'])}",
        )

        if rebuild_needed:
            try:
                logger.info("sync", "Mise a jour incrementale de l'index...")
                engine = apply_incremental_sync(changes, model)
                indexed_documents = _total_documents(engine)
                logger.success(
                    "sync",
                    f"Index mis a jour (incrementale) avec {indexed_documents} documents.",
                )
            except Exception as exc:
                logger.error(
                    "sync",
                    f"Echec de la mise a jour incrementale, reconstruction complete: {exc}",
                )
                engine = build_and_store_engine(model=model)
                indexed_documents = _total_documents(engine)
                logger.success("sync", f"Index reconstruit avec {indexed_documents} documents.")
        else:
            logger.info("sync", "Aucun changement. Index conserve.")
            indexed_documents = _total_documents(search_state["engine"])

        duration_ms = (time.perf_counter() - start) * 1000
        record_sync("incrementale" if rebuild_needed else "sans_changement", indexed_documents, duration_ms)

        return {
            "message": "Synchronisation terminee",
            "rebuild_performed": rebuild_needed,
            "documents_indexed": indexed_documents,
            "added": changes["added"],
            "updated": changes["updated"],
            "deleted": changes["deleted"],
        }
    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        record_sync("erreur", 0, duration_ms, error=str(exc))
        raise


def build_engine_from_saved_state(model=None):
    """Recharge le moteur sharde depuis la derniere synchronisation.

    Charge le manifeste shards.json, puis pour chaque categorie : index FAISS
    + meta (chunk_relative_paths), documents depuis la base, reconstruction
    des vecteurs caches et du BM25. Renvoie None si la sauvegarde est
    absente ou desynchronisee ; dans ce cas run_sync reconstruira tout.
    """

    manifest = load_shards_manifest(INDEX_DIR)

    if manifest is None:
        logger.info("demarrage", "Manifeste shards.json absent, reconstruction necessaire.")
        return None

    try:
        rows = get_all_documents()
    except Exception as exc:
        logger.warning("demarrage", f"Lecture base impossible: {exc}")
        return None

    if not rows:
        logger.info("demarrage", "Sauvegarde vide, reconstruction necessaire.")
        return None

    # Catalogue complet (avec et sans texte) : preserve les fichiers non
    # indexables pour une detection stable des changements.
    catalog = [
        {
            "path": row["path"],
            "relative_path": row["relative_path"],
            "file_name": row["file_name"],
            "file_type": row["file_type"],
            "modified_at": row["modified_at"],
            "content_hash": row["content_hash"],
            "text": row["extracted_text"] or "",
        }
        for row in rows
    ]

    if model is None:
        model = load_embedding_model()

    row_by_path = {row["relative_path"]: row for row in rows}
    shards = {}

    for cat in manifest["categories"]:
        try:
            index, meta = load_shard_index(INDEX_DIR, cat)
        except Exception as exc:
            logger.info("demarrage", f"Shard '{cat}' inutilisable ({exc}), reconstruction.")
            return None

        if meta is None:
            logger.info("demarrage", f"Meta du shard '{cat}' absente, reconstruction.")
            return None

        relative_paths = meta.get("chunk_relative_paths", [])

        if len(relative_paths) != index.ntotal:
            logger.info(
                "demarrage",
                f"Shard '{cat}' desynchronise (index: {index.ntotal}, passages: {len(relative_paths)}).",
            )
            return None

        # La meta liste un chemin PAR PASSAGE : un document decoupe en plusieurs
        # passages y apparait donc plusieurs fois. On deduplique en conservant
        # l'ordre pour reconstruire la liste des documents uniques du shard.
        seen_paths = set()
        unique_paths = []

        for relative_path in relative_paths:
            if relative_path not in seen_paths:
                seen_paths.add(relative_path)
                unique_paths.append(relative_path)

        # Reconstruction des documents + chunks du shard a partir de la base.
        documents = []
        for rp in unique_paths:
            row = row_by_path.get(rp)
            if row is None:
                logger.info("demarrage", f"Document manquant en base pour {rp} (shard '{cat}'), reconstruction.")
                return None
            documents.append({
                "path": row["path"],
                "relative_path": row["relative_path"],
                "file_name": row["file_name"],
                "file_type": row["file_type"],
                "modified_at": row["modified_at"],
                "content_hash": row["content_hash"],
                "text": row["extracted_text"],
            })

        chunks = build_chunks(documents)

        # Alignement exact : re-decouper les documents uniques doit reproduire
        # la sequence passage -> document sauvegardee dans la meta (meme texte,
        # meme parametrage de decoupage). Sinon le shard est desynchronise.
        chunk_paths = [chunk["document"]["relative_path"] for chunk in chunks]

        if chunk_paths != relative_paths:
            logger.info(
                "demarrage",
                f"Shard '{cat}' desynchronise (index: {index.ntotal}, chunks: {len(chunks)}).",
            )
            return None

        # Reconstruction des vecteurs caches.
        try:
            cached_vectors = index.reconstruct_n(0, index.ntotal)
        except Exception:
            cached_vectors = np.array(
                [index.reconstruct(i) for i in range(index.ntotal)], dtype="float32"
            )

        chunk_vectors = [np.asarray(vec, dtype="float32") for vec in cached_vectors]

        shards[cat] = {
            "documents": documents,
            "chunks": chunks,
            "chunk_vectors": chunk_vectors,
            "index": index,
        }

    return _assemble_engine(model, catalog, shards)


def background_startup_sync_worker():
    search_state["sync_running"] = True
    search_state["last_sync_message"] = "Verification de l'index existant"

    try:
        logger.info("demarrage", "Chargement de l'index existant...")
        model = load_embedding_model()

        engine = build_engine_from_saved_state(model=model)

        if engine is not None:
            with search_state_lock:
                search_state["engine"] = engine
            logger.success(
                "demarrage",
                f"Index existant charge ({_total_documents(engine)} documents, "
                f"{len(engine['categories'])} categories).",
            )

        run_sync(model=model)

        if search_state["engine"]:
            search_state["last_sync_message"] = (
                f"Synchronisation terminee - "
                f"{_total_documents(search_state['engine'])} documents indexes"
            )
        else:
            search_state["last_sync_message"] = "Synchronisation terminee"
    except Exception as exc:
        search_state["last_sync_message"] = f"Erreur de synchronisation: {exc}"
        logger.error("demarrage", f"Erreur pendant la synchronisation initiale: {exc}")
    finally:
        search_state["sync_running"] = False


def start_background_startup_sync():
    if search_state["sync_running"]:
        return False

    thread = threading.Thread(
        target=background_startup_sync_worker,
        daemon=True,
    )
    thread.start()
    return True
