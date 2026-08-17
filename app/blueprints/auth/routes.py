# Revive - app/blueprints/auth/routes.py
# Authentication: login, logout, password reset, language toggle, profile.
# Logic summary:
#   - Login: validate credentials, check lockout, record session, audit log
#   - Logout: clear session, mark session inactive, audit log
#   - Password reset: email token flow (2hr expiry)
#   - Language toggle: switch session lang between en/ta

import secrets
from datetime import datetime, timezone, timedelta
from flask import (Blueprint, render_template, redirect, url_for,
                   request, flash, session, current_app, jsonify)
from flask_login import login_user, logout_user, login_required, current_user
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app.extensions import db, login_manager
from app.models.users import User, UserSession, PasswordHistory, AuditLog
from app.utils.audit import log_action
from app.utils.email import send_password_reset_email

auth_bp = Blueprint("auth", __name__)


# ── Flask-Login user loader ───────────────────────────────────────────────────

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ── Login ─────────────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        remember = request.form.get("remember") == "on"

        user = User.query.filter(
            (User.username == username) | (User.email == username),
            User.is_deleted == False,
        ).first()

        # Account not found
        if not user:
            flash("Invalid username or password.", "danger")
            return render_template("auth/login.html")

        # Account inactive
        if not user.is_active:
            flash("Account is inactive. Contact administrator.", "warning")
            return render_template("auth/login.html")

        # Account locked
        if user.is_locked():
            remaining = int((user.locked_until - datetime.now(timezone.utc)).total_seconds() / 60)
            flash(f"Account locked. Try again in {remaining} minute(s).", "danger")
            return render_template("auth/login.html")

        # Wrong password
        if not user.check_password(password):
            user.login_attempts = (user.login_attempts or 0) + 1
            max_attempts = current_app.config.get("MAX_LOGIN_ATTEMPTS", 5)
            if user.login_attempts >= max_attempts:
                lockout = current_app.config.get("LOCKOUT_DURATION", timedelta(minutes=15))
                user.locked_until = datetime.now(timezone.utc) + lockout
                db.session.commit()
                flash(f"Too many failed attempts. Account locked for 15 minutes.", "danger")
            else:
                db.session.commit()
                flash(f"Invalid password. {max_attempts - user.login_attempts} attempt(s) remaining.", "danger")
            return render_template("auth/login.html")

        # Successful login
        user.login_attempts  = 0
        user.locked_until    = None
        user.last_login      = datetime.now(timezone.utc)
        user.last_login_ip   = _get_ip()
        db.session.commit()

        # Record session
        sess = UserSession(
            user_id=user.id,
            session_token=secrets.token_urlsafe(32),
            ip_address=_get_ip(),
            user_agent=request.headers.get("User-Agent", "")[:255],
            branch_id=user.branch_id,
        )
        db.session.add(sess)
        db.session.commit()

        login_user(user, remember=remember)

        # Set language preference
        session["lang"] = user.preferred_lang or "en"

        log_action("LOGIN", "auth", notes=f"Login from {_get_ip()}", user_id=user.id, branch_id=user.branch_id)

        # Force password change if required
        if user.must_change_pwd:
            flash("Please change your password before continuing.", "warning")
            return redirect(url_for("auth.change_password"))

        next_page = request.args.get("next")
        return redirect(next_page or url_for("dashboard.index"))

    return render_template("auth/login.html")


# ── Logout ────────────────────────────────────────────────────────────────────

@auth_bp.route("/logout")
@login_required
def logout():
    log_action("LOGOUT", "auth", user_id=current_user.id, branch_id=current_user.branch_id)

    # Mark active sessions as closed
    UserSession.query.filter_by(user_id=current_user.id, is_active=True).update(
        {"is_active": False, "logout_at": datetime.now(timezone.utc)}
    )
    db.session.commit()
    logout_user()
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


# ── Password Reset — Request ──────────────────────────────────────────────────

@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email, is_deleted=False).first()

        # Always show same message to prevent email enumeration
        flash("If that email exists, a reset link has been sent.", "info")

        if user and user.is_active:
            token = _generate_reset_token(user.email)
            reset_url = url_for("auth.reset_password", token=token, _external=True)
            send_password_reset_email(user, reset_url)
            log_action("PASSWORD_RESET_REQUEST", "auth", user_id=user.id)

        return redirect(url_for("auth.login"))

    return render_template("auth/forgot_password.html")


