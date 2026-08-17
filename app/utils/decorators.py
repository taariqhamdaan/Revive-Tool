# MediCore - app/utils/decorators.py
# Custom decorators for route-level permission enforcement.
# Usage: @require_permission("patients", "create")

from functools import wraps
from flask import abort, flash, redirect, url_for, request
from flask_login import current_user


def require_permission(module: str, action: str):
    """
    Decorator that checks if the current user has the given module+action permission.
    SuperAdmin always passes. Unauthenticated users are redirected to login.

    Usage:
        @require_permission("patients", "create")
        def create_patient():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login", next=request.url))
            if not current_user.is_active:
                flash("Your account is inactive. Please contact admin.", "danger")
                return redirect(url_for("auth.login"))
            if not current_user.has_permission(module, action):
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def superadmin_required(f):
    """Restrict route to SuperAdmin only."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if not current_user.is_superadmin:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


def branch_admin_required(f):
    """Restrict route to BranchAdmin or SuperAdmin."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        role_name = current_user.role.name if current_user.role else ""
        if not (current_user.is_superadmin or role_name in ("BranchAdmin", "SuperAdmin")):
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


def active_required(f):
    """Ensure user account is active."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if not current_user.is_active:
            flash("Account inactive. Contact administrator.", "danger")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated_function
