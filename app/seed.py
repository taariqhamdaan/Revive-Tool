import os
from datetime import datetime, timezone

from app.extensions import db
from app.models.foundation import Branch
from app.models.users import Role, User


def run_seed():
    """Idempotent: creates the default branch, SuperAdmin role and first login if missing."""
    branch = Branch.query.filter_by(code="BR001").first()
    if not branch:
        branch = Branch(
            code="BR001",
            name=os.environ.get("APP_NAME", "Rivive Speciality Care Hospital"),
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.session.add(branch)
        db.session.flush()
        print(f"Created default branch '{branch.code}'.")

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
        # Not NULL: most create routes use current_user.branch_id directly, which
        # would otherwise violate NOT NULL constraints on every branch-scoped table.
        # is_superadmin (not branch_id) is what actually grants full access.
        branch_id=branch.id,
        is_superadmin=True,
        is_active=True,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    print(f"Created SuperAdmin user '{username}'.")
