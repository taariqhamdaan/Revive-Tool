# Rivive - app/__init__.py
# Application factory. Creates and configures the Flask app.
# All blueprints, extensions, and middleware are registered here.

import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, request, session, g, redirect, url_for
from flask_babel import Babel
from werkzeug.middleware.proxy_fix import ProxyFix

from config import get_config
from app.extensions import db, migrate, login_manager, mail, babel, bcrypt, limiter, csrf


def create_app():
    """Create and configure the Flask application instance."""

    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    # ── Load Config ───────────────────────────────────────────────────────
    app.config.from_object(get_config())

    # Railway/Vercel terminate TLS at the edge; without this url_for(_external=True)
    # and secure-cookie checks see plain http.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # ── Ensure Required Folders Exist ───────────────────────────────────────
    # Vercel's function filesystem is read-only outside /tmp — writes elsewhere
    # raise OSError, so folder creation (and, in _setup_logging, file logging)
    # is best-effort rather than fatal.
    for folder in [app.config["UPLOAD_FOLDER"], app.config["EXPORT_FOLDER"], "logs"]:
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError:
            pass

    # ── Initialise Extensions ─────────────────────────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    mail.init_app(app)
    bcrypt.init_app(app)
    limiter.init_app(app)
    csrf.init_app(app)

    # ── Babel (i18n) ──────────────────────────────────────────────────────
    def get_locale():
        # 1. User preference stored in session
        if "lang" in session:
            return session["lang"]
        # 2. Accept-Language header fallback
        return request.accept_languages.best_match(["en", "ta"], default="en")

    babel.init_app(app, locale_selector=get_locale)

    # Jinja has no built-in enumerate(); templates (e.g. payroll/index.html) use it.
    app.jinja_env.globals["enumerate"] = enumerate

    # ── Register Blueprints ───────────────────────────────────────────────
    _register_blueprints(app)

    # ── Register Error Handlers ───────────────────────────────────────────
    _register_error_handlers(app)

    # ── Logging ───────────────────────────────────────────────────────────
    _setup_logging(app)

    # ── Health check + root redirect ────────────────────────────────────────
    @app.route("/healthz")
    def healthz():
        return {"status": "ok"}, 200

    @app.route("/")
    def home():
        return redirect(url_for("dashboard.index"))

    register_cli(app)

    # ── Shell Context ─────────────────────────────────────────────────────
    @app.shell_context_processor
    def make_shell_context():
        return {"db": db, "app": app}

    # ── Inject global template variables ─────────────────────────────────
    @app.context_processor
    def inject_globals():
        from flask_login import current_user
        from datetime import datetime
        return {
            "app_name": app.config.get("APP_NAME", "Rivive"),
            "current_user": current_user,
            "now": datetime.now(),
            "today": datetime.today().date(),
        }

    return app


def _register_blueprints(app):
    """Register all application blueprints."""

    from app.blueprints.auth.routes import auth_bp
    from app.blueprints.dashboard.routes import dashboard_bp
    from app.blueprints.patients.routes import patients_bp
    from app.blueprints.opd.routes import opd_bp
    from app.blueprints.ipd.routes import ipd_bp
    from app.blueprints.pharmacy.routes import pharmacy_bp
    from app.blueprints.lab.routes import lab_bp
    from app.blueprints.radiology.routes import radiology_bp
    from app.blueprints.billing.routes import billing_bp
    from app.blueprints.insurance.routes import insurance_bp
    from app.blueprints.hr.routes import hr_bp
    from app.blueprints.payroll.routes import payroll_bp
    from app.blueprints.reports.routes import reports_bp
    from app.blueprints.settings.routes import settings_bp

    app.register_blueprint(auth_bp,      url_prefix="/auth")
    app.register_blueprint(dashboard_bp, url_prefix="/dashboard")
    app.register_blueprint(patients_bp,  url_prefix="/patients")
    app.register_blueprint(opd_bp,       url_prefix="/opd")
    app.register_blueprint(ipd_bp,       url_prefix="/ipd")
    app.register_blueprint(pharmacy_bp,  url_prefix="/pharmacy")
    app.register_blueprint(lab_bp,       url_prefix="/lab")
    app.register_blueprint(radiology_bp, url_prefix="/radiology")
    app.register_blueprint(billing_bp,   url_prefix="/billing")
    app.register_blueprint(insurance_bp, url_prefix="/insurance")
    app.register_blueprint(hr_bp,        url_prefix="/hr")
    app.register_blueprint(payroll_bp,   url_prefix="/payroll")
    app.register_blueprint(reports_bp,   url_prefix="/reports")
    app.register_blueprint(settings_bp,  url_prefix="/settings")


def _register_error_handlers(app):
    """Custom error pages."""
    from flask import render_template

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("shared/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("shared/404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("shared/500.html"), 500


def _setup_logging(app):
    """File-based rotating log, structured for production. Falls back to
    stdout-only logging where the filesystem is read-only (e.g. Vercel)."""
    if not app.debug:
        try:
            handler = RotatingFileHandler(
                "logs/rivive.log",
                maxBytes=5 * 1024 * 1024,  # 5 MB per file
                backupCount=10,
            )
            handler.setLevel(logging.INFO)
            formatter = logging.Formatter(
                "[%(asctime)s] %(levelname)s in %(module)s: %(message)s"
            )
            handler.setFormatter(formatter)
            app.logger.addHandler(handler)
            app.logger.setLevel(logging.INFO)
            app.logger.info("Rivive startup complete.")
        except OSError:
            app.logger.setLevel(logging.INFO)


def register_cli(app):
    """`flask seed` — bootstraps the SuperAdmin role/user. Run once after
    the first deploy to each environment (Railway, Vercel)."""
    import click

    @app.cli.command("seed")
    def seed():
        from .seed import run_seed
        run_seed()
