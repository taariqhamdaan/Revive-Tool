# Rivive SCH - app/blueprints/auth/routes.py
# Minimal login/logout so @login_required routes can resolve login_view = "auth.login".

from urllib.parse import urlparse
from flask import (Blueprint, render_template, redirect, url_for,
                   request, flash)
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import or_
from app.models.foundation import User

auth_bp = Blueprint("auth", __name__)


def _safe_next(target):
    """Only honour ?next= when it points back at this host."""
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.netloc or parsed.scheme:
        return None
    if not target.startswith("/"):
        return None
    return target


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("lab.index"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        user = User.query.filter(
            or_(User.username == username, User.email == username)
        ).filter_by(is_deleted=False).first()

        if user is None or not user.check_password(password):
            flash("Invalid username or password.", "danger")
            return render_template("auth/login.html", username=username), 401

        if not user.is_active:
            flash("This account is disabled. Contact your administrator.", "warning")
            return render_template("auth/login.html", username=username), 403

        login_user(user, remember=bool(request.form.get("remember")))
        return redirect(_safe_next(request.args.get("next")) or url_for("lab.index"))

    return render_template("auth/login.html", username="")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))
