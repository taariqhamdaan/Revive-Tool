# Rivive - extensions.py
# All Flask extensions are initialised here without the app object.
# The app is passed in via init_app() inside create_app() in __init__.py
# This avoids circular imports across blueprints.

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_mail import Mail
from flask_babel import Babel
from flask_bcrypt import Bcrypt
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect

# ── Database ORM ──────────────────────────────────────────────────────────────
db = SQLAlchemy()

# ── Database Migrations ───────────────────────────────────────────────────────
migrate = Migrate()

# ── Authentication ────────────────────────────────────────────────────────────
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "warning"
# "strong" ties the session to a hash of remote_addr + user agent and drops
# it silently on mismatch. Behind Railway/Vercel's edge proxies the forwarded
# client IP isn't always stable hop-to-hop, which was logging users out on
# essentially random requests. "basic" only affects session freshness.
login_manager.session_protection = "basic"

# ── Email ─────────────────────────────────────────────────────────────────────
mail = Mail()

# ── Internationalisation (English + Tamil) ────────────────────────────────────
babel = Babel()

# ── Password Hashing ──────────────────────────────────────────────────────────
bcrypt = Bcrypt()

# ── Rate Limiting ─────────────────────────────────────────────────────────────
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per hour", "50 per minute"],
)

# ── CSRF Protection ───────────────────────────────────────────────────────────
csrf = CSRFProtect()
