"""Logique metier d'authentification : mots de passe, jetons, sessions, liens.

Ce module regroupe les primitives utilisees par le controller d'auth et par la
dependance d'authentification. Il ne fait aucune entree/sortie reseau directe :
l'envoi d'emails est delegue a l'adaptateur clients.email.
"""

import hashlib
import secrets
import bcrypt
from datetime import datetime, timedelta

from config import (
    EMAIL_VERIFICATION_HOURS,
    FRONTEND_BASE_URL,
    PASSWORD_RESET_HOURS,
    REMEMBER_ME_DAYS,
    SESSION_HOURS,
)


def validate_password(password):
    """Politique minimale de mot de passe."""
    if not password or len(password) < 8:
        raise ValueError("Le mot de passe doit contenir au moins 8 caracteres")

    if not any(character.isalpha() for character in password):
        raise ValueError("Le mot de passe doit contenir au moins une lettre")

    if not any(character.isdigit() for character in password):
        raise ValueError("Le mot de passe doit contenir au moins un chiffre")

    return True


def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password, stored_password):
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def generate_token():
    return secrets.token_urlsafe(32)


def hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_verification_expiration():
    return datetime.now() + timedelta(hours=EMAIL_VERIFICATION_HOURS)


def get_password_reset_expiration():
    return datetime.now() + timedelta(hours=PASSWORD_RESET_HOURS)


def get_session_expiration(remember_me=False):
    if remember_me:
        return datetime.now() + timedelta(days=REMEMBER_ME_DAYS)

    return datetime.now() + timedelta(hours=SESSION_HOURS)


def build_verification_link(token):
    return f"{FRONTEND_BASE_URL}/verify.html?token={token}"


def build_reset_link(token):
    return f"{FRONTEND_BASE_URL}/reset-password.html?token={token}"
