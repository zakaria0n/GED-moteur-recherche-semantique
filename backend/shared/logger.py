"""Logging configuration for the backend."""

import logging
from logging.handlers import RotatingFileHandler

from config import LOG_DIR


SUCCESS_LEVEL = 25
logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")


def _build_logger():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / "backend.log"

    logger = logging.getLogger("ged.backend")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-9s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


_logger = _build_logger()


def _user_suffix(user):
    """Build the user part of a log message."""
    if not user:
        return ""

    if isinstance(user, dict):
        name = user.get("full_name") or user.get("email") or "?"
        email = user.get("email")
        suffix = f" — user: {name}"

        if email and email != name:
            suffix += f" ({email})"

        return suffix

    return f" — email: {user}"


def info(category, message, user=None):
    _logger.log(logging.INFO, f"[{category}] {message}{_user_suffix(user)}")


def success(category, message, user=None):
    _logger.log(SUCCESS_LEVEL, f"[{category}] {message}{_user_suffix(user)}")


def warning(category, message, user=None):
    _logger.log(logging.WARNING, f"[{category}] {message}{_user_suffix(user)}")


def error(category, message, user=None):
    _logger.log(logging.ERROR, f"[{category}] {message}{_user_suffix(user)}")


def request(method, path, status_code, duration_ms, user=None):
    """Log an HTTP request with its result and duration."""
    if status_code >= 500:
        level = logging.ERROR
    elif status_code >= 400:
        level = logging.WARNING
    else:
        level = logging.INFO

    user_text = _user_suffix(user) if user else " — not connected"

    _logger.log(
        level,
        f"[request] {method} {path} -> {status_code} "
        f"({duration_ms:.0f} ms){user_text}",
    )
