"""Connexion a MariaDB/MySQL avec context manager et pool de connexions."""

import threading
from contextlib import contextmanager

import mysql.connector
from mysql.connector import pooling

from config import (
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_POOL_SIZE,
    DB_PORT,
    DB_USER,
)


_pool = None
_pool_lock = threading.Lock()


def _build_pool():
    """Cree le pool une seule fois (apres la creation de la base)."""

    global _pool

    if _pool is not None:
        return _pool

    with _pool_lock:
        if _pool is None:
            _pool = pooling.MySQLConnectionPool(
                pool_name="ged_pool",
                pool_size=DB_POOL_SIZE,
                pool_reset_session=True,
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME,
            )

    return _pool


@contextmanager
def get_connection():
    """Connexion du pool (context manager). La fermeture la rend au pool."""

    pool = _build_pool()
    connection = pool.get_connection()

    try:
        yield connection
    finally:
        connection.close()


def get_server_connection():
    """Connexion directe sans base (creation du schema). Hors pool car la base
    n'existe pas encore au premier lancement."""

    return mysql.connector.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
    )
