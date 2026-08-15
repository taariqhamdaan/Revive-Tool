from datetime import datetime, timezone
from app.extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

class Branch(db.Model):
    __tablename__ = "branches"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    address = db.Column(db.Text)
    phone = db.Column(db.String(20))
    email = db.Column(db.String(150))
    is_active = db.Column(db.Boolean, default=True)
    is_deleted = db.Column(db.Boolean, default=False)

class Role(db.Model):
    __tablename__ = "roles"
    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    branch = db.relationship("Branch", backref="roles")

class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=True)
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"), nullable=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    full_name = db.Column(db.String(150), nullable=False)
    password_hash = db.Column(db.String(255))
    phone = db.Column(db.String(20))
    is_active = db.Column(db.Boolean, default=True)
    is_superadmin = db.Column(db.Boolean, default=False)
    is_deleted = db.Column(db.Boolean, default=False)
    branch = db.relationship("Branch", backref="users")
    role = db.relationship("Role", backref="users")
    def has_permission(self, module, action): return True

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, raw)

class Department(db.Model):
    __tablename__ = "departments"
    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    is_deleted = db.Column(db.Boolean, default=False)
    branch = db.relationship("Branch", backref="departments")

class Patient(db.Model):
    __tablename__ = "patients"
    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    uhid = db.Column(db.String(30), unique=True, index=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100))
    gender = db.Column(db.String(20))
    date_of_birth = db.Column(db.Date)
    age_years = db.Column(db.Integer)
    phone = db.Column(db.String(20), nullable=False, index=True)
    email = db.Column(db.String(150))
    blood_group = db.Column(db.String(5))
    address = db.Column(db.Text)
    city = db.Column(db.String(100))
    abha_number = db.Column(db.String(30))
    is_active = db.Column(db.Boolean, default=True)
    is_deleted = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    branch = db.relationship("Branch", backref="patients")
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name or ''}".strip()

class Bill(db.Model):
    __tablename__ = "bills"
    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey("doctors.id"), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    bill_number = db.Column(db.String(30), unique=True, index=True)
    bill_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    module_type = db.Column(db.String(30), default="op")
    bill_type = db.Column(db.String(20), default="regular")
    billed_from = db.Column(db.String(30), default="lab")
    subtotal = db.Column(db.Numeric(12,2), default=0)
    gross_total = db.Column(db.Numeric(12,2), default=0)
    payable_amount = db.Column(db.Numeric(12,2), default=0)
    paid_amount = db.Column(db.Numeric(12,2), default=0)
    balance_amount = db.Column(db.Numeric(12,2), default=0)
    received_amount = db.Column(db.Numeric(12,2), default=0)
    payment_mode = db.Column(db.String(20))
    status = db.Column(db.String(20), default="draft")
    is_deleted = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    branch = db.relationship("Branch", backref="bills")
    patient = db.relationship("Patient", backref="bills", foreign_keys=[patient_id])

class Doctor(db.Model):
    __tablename__ = "doctors"
    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    doctor_code = db.Column(db.String(20), unique=True)
    title = db.Column(db.String(20))
    full_name = db.Column(db.String(150), nullable=False)
    specialisation = db.Column(db.String(150))
    qualification = db.Column(db.String(255))
    reg_number = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, default=True)
    is_deleted = db.Column(db.Boolean, default=False)
    branch = db.relationship("Branch", backref="doctors")
