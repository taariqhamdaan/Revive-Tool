import os

from app.extensions import db
from app.models.users import Role, User


def run_seed():
    """Idempotent: creates the SuperAdmin role and first login if missing."""
    role = Role.query.filter_by(name="SuperAdmin", branch_id=None).first()
    if not role:
        role = Role(name="SuperAdmin", description="Full system access", is_system=True)
        db.session.add(role)
        db.session.flush()

    username = os.environ.get("SEED_ADMIN_USERNAME", "admin")
    user = User.query.filter_by(username=username).first()
    if user:
        print(f"User '{username}' already exists — skipping.")
        db.session.commit()
        return

    password = os.environ.get("SEED_ADMIN_PASSWORD")
    if not password:
        raise SystemExit("SEED_ADMIN_PASSWORD is not set — aborting seed.")

    user = User(
        username=username,
        email=os.environ.get("SEED_ADMIN_EMAIL", "admin@rivive.local"),
        full_name="System Administrator",
        role_id=role.id,
        branch_id=None,
        is_superadmin=True,
        is_active=True,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    print(f"Created SuperAdmin user '{username}'.")
