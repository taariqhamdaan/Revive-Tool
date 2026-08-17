# Revive - app/models/radiology.py
# Radiology: Investigation master, orders, reports.

from datetime import datetime, timezone
from app.extensions import db


class InvestigationMaster(db.Model):
    """Radiology investigation types (X-Ray, USG, CT, MRI, Echo, etc.)"""
    __tablename__ = "investigation_master"

    id           = db.Column(db.Integer, primary_key=True)
    branch_id    = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    code         = db.Column(db.String(30))
    name         = db.Column(db.String(200), nullable=False)
    name_ta      = db.Column(db.String(200))
    category     = db.Column(db.String(50))    # xray, usg, ct, mri, echo, other
    price        = db.Column(db.Numeric(10, 2), default=0)
    preparation  = db.Column(db.Text)          # patient prep instructions
    is_active    = db.Column(db.Boolean, default=True)
    is_deleted   = db.Column(db.Boolean, default=False)


class RadiologyOrder(db.Model):
    """Radiology investigation order for a patient."""
    __tablename__ = "radiology_orders"

    id              = db.Column(db.Integer, primary_key=True)
    branch_id       = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    patient_id      = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    doctor_id       = db.Column(db.Integer, db.ForeignKey("doctors.id"), nullable=True)
    consultation_id = db.Column(db.Integer, db.ForeignKey("consultations.id"), nullable=True)
    admission_id    = db.Column(db.Integer, db.ForeignKey("admissions.id"), nullable=True)
    investigation_id = db.Column(db.Integer, db.ForeignKey("investigation_master.id"), nullable=False)
    order_number    = db.Column(db.String(30), unique=True)
    ordered_at      = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    priority        = db.Column(db.String(20), default="routine")
    clinical_info   = db.Column(db.Text)
    status          = db.Column(db.String(30), default="ordered")
    # status: ordered, in_progress, reported, delivered, cancelled
    price           = db.Column(db.Numeric(10, 2), default=0)
    is_billed       = db.Column(db.Boolean, default=False)
    is_deleted      = db.Column(db.Boolean, default=False)

    patient       = db.relationship("Patient", backref="radiology_orders")
    investigation = db.relationship("InvestigationMaster", backref="orders")


class RadiologyReport(db.Model):
    """Report entered by radiologist for an order."""
    __tablename__ = "radiology_reports"

    id           = db.Column(db.Integer, primary_key=True)
    order_id     = db.Column(db.Integer, db.ForeignKey("radiology_orders.id"), nullable=False, unique=True)
    patient_id   = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    findings     = db.Column(db.Text)
    impression   = db.Column(db.Text)
    image_path   = db.Column(db.String(500))   # path to uploaded image/scan
    reported_by  = db.Column(db.Integer, db.ForeignKey("users.id"))
    reported_at  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    verified_by  = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    verified_at  = db.Column(db.DateTime, nullable=True)
    is_deleted   = db.Column(db.Boolean, default=False)

    order = db.relationship("RadiologyOrder", backref="report", uselist=False)
