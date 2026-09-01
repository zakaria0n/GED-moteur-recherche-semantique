"""Creation de la base de donnees et du schema complet au demarrage."""

import re

from config import DB_NAME
from repositories.connection import get_connection, get_server_connection
from repositories.documents import initialize_schema as init_documents_schema
from repositories.users import initialize_schema as init_users_schema


# Identifiant SQL strict : lettres, chiffres, underscore (pas d'injection possible).
_DB_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")


def initialize_database():
    """Cree la base si absente puis toutes les tables du projet."""

    if not _DB_NAME_PATTERN.match(DB_NAME):
        raise ValueError(
            f"Nom de base de donnees invalide (caracteres non autorises) : {DB_NAME!r}"
        )

    server_conn = get_server_connection()
    server_cursor = server_conn.cursor()

    server_cursor.execute(
        f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )

    server_cursor.close()
    server_conn.close()

    with get_connection() as conn:
        cursor = conn.cursor()
        init_documents_schema(cursor)
        init_users_schema(cursor)
        conn.commit()
        cursor.close()
