import os
import secrets

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _db_uri():
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+pg8000://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+pg8000://", 1)
    return url or f"sqlite:///{os.path.join(BASE_DIR, 'sponge.db')}"


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    SQLALCHEMY_DATABASE_URI = _db_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("RAILWAY_ENVIRONMENT") is not None
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 24 * 30  # 30 days

    # WebAuthn
    RP_ID = os.environ.get("RP_ID", "localhost")
    RP_NAME = "Sponge"
    ORIGIN = os.environ.get("ORIGIN", "http://localhost:8080")