# ── Password Reset — Set New Password ────────────────────────────────────────

@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    email = _verify_reset_token(token)
    if not email:
        flash("Reset link is invalid or has expired.", "danger")
        return redirect(url_for("auth.forgot_password"))

    user = User.query.filter_by(email=email, is_deleted=False).first()
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        new_password = request.form.get("password", "")
        confirm      = request.form.get("confirm_password", "")

        if len(new_password) < current_app.config.get("PASSWORD_MIN_LENGTH", 8):
            flash(f"Password must be at least {current_app.config['PASSWORD_MIN_LENGTH']} characters.", "danger")
            return render_template("auth/reset_password.html", token=token)

        if new_password != confirm:
            flash("Passwords do not match.", "danger")
            return render_template("auth/reset_password.html", token=token)

        # Check password history (last 5)
        if _is_recent_password(user, new_password):
            flash("Cannot reuse a recent password.", "danger")
            return render_template("auth/reset_password.html", token=token)

        # Save to history before changing
        _save_password_history(user)

        user.set_password(new_password)
        user.must_change_pwd = False
        db.session.commit()

        log_action("PASSWORD_RESET", "auth", user_id=user.id)
        flash("Password reset successfully. Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html", token=token)


# ── Change Password (logged in) ───────────────────────────────────────────────

@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_pwd = request.form.get("current_password", "")
        new_pwd     = request.form.get("new_password", "")
        confirm     = request.form.get("confirm_password", "")

        if not current_user.check_password(current_pwd):
            flash("Current password is incorrect.", "danger")
            return render_template("auth/change_password.html")

        if new_pwd != confirm:
            flash("New passwords do not match.", "danger")
            return render_template("auth/change_password.html")

        if len(new_pwd) < current_app.config.get("PASSWORD_MIN_LENGTH", 8):
            flash(f"Password must be at least {current_app.config['PASSWORD_MIN_LENGTH']} characters.", "danger")
            return render_template("auth/change_password.html")

        if _is_recent_password(current_user, new_pwd):
            flash("Cannot reuse a recent password.", "danger")
            return render_template("auth/change_password.html")

        _save_password_history(current_user)
        current_user.set_password(new_pwd)
        current_user.must_change_pwd = False
        db.session.commit()

        log_action("PASSWORD_CHANGED", "auth")
        flash("Password changed successfully.", "success")
        return redirect(url_for("dashboard.index"))

    return render_template("auth/change_password.html")


# ── Language Toggle ───────────────────────────────────────────────────────────

@auth_bp.route("/set-language/<lang>")
def set_language(lang):
    if lang in ("en", "ta"):
        session["lang"] = lang
        if current_user.is_authenticated:
            current_user.preferred_lang = lang
            db.session.commit()
    return redirect(request.referrer or url_for("dashboard.index"))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _generate_reset_token(email: str) -> str:
    s = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    return s.dumps(email, salt="password-reset")


def _verify_reset_token(token: str) -> str:
    s = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    expiry = int(current_app.config.get("PASSWORD_RESET_EXPIRY", timedelta(hours=2)).total_seconds())
    try:
        email = s.loads(token, salt="password-reset", max_age=expiry)
        return email
    except (BadSignature, SignatureExpired):
        return None


def _is_recent_password(user: User, new_password: str) -> bool:
    history = PasswordHistory.query.filter_by(user_id=user.id).order_by(
        PasswordHistory.changed_at.desc()
    ).limit(5).all()
    from app.extensions import bcrypt
    for h in history:
        if bcrypt.check_password_hash(h.password_hash, new_password):
            return True
    return False


def _save_password_history(user: User):
    history = PasswordHistory(user_id=user.id, password_hash=user.password_hash)
    db.session.add(history)
    # Keep only last 5
    old_entries = PasswordHistory.query.filter_by(user_id=user.id).order_by(
        PasswordHistory.changed_at.desc()
    ).offset(5).all()
    for e in old_entries:
        db.session.delete(e)


def _get_ip() -> str:
    cf = request.headers.get("CF-Connecting-IP")
    if cf:
        return cf
    fwd = request.headers.get("X-Forwarded-For")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.remote_addr or ""
