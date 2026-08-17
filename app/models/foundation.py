# Revive - app/models/foundation.py
# Foundation tables: Branches, Departments, Designations, SystemSettings, EmailTemplates
# These are the root reference tables that everything else depends on.

from app.extensions import db
from app.models.base import BaseModel


class Branch(db.Model):
    """
    Multi-branch support. Every record in the system is scoped to a branch.
    SuperAdmin sees all branches. BranchAdmin sees only their own.
    """
    __tablename__ = "branches"

    id            = db.Column(db.Integer, primary_key=True)
    code          = db.Column(db.String(20), unique=True, nullable=False)   # e.g. BR001
    name          = db.Column(db.String(150), nullable=False)
    name_ta       = db.Column(db.String(150))                                # Tamil name
    address       = db.Column(db.Text)
    city          = db.Column(db.String(100))
    state         = db.Column(db.String(100), default="Tamil Nadu")
    pincode       = db.Column(db.String(10))
    phone         = db.Column(db.String(20))
    email         = db.Column(db.String(120))
    gstin         = db.Column(db.String(20))                                 # GST number
    reg_number    = db.Column(db.String(50))                                 # Clinic reg number
    logo_path     = db.Column(db.String(255))                                # Branch logo
    theme_primary = db.Column(db.String(10), default="#0d6efd")              # CSS hex color
    theme_accent  = db.Column(db.String(10), default="#198754")
    is_active     = db.Column(db.Boolean, default=True, nullable=False)
    is_deleted    = db.Column(db.Boolean, default=False)
    created_at    = db.Column(db.DateTime)
    updated_at    = db.Column(db.DateTime)

    def __repr__(self):
        return f"<Branch {self.code}: {self.name}>"


class Department(db.Model):
    """Clinical and administrative departments within a branch."""
    __tablename__ = "departments"

    id         = db.Column(db.Integer, primary_key=True)
    branch_id  = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    code       = db.Column(db.String(20), nullable=False)
    name       = db.Column(db.String(100), nullable=False)
    name_ta    = db.Column(db.String(100))
    dept_type  = db.Column(db.String(50))   # clinical, admin, support
    head_id    = db.Column(db.Integer)       # FK to employees (set after employees table exists)
    is_active  = db.Column(db.Boolean, default=True)
    is_deleted = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime)

    branch = db.relationship("Branch", backref="departments")

    def __repr__(self):
        return f"<Department {self.code}: {self.name}>"


class Designation(db.Model):
    """Job titles / designations used in HR."""
    __tablename__ = "designations"

    id         = db.Column(db.Integer, primary_key=True)
    branch_id  = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    name       = db.Column(db.String(100), nullable=False)
    name_ta    = db.Column(db.String(100))
    is_active  = db.Column(db.Boolean, default=True)
    is_deleted = db.Column(db.Boolean, default=False)

    branch = db.relationship("Branch", backref="designations")


class SystemSetting(db.Model):
    """
    Key-value store for per-branch system configuration.
    Examples: date_format, currency, default_language, appointment_slot_duration.
    """
    __tablename__ = "system_settings"

    id         = db.Column(db.Integer, primary_key=True)
    branch_id  = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=True)  # NULL = global
    key        = db.Column(db.String(100), nullable=False)
    value      = db.Column(db.Text)
    label      = db.Column(db.String(200))     # Human readable label
    setting_group = db.Column(db.String(50))   # group: general, billing, lab, etc.
    is_public  = db.Column(db.Boolean, default=False)  # visible to non-admin
    updated_at = db.Column(db.DateTime)

    branch = db.relationship("Branch", backref="settings")

    __table_args__ = (db.UniqueConstraint("branch_id", "key", name="uq_branch_setting"),)

    @staticmethod
    def get(key, branch_id=None, default=None):
        """Convenience: fetch a setting value by key."""
        q = SystemSetting.query.filter_by(key=key, is_deleted=False if hasattr(SystemSetting, "is_deleted") else True)
        if branch_id:
            setting = q.filter_by(branch_id=branch_id).first()
            if setting:
                return setting.value
        # Fall back to global setting
        setting = q.filter_by(branch_id=None).first()
        return setting.value if setting else default


class EmailTemplate(db.Model):
    """
    Email templates with variable substitution.
    Variables wrapped in {{double_braces}} are replaced at send time.
    """
    __tablename__ = "email_templates"

    id          = db.Column(db.Integer, primary_key=True)
    branch_id   = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=True)
    template_key = db.Column(db.String(100), nullable=False)  # e.g. appointment_confirm
    subject     = db.Column(db.String(255), nullable=False)
    body_html   = db.Column(db.Text, nullable=False)
    body_text   = db.Column(db.Text)   # plain text fallback
    variables   = db.Column(db.Text)   # JSON list of available variables
    is_active   = db.Column(db.Boolean, default=True)
    is_deleted  = db.Column(db.Boolean, default=False)
    updated_at  = db.Column(db.DateTime)

    branch = db.relationship("Branch", backref="email_templates")
