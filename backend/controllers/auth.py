"""Routes d'authentification et de gestion du compte utilisateur."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from shared import logger
from config import (
    COOKIE_SAMESITE,
    COOKIE_SECURE,
    REMEMBER_ME_DAYS,
    SESSION_COOKIE_NAME,
    SESSION_HOURS,
)
from services.auth import (
    build_reset_link,
    build_verification_link,
    generate_token,
    get_password_reset_expiration,
    get_session_expiration,
    get_verification_expiration,
    hash_password,
    hash_token,
    validate_password,
    verify_password,
)
from clients.email import send_email
from repositories.users import (
    create_user,
    create_user_session,
    delete_email_verification_tokens,
    delete_password_reset_tokens,
    delete_session,
    delete_user_account,
    delete_user_sessions,
    get_email_verification_token,
    get_password_reset_token,
    get_user_by_email,
    get_user_by_id,
    mark_user_email_verified,
    store_email_verification_token,
    store_password_reset_token,
    update_user_password,
    update_user_profile,
)
from config.ratelimit import limiter
from middleware.auth import get_current_user
from shared.serialization import normalize_email, serialize_user
from models.auth import (
    ChangePasswordRequest,
    DeleteAccountRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    UpdateProfileRequest,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
@limiter.limit("5/minute")
def register(request: Request, body: RegisterRequest):

    email = normalize_email(body.email)

    if get_user_by_email(email):
        logger.warning("auth", f"Tentative d'inscription avec un email deja utilise: {email}")
        raise HTTPException(status_code=400, detail="Inscription impossible. Verifiez vos informations.")

    try:
        validate_password(body.password)
    except ValueError as exc:
        logger.warning("auth", f"Mot de passe refuse pour {email}: {exc}")
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    password_hash = hash_password(body.password)
    user_id = create_user(body.full_name.strip(), email, password_hash)

    verification_token = generate_token()
    verification_token_hash = hash_token(verification_token)
    verification_expires_at = get_verification_expiration()

    store_email_verification_token(user_id, verification_token_hash, verification_expires_at)

    verification_link = build_verification_link(verification_token)
    email_sent = send_email(
        email,
        "Verification de votre compte",
        f"Bonjour {body.full_name},\n\nVerifiez votre email ici:\n{verification_link}",
    )

    logger.success("auth", f"Inscription de {body.full_name.strip()} ({email})")

    response = {"message": "Compte cree avec succes", "email_sent": email_sent}

    # Le jeton n'est expose dans la reponse que si l'email n'a pas pu partir
    # (developpement sans SMTP). Sinon, il ne transite que par l'email.
    if not email_sent:
        response["verification_link"] = verification_link
        response["verification_token"] = verification_token

    return response


@router.get("/verify-email")
def verify_email(token: str = Query(...)):

    token_row = get_email_verification_token(hash_token(token))

    if not token_row:
        logger.warning("auth", "Tentative de verification avec un token invalide")
        raise HTTPException(status_code=400, detail="Token de verification invalide")

    if token_row["expires_at"] < datetime.now():
        logger.warning("auth", "Tentative de verification avec un token expire")
        raise HTTPException(status_code=400, detail="Token de verification expire")

    mark_user_email_verified(token_row["user_id"])
    delete_email_verification_tokens(token_row["user_id"])

    user = get_user_by_id(token_row["user_id"])
    logger.success("auth", "Email verifie avec succes", user=user)

    return {"message": "Email verifie avec succes"}


@router.post("/login")
@limiter.limit("5/minute")
def login(request: Request, response: Response, body: LoginRequest):

    email = normalize_email(body.email)

    user = get_user_by_email(email)

    if not user or not verify_password(body.password, user["password_hash"]):
        logger.warning("auth", f"Echec de connexion pour {email}: email ou mot de passe incorrect")
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")

    if not user["is_email_verified"]:
        logger.warning("auth", f"Connexion refusee pour {email}: email non verifie")
        raise HTTPException(status_code=403, detail="Email non verifie")

    session_token = generate_token()
    session_token_hash = hash_token(session_token)
    expires_at = get_session_expiration(remember_me=body.remember_me)

    create_user_session(user["id"], session_token_hash, body.remember_me, expires_at)

    # Cookie httpOnly : non lisible par le JS, transmis automatiquement par le
    # navigateur. SameSite vient de la config (lax en dev local, none en prod
    # cross-sous-domaine avec COOKIE_SECURE=true).
    max_age = int((expires_at - datetime.now()).total_seconds())
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/",
        max_age=max_age,
    )

    logger.success("auth", "Connexion reussie", user=user)

    return {
        "message": "Connexion reussie",
        "token": session_token,
        "expires_at": expires_at,
        "user": serialize_user(user),
    }


@router.post("/logout")
def logout(response: Response, current_user=Depends(get_current_user)):
    delete_session(hash_token(current_user["raw_token"]))
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    logger.info("auth", "Deconnexion", user=current_user)
    return {"message": "Deconnexion reussie"}


@router.post("/forgot-password")
@limiter.limit("5/minute")
def forgot_password(request: Request, body: ForgotPasswordRequest):

    email = normalize_email(body.email)

    user = get_user_by_email(email)

    if not user:
        logger.info("auth", f"Demande de reinitialisation pour un email inconnu: {email}")
        return {"message": "Si le compte existe, un email de reinitialisation a ete envoye"}

    reset_token = generate_token()
    reset_token_hash = hash_token(reset_token)
    reset_expires_at = get_password_reset_expiration()

    store_password_reset_token(user["id"], reset_token_hash, reset_expires_at)

    reset_link = build_reset_link(reset_token)
    email_sent = send_email(
        email,
        "Reinitialisation du mot de passe",
        f"Bonjour {user['full_name']},\n\nReinitialisez votre mot de passe ici:\n{reset_link}",
    )

    logger.info("auth", f"Demande de reinitialisation du mot de passe pour {email}")

    response = {
        "message": "Si le compte existe, un email de reinitialisation a ete envoye",
        "email_sent": email_sent,
    }

    # Meme regle que l'inscription : jeton expose seulement sans SMTP.
    if not email_sent:
        response["reset_link"] = reset_link
        response["reset_token"] = reset_token

    return response


@router.post("/reset-password")
@limiter.limit("5/minute")
def reset_password(request: Request, body: ResetPasswordRequest):

    token_row = get_password_reset_token(hash_token(body.token))

    if not token_row:
        logger.warning("auth", "Tentative de reinitialisation avec un token invalide")
        raise HTTPException(status_code=400, detail="Token de reinitialisation invalide")

    if token_row["expires_at"] < datetime.now():
        logger.warning("auth", "Tentative de reinitialisation avec un token expire")
        raise HTTPException(status_code=400, detail="Token de reinitialisation expire")

    try:
        validate_password(body.new_password)
    except ValueError as exc:
        logger.warning("auth", f"Nouveau mot de passe refuse: {exc}")
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    new_password_hash = hash_password(body.new_password)
    update_user_password(token_row["user_id"], new_password_hash)
    delete_password_reset_tokens(token_row["user_id"])
    delete_user_sessions(token_row["user_id"])

    user = get_user_by_id(token_row["user_id"])
    logger.success("auth", "Mot de passe reinitialise", user=user)

    return {"message": "Mot de passe reinitialise avec succes"}


@router.get("/me")
def get_me(current_user=Depends(get_current_user)):
    return {"user": serialize_user(current_user)}


@router.put("/profile")
def update_profile(request: UpdateProfileRequest, current_user=Depends(get_current_user)):

    full_name = request.full_name.strip() if request.full_name else current_user["full_name"]
    email = normalize_email(request.email) if request.email else current_user["email"]

    if email != current_user["email"]:
        existing_user = get_user_by_email(email)

        if existing_user and existing_user["id"] != current_user["id"]:
            logger.warning("profile", f"Email deja utilise: {email}", user=current_user)
            raise HTTPException(status_code=400, detail="Email deja utilise")

        update_user_profile(current_user["id"], full_name, email, False)

        # L'email change : on deconnecte l'utilisateur jusqu'a verification
        # du nouvel email (meme logique qu'un changement de mot de passe).
        delete_user_sessions(current_user["id"])

        verification_token = generate_token()
        verification_token_hash = hash_token(verification_token)
        verification_expires_at = get_verification_expiration()
        store_email_verification_token(current_user["id"], verification_token_hash, verification_expires_at)

        verification_link = build_verification_link(verification_token)
        email_sent = send_email(
            email,
            "Verification de votre nouvel email",
            f"Bonjour {full_name},\n\nVerifiez votre nouvel email ici:\n{verification_link}",
        )

        updated_user = get_user_by_id(current_user["id"])

        logger.info(
            "profile",
            f"Changement d'email de {current_user['email']} vers {email}",
            user=current_user,
        )

        response = {
            "message": "Profil mis a jour. Verification du nouvel email requise",
            "email_sent": email_sent,
            "user": serialize_user(updated_user),
        }

        if not email_sent:
            response["verification_link"] = verification_link
            response["verification_token"] = verification_token

        return response

    update_user_profile(current_user["id"], full_name, email, current_user["is_email_verified"])
    updated_user = get_user_by_id(current_user["id"])

    logger.info("profile", "Mise a jour du profil", user=current_user)

    return {
        "message": "Profil mis a jour avec succes",
        "user": serialize_user(updated_user),
    }


@router.put("/change-password")
@limiter.limit("5/minute")
def change_password(request: Request, response: Response, body: ChangePasswordRequest, current_user=Depends(get_current_user)):

    if not verify_password(body.current_password, current_user["password_hash"]):
        logger.warning("auth", "Mot de passe actuel incorrect lors du changement", user=current_user)
        raise HTTPException(status_code=400, detail="Mot de passe actuel incorrect")

    try:
        validate_password(body.new_password)
    except ValueError as exc:
        logger.warning("auth", f"Nouveau mot de passe refuse: {exc}", user=current_user)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    new_password_hash = hash_password(body.new_password)
    update_user_password(current_user["id"], new_password_hash)
    delete_user_sessions(current_user["id"])
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")

    logger.info("auth", "Changement du mot de passe", user=current_user)

    return {"message": "Mot de passe modifie. Reconnectez-vous"}


@router.delete("/delete-account")
def delete_account(response: Response, request: DeleteAccountRequest, current_user=Depends(get_current_user)):

    if not verify_password(request.password, current_user["password_hash"]):
        logger.warning("auth", "Mot de passe incorrect lors de la suppression du compte", user=current_user)
        raise HTTPException(status_code=400, detail="Mot de passe incorrect")

    delete_email_verification_tokens(current_user["id"])
    delete_password_reset_tokens(current_user["id"])
    delete_user_sessions(current_user["id"])
    delete_user_account(current_user["id"])
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")

    logger.warning("auth", "Compte supprime", user=current_user)

    return {"message": "Compte supprime avec succes"}
