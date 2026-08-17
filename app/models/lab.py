# MediCore - app/models/lab.py
# Laboratory: Test master, panels, sample collection, results, report templates.

from datetime import datetime, timezone
from app.extensions import db


class TestCategory(db.Model):
    __tablename__ = "test_categories"
    id         = db.Column(db.Integer, primary_key=True)
    branch_id  = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    name       = db.Column(db.String(100), nullable=False)
    name_ta    = db.Column(db.String(100))
    is_active  = db.Column(db.Boolean, default=True)
    is_deleted = db.Column(db.Boolean, default=False)


class TestMaster(db.Model):
    """Lab test master. Each test has reference ranges by gender/age."""
    __tablename__ = "test_master"

    id             = db.Column(db.Integer, primary_key=True)
    branch_id      = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    category_id    = db.Column(db.Integer, db.ForeignKey("test_categories.id"))
    test_code      = db.Column(db.String(30))
    name           = db.Column(db.String(200), nullable=False)
    name_ta        = db.Column(db.String(200))
    sample_type    = db.Column(db.String(50))    # blood, urine, stool, swab, etc.
    method         = db.Column(db.String(100))
    unit           = db.Column(db.String(50))    # mg/dL, IU/L, etc.
    normal_range   = db.Column(db.String(100))   # e.g. 70-110
    male_range     = db.Column(db.String(100))
    female_range   = db.Column(db.String(100))
    paed_range     = db.Column(db.String(100))
    critical_low   = db.Column(db.Numeric(12, 4))
    critical_high  = db.Column(db.Numeric(12, 4))
    turnaround_hrs = db.Column(db.Integer, default=24)
    price          = db.Column(db.Numeric(10, 2), default=0)
    is_active      = db.Column(db.Boolean, default=True)
    is_deleted     = db.Column(db.Boolean, default=False)
    created_at     = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    category = db.relationship("TestCategory", backref="tests")


class TestPanel(db.Model):
    """
    Panel = group of tests ordered together (e.g. CBC, LFT, RFT).
    Panel price is usually discounted vs individual tests.
    """
    __tablename__ = "test_panels"

    id         = db.Column(db.Integer, primary_key=True)
    branch_id  = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    name       = db.Column(db.String(200), nullable=False)
    name_ta    = db.Column(db.String(200))
    price      = db.Column(db.Numeric(10, 2), default=0)
    is_active  = db.Column(db.Boolean, default=True)
    is_deleted = db.Column(db.Boolean, default=False)
    tests      = db.relationship("TestPanelItem", backref="panel", lazy="dynamic")


class TestPanelItem(db.Model):
    """Tests included in a panel."""
    __tablename__ = "test_panel_items"
    id         = db.Column(db.Integer, primary_key=True)
    panel_id   = db.Column(db.Integer, db.ForeignKey("test_panels.id"), nullable=False)
    test_id    = db.Column(db.Integer, db.ForeignKey("test_master.id"), nullable=False)
    test       = db.relationship("TestMaster")


class LabOrder(db.Model):
    """Lab order header raised for a patient (from OPD/IPD or direct)."""
    __tablename__ = "lab_orders"

    id             = db.Column(db.Integer, primary_key=True)
    branch_id      = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    patient_id     = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    doctor_id      = db.Column(db.Integer, db.ForeignKey("doctors.id"), nullable=True)
    consultation_id = db.Column(db.Integer, db.ForeignKey("consultations.id"), nullable=True)
    admission_id   = db.Column(db.Integer, db.ForeignKey("admissions.id"), nullable=True)
    order_number   = db.Column(db.String(30), unique=True, nullable=False)
    ordered_at     = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    priority       = db.Column(db.String(20), default="routine")  # routine, urgent, stat
    status         = db.Column(db.String(30), default="ordered")
    # status: ordered, sample_collected, processing, resulted, reported, cancelled
    clinical_info  = db.Column(db.Text)
    total_amount   = db.Column(db.Numeric(12, 2), default=0)
    is_billed      = db.Column(db.Boolean, default=False)
    is_deleted     = db.Column(db.Boolean, default=False)

    items   = db.relationship("LabOrderItem", backref="order", lazy="dynamic")
    patient = db.relationship("Patient", backref="lab_orders")


class LabOrderItem(db.Model):
    """Individual test within a lab order."""
    __tablename__ = "lab_order_items"

    id             = db.Column(db.Integer, primary_key=True)
    order_id       = db.Column(db.Integer, db.ForeignKey("lab_orders.id"), nullable=False)
    test_id        = db.Column(db.Integer, db.ForeignKey("test_master.id"), nullable=False)
    panel_id       = db.Column(db.Integer, db.ForeignKey("test_panels.id"), nullable=True)
    sample_barcode = db.Column(db.String(50))
    collected_at   = db.Column(db.DateTime)
    collected_by   = db.Column(db.Integer, db.ForeignKey("users.id"))
    status         = db.Column(db.String(30), default="ordered")
    price          = db.Column(db.Numeric(10, 2), default=0)
    is_deleted     = db.Column(db.Boolean, default=False)

    test    = db.relationship("TestMaster")
    results = db.relationship("LabResult", foreign_keys="LabResult.order_item_id", backref="order_item", lazy="dynamic")


class LabResult(db.Model):
    """Result entry for a single test item in an order."""
    __tablename__ = "lab_results"

    id              = db.Column(db.Integer, primary_key=True)
    order_item_id   = db.Column(db.Integer, db.ForeignKey("lab_order_items.id"), nullable=False)
    order_id        = db.Column(db.Integer, db.ForeignKey("lab_orders.id"), nullable=False)
    patient_id      = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    test_id         = db.Column(db.Integer, db.ForeignKey("test_master.id"), nullable=False)
    result_value    = db.Column(db.String(255))    # numeric or text
    result_unit     = db.Column(db.String(50))
    reference_range = db.Column(db.String(100))
    is_critical     = db.Column(db.Boolean, default=False)
    is_abnormal     = db.Column(db.Boolean, default=False)
    abnormal_flag   = db.Column(db.String(5))      # H, L, HH, LL
    remarks         = db.Column(db.Text)
    resulted_at     = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    resulted_by     = db.Column(db.Integer, db.ForeignKey("users.id"))
    verified_by     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    verified_at     = db.Column(db.DateTime, nullable=True)
    is_deleted      = db.Column(db.Boolean, default=False)
