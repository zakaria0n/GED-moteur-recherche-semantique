"""Adaptateur d'envoi d'emails (SMTP Brevo / serveur mail externe).

Cache la mecanique SMTP derriere une fonction simple : c'est un adaptateur
sortant (le serveur de mail est un tiers), aucune regle metier ici.
"""

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from config import (
    SMTP_FROM_EMAIL,
    SMTP_FROM_NAME,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USER,
)


def send_email(recipient, subject, body):
    if not SMTP_HOST:
        print(f"[EMAIL] SMTP non configure. Destinataire: {recipient}")
        print(f"[EMAIL] Sujet: {subject}")
        print(f"[EMAIL] Contenu: {body}")
        return False

    message = EmailMessage()
    message["From"] = formataddr((SMTP_FROM_NAME, SMTP_FROM_EMAIL))
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.starttls(context=ssl.create_default_context())

        if SMTP_USER:
            smtp.login(SMTP_USER, SMTP_PASSWORD)

        smtp.send_message(message)

    return True
