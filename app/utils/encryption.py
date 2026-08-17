# Revive - app/utils/encryption.py
# Field-level encryption for sensitive patient/employee data (Aadhaar, bank accounts).
# Uses Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256).
# Key is loaded from environment — never hardcoded.

import os
import base64
from cryptography.fernet import Fernet, InvalidToken
from flask import current_app


def _get_fernet() -> Fernet:
    """Load Fernet instance from app config. Generates a dev key if not set."""
    key = current_app.config.get("ENCRYPTION_KEY")
    if not key:
        # Development fallback — logs a warning; production MUST set ENCRYPTION_KEY
        current_app.logger.warning("ENCRYPTION_KEY not set — using insecure dev key.")
        key = Fernet.generate_key().decode()
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


def encrypt(plaintext: str) -> str:
    """Encrypt a string. Returns base64-encoded ciphertext string."""
    if not plaintext:
        return ""
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a ciphertext string. Returns plaintext or empty string on failure."""
    if not ciphertext:
        return ""
    try:
        f = _get_fernet()
        return f.decrypt(ciphertext.encode()).decode()
    except (InvalidToken, Exception):
        return ""


def mask_aadhaar(aadhaar: str) -> str:
    """Return masked Aadhaar: XXXX-XXXX-1234 (last 4 digits only)."""
    digits = "".join(filter(str.isdigit, aadhaar or ""))
    if len(digits) == 12:
        return f"XXXX-XXXX-{digits[-4:]}"
    return "XXXX-XXXX-XXXX"


def generate_encryption_key() -> str:
    """Generate a new Fernet key. Run once during initial setup."""
    return Fernet.generate_key().decode()
