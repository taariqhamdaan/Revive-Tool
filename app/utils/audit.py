# Rivive - app/utils/audit.py
# Utility to write audit log entries from anywhere in the application.
# Call log_action() after any CREATE / UPDATE / DELETE operation.

import json
from datetime import datetime, timezone
from flask import request
from flask_login import current_user
from app.extensions import db
from app.models.users import AuditLog


def log_action(
    action: str,
    module: str,
    record_id: int = None,
    record_type: str = None,
    old_value: dict = None,
    new_value: dict = None,
    notes: str = None,
    user_id: int = None,
    branch_id: int = None,
):
    """
    Write an audit log entry.

    Parameters:
        action      — CREATE, UPDATE, DELETE, LOGIN, LOGOUT, EXPORT, VIEW
        module      — patients, billing, hr, etc.
        record_id   — primary key of the affected record
        record_type — model class name (e.g. 'Patient')
        old_value   — dict of previous state (before change)
        new_value   — dict of new state (after change)
        notes       — free text note
        user_id     — override; defaults to current_user.id
        branch_id   — override; defaults to current_user.branch_id
    """
    try:
        uid = user_id
        bid = branch_id

        if uid is None and current_user and current_user.is_authenticated:
            uid = current_user.id
        if bid is None and current_user and current_user.is_authenticated:
            bid = getattr(current_user, "branch_id", None)

        entry = AuditLog(
            user_id     = uid,
            branch_id   = bid,
            action      = action,
            module      = module,
            record_id   = record_id,
            record_type = record_type,
            old_value   = json.dumps(old_value, default=str) if old_value else None,
            new_value   = json.dumps(new_value, default=str) if new_value else None,
            ip_address  = _get_ip(),
            user_agent  = request.headers.get("User-Agent", "")[:255] if request else None,
            timestamp   = datetime.now(timezone.utc),
            notes       = notes,
        )
        db.session.add(entry)
        db.session.commit()
    except Exception as e:
        # Audit failures must NOT break the main request
        db.session.rollback()


def _get_ip() -> str:
    """Extract real IP, respecting Cloudflare proxy headers."""
    if request:
        # Cloudflare passes real IP in CF-Connecting-IP
        cf_ip = request.headers.get("CF-Connecting-IP")
        if cf_ip:
            return cf_ip
        # Standard proxy header
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.remote_addr or ""
    return ""
