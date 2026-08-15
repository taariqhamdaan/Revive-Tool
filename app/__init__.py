import os
from flask import Flask, redirect, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from .extensions import db, login_manager, csrf, migrate


def _database_uri():
    """Railway/Heroku hand out postgres:// which SQLAlchemy 2.x no longer accepts."""
    uri = os.environ.get("DATABASE_URL", "sqlite:///rivive.db")
    if uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    return uri


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"]               = os.environ.get("SECRET_KEY","rivive-dev-2026")
    app.config["SQLALCHEMY_DATABASE_URI"]  = _database_uri()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["WTF_CSRF_ENABLED"]         = os.environ.get("WTF_CSRF_ENABLED","1") == "1"

    # Railway recycles idle Postgres connections; pre_ping avoids stale-socket 500s.
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql"):
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True, "pool_recycle": 300}

    # Railway terminates TLS at its edge; without this url_for(_external=True) emits http://
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    @login_manager.user_loader
    def load_user(uid):
        from .models.foundation import User
        return User.query.get(int(uid))

    with app.app_context():
        from .models import foundation, lab  # noqa

    from .blueprints.lab.routes import lab_bp
    from .blueprints.auth.routes import auth_bp
    app.register_blueprint(lab_bp, url_prefix="/lab")
    app.register_blueprint(auth_bp, url_prefix="/auth")

    @app.route("/")
    def home():
        return redirect(url_for("lab.index"))

    @app.route("/healthz")
    def healthz():
        return {"status": "ok"}, 200

    @app.context_processor
    def _ctx():
        from datetime import date
        return {"today": date.today(), "app_name": "Rivive SCH"}

    register_cli(app)
    return app


def register_cli(app):
    """`flask init-db` and `flask seed` — used once after the first Railway deploy."""
    import click

    @app.cli.command("init-db")
    def init_db():
        db.create_all()
        click.echo("Tables created.")

    @app.cli.command("seed")
    def seed():
        from .seed import run_seed
        run_seed()
