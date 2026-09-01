"""Dependance d'authentification (resolution du token de session).

Lit le cookie de session httpOnly en priorite, puis retombe sur le header
Bearer pour la compatibilite. Fait partie du pipeline transversal d'auth.
"""

from datetime import datetime

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import SESSION_COOKIE_NAME
from repositories.users import delete_session, get_session_with_user
from services.auth import hash_token

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
):
    # Cookie httpOnly en priorite (non lisible par le JS -> reduit le risque XSS),
    # fallback sur le header Bearer pour la compatibilite.
    raw_token = request.cookies.get(SESSION_COOKIE_NAME)

    if not raw_token and credentials is not None:
        raw_token = credentials.credentials

    if not raw_token:
        raise HTTPException(status_code=401, detail="Authentification requise")

    session = get_session_with_user(hash_token(raw_token))

    if not session:
        raise HTTPException(status_code=401, detail="Session introuvable")

    if session["expires_at"] < datetime.now():
        delete_session(hash_token(raw_token))
        raise HTTPException(status_code=401, detail="Session expiree")

    return {
        "id": session["user_id"],
        "full_name": session["full_name"],
        "email": session["email"],
        "password_hash": session["password_hash"],
        "is_email_verified": session["is_email_verified"],
        "created_at": session["created_at"],
        "updated_at": session["updated_at"],
        "raw_token": raw_token,
    }
