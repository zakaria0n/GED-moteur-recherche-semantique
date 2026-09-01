"""Operations DB sur la table documents."""

from repositories.connection import get_connection


def initialize_schema(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            id INT AUTO_INCREMENT PRIMARY KEY,
            path TEXT NOT NULL,
            relative_path VARCHAR(500) NOT NULL,
            file_name VARCHAR(255) NOT NULL,
            file_type VARCHAR(50) NOT NULL,
            modified_at VARCHAR(50) NOT NULL,
            content_hash VARCHAR(64) NOT NULL,
            extracted_text LONGTEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY unique_relative_path (relative_path)
        )
        """
    )


def upsert_documents(documents):
    """Insere ou met a jour les documents dans une seule transaction.

    Mise a jour ciblee (ON DUPLICATE KEY UPDATE sur unique_relative_path) :
    les fichiers non changes gardent leur ligne, seuls les ajoutes/modifies
    sont re-ecrits. Nettement plus rapide que un DELETE + INSERT global a
    chaque synchronisation, et la table n'est jamais videe (rollback sinon).
    """
    if not documents:
        return

    with get_connection() as conn:
        conn.autocommit = False
        cursor = conn.cursor()

        try:
            rows = [
                (
                    document["path"],
                    document["relative_path"],
                    document["file_name"],
                    document["file_type"],
                    document["modified_at"],
                    document["content_hash"],
                    document["text"],
                )
                for document in documents
            ]

            cursor.executemany(
                """
                INSERT INTO documents (
                    path,
                    relative_path,
                    file_name,
                    file_type,
                    modified_at,
                    content_hash,
                    extracted_text
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    path = VALUES(path),
                    file_name = VALUES(file_name),
                    file_type = VALUES(file_type),
                    modified_at = VALUES(modified_at),
                    content_hash = VALUES(content_hash),
                    extracted_text = VALUES(extracted_text)
                """,
                rows,
            )

            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()


def delete_documents_not_in(relative_paths):
    """Supprime les lignes dont le chemin n'est plus dans le corpus courant.

    Complement de upsert_documents pour refleter les fichiers supprimes du
    dossier sans vider la table.
    """
    if not relative_paths:
        return

    with get_connection() as conn:
        cursor = conn.cursor()
        placeholders = ",".join("%s" for _ in relative_paths)

        cursor.execute(
            f"DELETE FROM documents WHERE relative_path NOT IN ({placeholders})",
            tuple(relative_paths),
        )

        # Le connecteur demarre sans autocommit : sans commit explicite, le
        # DELETE est perdu (rollback implicite a la fermeture de la connexion).
        conn.commit()

        cursor.close()


def list_documents(limit=None, offset=0):
    with get_connection() as conn:
        cursor = conn.cursor(dictionary=True)

        if limit is None:
            cursor.execute(
                """
                SELECT
                    id,
                    path,
                    relative_path,
                    file_name,
                    file_type,
                    modified_at,
                    content_hash,
                    created_at,
                    updated_at
                FROM documents
                ORDER BY id ASC
                """
            )
        else:
            # Quand un limit est demande, on renvoie les plus recents (id DESC).
            cursor.execute(
                """
                SELECT
                    id,
                    path,
                    relative_path,
                    file_name,
                    file_type,
                    modified_at,
                    content_hash,
                    created_at,
                    updated_at
                FROM documents
                ORDER BY id DESC
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )

        documents = cursor.fetchall()
        cursor.close()

    return documents


def get_documents_with_text():
    """Tous les documents avec leur texte extrait (rechargement de l'index).

    L'ordre (id ASC) correspond a l'ordre d'insertion en base, donc a l'ordre
    des vecteurs dans l'index FAISS sauvegarde.
    """
    with get_connection() as conn:
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT
                id,
                path,
                relative_path,
                file_name,
                file_type,
                modified_at,
                content_hash,
                extracted_text
            FROM documents
            ORDER BY id ASC
            """
        )

        rows = cursor.fetchall()
        cursor.close()

    return rows


def get_all_documents():
    """Tous les documents (avec ou sans texte) pour reconstruire le catalogue
    complet au rechargement, sans perdre les fichiers non indexables."""

    with get_connection() as conn:
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT
                id,
                path,
                relative_path,
                file_name,
                file_type,
                modified_at,
                content_hash,
                extracted_text
            FROM documents
            ORDER BY id ASC
            """
        )

        rows = cursor.fetchall()
        cursor.close()

    return rows


def get_indexed_documents_metadata():
    with get_connection() as conn:
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT relative_path, content_hash, modified_at
            FROM documents
            ORDER BY id ASC
            """
        )

        rows = cursor.fetchall()
        cursor.close()

    return rows


def count_documents():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM documents")
        count = cursor.fetchone()[0]
        cursor.close()

    return count
