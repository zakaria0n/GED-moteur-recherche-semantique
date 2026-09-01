"""Operations DB sur les utilisateurs, sessions et tokens."""

from repositories.connection import get_connection


def initialize_schema(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            full_name VARCHAR(255) NOT NULL,
            email VARCHAR(255) NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            is_email_verified BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS email_verification_tokens (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            token_hash VARCHAR(64) NOT NULL UNIQUE,
            expires_at DATETIME NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            token_hash VARCHAR(64) NOT NULL UNIQUE,
            expires_at DATETIME NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_sessions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            token_hash VARCHAR(64) NOT NULL UNIQUE,
            remember_me BOOLEAN NOT NULL DEFAULT FALSE,
            expires_at DATETIME NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )


# ---- Users ----


def get_user_by_email(email):
    with get_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id, full_name, email, password_hash, is_email_verified, created_at, updated_at
            FROM users
            WHERE email = %s
            """,
            (email,),
        )
        user = cursor.fetchone()
        cursor.close()

    return user


def get_user_by_id(user_id):
    with get_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id, full_name, email, password_hash, is_email_verified, created_at, updated_at
            FROM users
            WHERE id = %s
            """,
            (user_id,),
        )
        user = cursor.fetchone()
        cursor.close()

    return user


def create_user(full_name, email, password_hash):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO users (full_name, email, password_hash)
            VALUES (%s, %s, %s)
            """,
            (full_name, email, password_hash),
        )
        user_id = cursor.lastrowid
        conn.commit()
        cursor.close()

    return user_id


def update_user_profile(user_id, full_name, email, is_email_verified):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE users
            SET full_name = %s, email = %s, is_email_verified = %s
            WHERE id = %s
            """,
            (full_name, email, is_email_verified, user_id),
        )
        conn.commit()
        cursor.close()


def update_user_password(user_id, password_hash):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE users
            SET password_hash = %s
            WHERE id = %s
            """,
            (password_hash, user_id),
        )
        conn.commit()
        cursor.close()


def mark_user_email_verified(user_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE users
            SET is_email_verified = TRUE
            WHERE id = %s
            """,
            (user_id,),
        )
        conn.commit()
        cursor.close()


def delete_user_account(user_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        cursor.close()


# ---- Tokens de verification / reset ----


def store_email_verification_token(user_id, token_hash, expires_at):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM email_verification_tokens WHERE user_id = %s", (user_id,))
        cursor.execute(
            """
            INSERT INTO email_verification_tokens (user_id, token_hash, expires_at)
            VALUES (%s, %s, %s)
            """,
            (user_id, token_hash, expires_at),
        )
        conn.commit()
        cursor.close()


def get_email_verification_token(token_hash):
    with get_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id, user_id, token_hash, expires_at
            FROM email_verification_tokens
            WHERE token_hash = %s
            """,
            (token_hash,),
        )
        token_row = cursor.fetchone()
        cursor.close()

    return token_row


def delete_email_verification_tokens(user_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM email_verification_tokens WHERE user_id = %s", (user_id,))
        conn.commit()
        cursor.close()


def store_password_reset_token(user_id, token_hash, expires_at):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM password_reset_tokens WHERE user_id = %s", (user_id,))
        cursor.execute(
            """
            INSERT INTO password_reset_tokens (user_id, token_hash, expires_at)
            VALUES (%s, %s, %s)
            """,
            (user_id, token_hash, expires_at),
        )
        conn.commit()
        cursor.close()


def get_password_reset_token(token_hash):
    with get_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id, user_id, token_hash, expires_at
            FROM password_reset_tokens
            WHERE token_hash = %s
            """,
            (token_hash,),
        )
        token_row = cursor.fetchone()
        cursor.close()

    return token_row


def delete_password_reset_tokens(user_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM password_reset_tokens WHERE user_id = %s", (user_id,))
        conn.commit()
        cursor.close()


# ---- Sessions ----


def create_user_session(user_id, token_hash, remember_me, expires_at):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO user_sessions (user_id, token_hash, remember_me, expires_at)
            VALUES (%s, %s, %s, %s)
            """,
            (user_id, token_hash, remember_me, expires_at),
        )
        conn.commit()
        cursor.close()


def get_session_with_user(token_hash):
    with get_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                user_sessions.id AS session_id,
                user_sessions.user_id,
                user_sessions.expires_at,
                users.full_name,
                users.email,
                users.password_hash,
                users.is_email_verified,
                users.created_at,
                users.updated_at
            FROM user_sessions
            JOIN users ON users.id = user_sessions.user_id
            WHERE user_sessions.token_hash = %s
            """,
            (token_hash,),
        )
        session = cursor.fetchone()
        cursor.close()

    return session


def delete_session(token_hash):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_sessions WHERE token_hash = %s", (token_hash,))
        conn.commit()
        cursor.close()


def delete_user_sessions(user_id):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_sessions WHERE user_id = %s", (user_id,))
        conn.commit()
        cursor.close()
