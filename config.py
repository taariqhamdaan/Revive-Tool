# Revive - config.py
# Environment-based configuration. Reads from .env file.

import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base configuration shared across all environments."""

    # ── Core ──────────────────────────────────────────────────────────────
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-key-change-in-production")
    APP_NAME = os.environ.get("APP_NAME", "Rivive Speciality Care Hospital")
    APP_URL = os.environ.get("APP_URL", "http://localhost:5000")

    # ── Database ──────────────────────────────────────────────────────────
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "postgresql://revive_user:password@localhost:5432/revive_db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 10,          # base connections kept open
        "max_overflow": 20,       # extra connections under load
        "pool_timeout": 30,       # seconds before giving up on a connection
        "pool_recycle": 1800,     # recycle connections every 30 min
        "pool_pre_ping": True,    # verify connection is alive before using
    }

    # ── Sessions ──────────────────────────────────────────────────────────
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_DURATION = timedelta(days=1)

    # ── Email ─────────────────────────────────────────────────────────────
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "1") == "1"
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "Revive <noreply@revive.local>")

    # ── File Uploads ──────────────────────────────────────────────────────
    # Vercel's function filesystem is read-only outside /tmp.
    _files_root = "/tmp" if os.environ.get("VERCEL") else os.path.dirname(os.path.abspath(__file__))
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_SIZE_MB", 10)) * 1024 * 1024
    UPLOAD_FOLDER = os.path.join(_files_root, "uploads")
    EXPORT_FOLDER = os.path.join(_files_root, "exports")
    ALLOWED_EXTENSIONS = {"xlsx", "xls", "csv", "pdf", "jpg", "jpeg", "png"}

    # ── Security ──────────────────────────────────────────────────────────
    ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY")
    PASSWORD_MIN_LENGTH = 8
    PASSWORD_RESET_EXPIRY = timedelta(hours=2)
    MAX_LOGIN_ATTEMPTS = 5
    LOCKOUT_DURATION = timedelta(minutes=15)

    # ── Babel (i18n) ──────────────────────────────────────────────────────
    BABEL_DEFAULT_LOCALE = "en"
    BABEL_SUPPORTED_LOCALES = ["en", "ta"]  # English, Tamil
    BABEL_TRANSLATION_DIRECTORIES = "translations"

    # ── Rate Limiting ─────────────────────────────────────────────────────
    RATELIMIT_STORAGE_URL = os.environ.get("RATELIMIT_STORAGE_URL", "memory://")
    RATELIMIT_DEFAULT = "200 per hour"

    # ── Pagination ────────────────────────────────────────────────────────
    RECORDS_PER_PAGE = 25


class DevelopmentConfig(Config):
    """Development — debug on, relaxed security."""
    FLASK_DEBUG = True
    SQLALCHEMY_ECHO = False  # Set True to log all SQL queries


class ProductionConfig(Config):
    """Production — hardened settings."""
    FLASK_DEBUG = False
    SESSION_COOKIE_SECURE = True   # requires HTTPS (Cloudflare provides this)
    REMEMBER_COOKIE_SECURE = True


class TestingConfig(Config):
    """Testing — in-memory SQLite, no emails sent."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    MAIL_SUPPRESS_SEND = True


# Config selector
config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config():
    env = os.environ.get("FLASK_ENV", "production")
    return config_map.get(env, ProductionConfig)
