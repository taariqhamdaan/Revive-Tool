# Rivive - app/models/users.py
# User authentication, role-based access control, sessions, audit.
# Roles are assigned per branch. SuperAdmin bypasses all permission checks.

from datetime import datetime, timezone
from flask_login import UserMixin
from app.extensions import db, bcrypt


# ── Role ──────────────────────────────────────────────────────────────────────

class Role(db.Model):
    """
    Roles define what a user can do. Examples: SuperAdmin, BranchAdmin,
    Doctor, Nurse, Pharmacist, Receptionist, LabTechnician, Accountant, HR.
    Roles are per-branch except SuperAdmin (branch_id=NULL).
    """
    __tablename__ = "roles"

    id          = db.Column(db.Integer, primary_key=True)
    branch_id   = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=True)
    name        = db.Column(db.String(80), nullable=False)
    name_ta     = db.Column(db.String(80))
    description = db.Column(db.String(255))
    is_system   = db.Column(db.Boolean, default=False)   # system roles cannot be deleted
    is_active   = db.Column(db.Boolean, default=True)
    is_deleted  = db.Column(db.Boolean, default=False)
    created_at  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    branch      = db.relationship("Branch", backref="roles")
    permissions = db.relationship("RolePermission", backref="role", lazy="dynamic")

    def __repr__(self):
        return f"<Role {self.name}>"


# ── Permission ────────────────────────────────────────────────────────────────

class Permission(db.Model):
    """
    Granular permissions. Format: module.action
    Examples: patients.view, patients.create, billing.edit, reports.export
    """
    __tablename__ = "permissions"

    id          = db.Column(db.Integer, primary_key=True)
    module      = db.Column(db.String(50), nullable=False)    # e.g. patients
    action      = db.Column(db.String(50), nullable=False)    # e.g. view, create, edit, delete, export
    label       = db.Column(db.String(150))
    description = db.Column(db.String(255))

    __table_args__ = (db.UniqueConstraint("module", "action", name="uq_permission"),)

    def __repr__(self):
        return f"<Permission {self.module}.{self.action}>"


class RolePermission(db.Model):
    """Maps permissions to roles."""
    __tablename__ = "role_permissions"

    id            = db.Column(db.Integer, primary_key=True)
    role_id       = db.Column(db.Integer, db.ForeignKey("roles.id"), nullable=False)
    permission_id = db.Column(db.Integer, db.ForeignKey("permissions.id"), nullable=False)
    granted_by    = db.Column(db.Integer, db.ForeignKey("users.id"))
    granted_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    permission = db.relationship("Permission", backref="role_permissions")

    __table_args__ = (db.UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),)


# ── User ──────────────────────────────────────────────────────────────────────

class User(UserMixin, db.Model):
    """
    Application user. Can be assigned to one or more branches.
    Password is bcrypt-hashed. Sensitive fields are never stored plain.
    """
    __tablename__ = "users"

    id               = db.Column(db.Integer, primary_key=True)
    branch_id        = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=True)  # NULL = SuperAdmin
    role_id          = db.Column(db.Integer, db.ForeignKey("roles.id"), nullable=False)
    employee_id      = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=True)  # linked staff record

    username         = db.Column(db.String(80), unique=True, nullable=False)
    email            = db.Column(db.String(120), unique=True, nullable=False)
    password_hash    = db.Column(db.String(255), nullable=False)
    full_name        = db.Column(db.String(150), nullable=False)
    full_name_ta     = db.Column(db.String(150))
    phone            = db.Column(db.String(20))
    profile_photo    = db.Column(db.String(255))
    preferred_lang   = db.Column(db.String(5), default="en")  # en or ta

    # Account state
    is_active        = db.Column(db.Boolean, default=True, nullable=False)
    is_deleted       = db.Column(db.Boolean, default=False, nullable=False)
    is_superadmin    = db.Column(db.Boolean, default=False, nullable=False)

    # Security
    login_attempts   = db.Column(db.Integer, default=0)
    locked_until     = db.Column(db.DateTime, nullable=True)
    last_login       = db.Column(db.DateTime, nullable=True)
    last_login_ip    = db.Column(db.String(45))  # IPv6 max length
    must_change_pwd  = db.Column(db.Boolean, default=False)  # force password change on first login
    pwd_changed_at   = db.Column(db.DateTime)

    created_at       = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at       = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                                 onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    branch           = db.relationship("Branch", backref="users")
    role             = db.relationship("Role", backref="users")
    sessions         = db.relationship("UserSession", backref="user", lazy="dynamic")
    password_history = db.relationship("PasswordHistory", backref="user", lazy="dynamic")

    # ── Password methods ──────────────────────────────────────────────────

    def set_password(self, password: str):
        self.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")
        self.pwd_changed_at = datetime.now(timezone.utc)

    def check_password(self, password: str) -> bool:
        return bcrypt.check_password_hash(self.password_hash, password)

    def is_locked(self) -> bool:
        if self.locked_until and self.locked_until > datetime.now(timezone.utc):
            return True
        return False

    # ── Permission check ──────────────────────────────────────────────────

    def has_permission(self, module: str, action: str) -> bool:
        """Check if this user's role grants the given permission."""
        if self.is_superadmin:
            return True
        return db.session.query(RolePermission).join(Permission).filter(
            RolePermission.role_id == self.role_id,
            Permission.module == module,
            Permission.action == action,
        ).first() is not None

    def __repr__(self):
        return f"<User {self.username}>"


# ── User Session ──────────────────────────────────────────────────────────────

class UserSession(db.Model):
    """Tracks active sessions per user. Used for concurrent session control and audit."""
    __tablename__ = "user_sessions"

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    session_token = db.Column(db.String(255), unique=True, nullable=False)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(255))
    branch_id  = db.Column(db.Integer, db.ForeignKey("branches.id"))
    login_at   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    logout_at  = db.Column(db.DateTime, nullable=True)
    is_active  = db.Column(db.Boolean, default=True)


# ── Password History ──────────────────────────────────────────────────────────

class PasswordHistory(db.Model):
    """
    Stores last 5 password hashes per user.
    Prevents reuse of recent passwords — required for compliance.
    """
    __tablename__ = "password_history"

    id            = db.Column(db.Integer, primary_key=True)
    user_id       = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    changed_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


# ── Audit Log ─────────────────────────────────────────────────────────────────

class AuditLog(db.Model):
    """
    Immutable audit trail. Every data-changing action is logged here.
    Required by DISHA / IT Act. Records are NEVER deleted.
    """
    __tablename__ = "audit_logs"

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    branch_id   = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=True)
    action      = db.Column(db.String(50), nullable=False)   # CREATE, UPDATE, DELETE, LOGIN, EXPORT
    module      = db.Column(db.String(50))                   # patients, billing, etc.
    record_id   = db.Column(db.Integer)                      # ID of affected record
    record_type = db.Column(db.String(100))                  # Model class name
    old_value   = db.Column(db.Text)                         # JSON of previous state
    new_value   = db.Column(db.Text)                         # JSON of new state
    ip_address  = db.Column(db.String(45))
    user_agent  = db.Column(db.String(255))
    timestamp   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    notes       = db.Column(db.Text)

    user   = db.relationship("User", backref="audit_logs")
    branch = db.relationship("Branch", backref="audit_logs")

    def __repr__(self):
        return f"<AuditLog {self.action} {self.module} by user {self.user_id}>"
