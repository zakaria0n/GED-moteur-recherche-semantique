"""Helpers de serialisation partages (sans dependance metier)."""


def serialize_user(user):
    return {
        "id": user["id"],
        "full_name": user["full_name"],
        "email": user["email"],
        "is_email_verified": bool(user["is_email_verified"]),
        "created_at": user["created_at"],
        "updated_at": user["updated_at"],
    }


def normalize_email(email):
    return email.strip().lower()
