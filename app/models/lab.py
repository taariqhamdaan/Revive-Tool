# Rivive SCH - app/models/lab.py  v4.2
# Lab: LabCategory, TestMaster, TestPanel, LabOrder, LabOrderItem,
#       SampleCollection, LabResult, LabApproval

from datetime import datetime, timezone, date
from app.extensions import db


class LabCategory(db.Model):
    __tablename__ = "lab_categories"
    id        = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    name      = db.Column(db.String(100), nullable=False)
    code      = db.Column(db.String(20))
    is_active = db.Column(db.Boolean, default=True)
    branch    = db.relationship("Branch", backref="lab_categories")


class TestMaster(db.Model):
    """
    Lab test definition.
    Reference ranges stored as individual columns for direct querying.
    age_ranges stores JSON for paediatric/geriatric variants.
    Auto-flagging: critical_low/high trigger CRITICAL; normal_low/high trigger H/L.
    """
    __tablename__ = "test_master"
    id                = db.Column(db.Integer, primary_key=True)
    branch_id         = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    category_id       = db.Column(db.Integer, db.ForeignKey("lab_categories.id"), nullable=True)

    # Identity
    test_code         = db.Column(db.String(30), index=True)
    test_name         = db.Column(db.String(255), nullable=False, index=True)
    test_short_name   = db.Column(db.String(50))
    department        = db.Column(db.String(100))
    sample_type       = db.Column(db.String(50))   # Blood / Urine / Stool / Swab / CSF
    method            = db.Column(db.String(100))
    instrument        = db.Column(db.String(100))

    # Reference ranges
    unit              = db.Column(db.String(30))
    normal_range      = db.Column(db.String(100))   # display string e.g. "70-110"
    normal_range_text = db.Column(db.String(255))   # for non-numeric e.g. "Negative"
    male_range        = db.Column(db.String(100))
    female_range      = db.Column(db.String(100))
    age_ranges        = db.Column(db.Text)           # JSON array

    # Numeric limits for auto-flagging
    normal_low        = db.Column(db.Numeric(14, 4), nullable=True)
    normal_high       = db.Column(db.Numeric(14, 4), nullable=True)
    critical_low      = db.Column(db.Numeric(14, 4), nullable=True)
    critical_high     = db.Column(db.Numeric(14, 4), nullable=True)

    # Pricing & TAT
    price             = db.Column(db.Numeric(10, 2), default=0)
    gst_percent       = db.Column(db.Numeric(5, 2), default=0)
    turnaround_hrs    = db.Column(db.Integer, default=24)
    print_note        = db.Column(db.Text)

    is_active         = db.Column(db.Boolean, default=True)
    is_deleted        = db.Column(db.Boolean, default=False)
    created_by        = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at        = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at        = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                                   onupdate=lambda: datetime.now(timezone.utc))

    branch   = db.relationship("Branch", backref="test_masters")
    category = db.relationship("LabCategory", backref="tests")

    def __repr__(self):
        return f"<Test {self.test_code}: {self.test_name}>"


class LabOrder(db.Model):
    """
    Stage 1 — Patient details + test selection + payment link.
    status flow: ordered → sample_collected → resulted → approved
    """
    __tablename__ = "lab_orders"
    id             = db.Column(db.Integer, primary_key=True)
    branch_id      = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    patient_id     = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    doctor_id      = db.Column(db.Integer, db.ForeignKey("doctors.id"), nullable=True)
    bill_id        = db.Column(db.Integer, db.ForeignKey("bills.id"), nullable=True)
    ordered_by     = db.Column(db.Integer, db.ForeignKey("users.id"))

    order_number   = db.Column(db.String(30), unique=True, index=True)
    ordered_at     = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    visit_type     = db.Column(db.String(20), default="op")   # op / ip / walkin
    clinical_info  = db.Column(db.Text)
    priority       = db.Column(db.String(20), default="routine")  # routine / urgent / stat

    total_amount   = db.Column(db.Numeric(12, 2), default=0)
    payment_status = db.Column(db.String(20), default="pending")  # pending / paid / credit

    status         = db.Column(db.String(30), default="ordered")
    # ordered → sample_collected → resulted → approved

    is_deleted     = db.Column(db.Boolean, default=False)
    created_at     = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    branch   = db.relationship("Branch",  backref="lab_orders")
    patient  = db.relationship("Patient", backref="lab_orders")
    doctor   = db.relationship("Doctor",  backref="lab_orders")
    bill     = db.relationship("Bill",    backref="lab_orders")
    items    = db.relationship("LabOrderItem", backref="order",
                                lazy="dynamic", cascade="all, delete-orphan")
    sample   = db.relationship("SampleCollection", backref="order", uselist=False)
    approval = db.relationship("LabApproval",       backref="order", uselist=False)


class LabOrderItem(db.Model):
    """Individual test within an order — one row per test."""
    __tablename__ = "lab_order_items"
    id          = db.Column(db.Integer, primary_key=True)
    order_id    = db.Column(db.Integer, db.ForeignKey("lab_orders.id"), nullable=False)
    test_id     = db.Column(db.Integer, db.ForeignKey("test_master.id"), nullable=False)
    branch_id   = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)

    # Snapshot at time of order
    test_name   = db.Column(db.String(255))
    test_code   = db.Column(db.String(30))
    sample_type = db.Column(db.String(50))
    price       = db.Column(db.Numeric(10, 2), default=0)
    gst_percent = db.Column(db.Numeric(5, 2), default=0)
    gst_amount  = db.Column(db.Numeric(10, 2), default=0)
    total       = db.Column(db.Numeric(10, 2), default=0)

    status      = db.Column(db.String(20), default="pending")
    # pending → collected → resulted → approved
    is_deleted  = db.Column(db.Boolean, default=False)

    test   = db.relationship("TestMaster", backref="order_items")
    result = db.relationship("LabResult",  backref="order_item", uselist=False)


class SampleCollection(db.Model):
    """
    Stage 2 — Phlebotomist assigned + timestamp updated on collection.
    collected_at is set when phlebotomist physically collects the sample.
    """
    __tablename__ = "sample_collections"
    id                 = db.Column(db.Integer, primary_key=True)
    order_id           = db.Column(db.Integer, db.ForeignKey("lab_orders.id"),
                                    nullable=False, unique=True)
    branch_id          = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    phlebotomist_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    collected_at       = db.Column(db.DateTime)   # set on collection
    received_at        = db.Column(db.DateTime)   # set when lab receives
    sample_id          = db.Column(db.String(30)) # barcode / tube label
    collection_notes   = db.Column(db.Text)
    is_fasting         = db.Column(db.Boolean, default=False)
    created_at         = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    phlebotomist = db.relationship("User", foreign_keys=[phlebotomist_id],
                                    backref="samples_collected")

    @property
    def turnaround_minutes(self):
        if not self.collected_at:
            return None
        end = self.received_at or datetime.now(timezone.utc)
        # make both offset-naive for comparison
        ca = self.collected_at.replace(tzinfo=None) if self.collected_at.tzinfo else self.collected_at
        en = end.replace(tzinfo=None) if hasattr(end,'tzinfo') and end.tzinfo else end
        return int((en - ca).total_seconds() / 60)


class LabResult(db.Model):
    """
    Stage 3 — Result values entered by lab technician.
    is_locked = True once report is approved (Stage 4).
    compute_flags() auto-sets is_abnormal / is_critical from TestMaster ranges.
    """
    __tablename__ = "lab_results"
    id             = db.Column(db.Integer, primary_key=True)
    order_item_id  = db.Column(db.Integer, db.ForeignKey("lab_order_items.id"),
                                nullable=False, unique=True)
    order_id       = db.Column(db.Integer, db.ForeignKey("lab_orders.id"), nullable=False)
    branch_id      = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    entered_by     = db.Column(db.Integer, db.ForeignKey("users.id"))

    result_value   = db.Column(db.String(255))
    result_unit    = db.Column(db.String(30))
    reference_range= db.Column(db.String(100))  # snapshot at time of result

    is_abnormal    = db.Column(db.Boolean, default=False)
    is_critical    = db.Column(db.Boolean, default=False)
    abnormal_flag  = db.Column(db.String(10))   # H / L / HH / LL / ABNL
    remarks        = db.Column(db.Text)

    # Locked after approval — cannot edit without superadmin unlock
    is_locked      = db.Column(db.Boolean, default=False)

    resulted_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at     = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                                onupdate=lambda: datetime.now(timezone.utc))

    entered_user = db.relationship("User", backref="lab_results_entered",
                                    foreign_keys=[entered_by])
    order        = db.relationship("LabOrder", backref="results")

    def compute_flags(self, test: TestMaster):
        """Auto-set H/L/HH/LL flags. Called every time a result is saved."""
        try:
            val = float(self.result_value)
        except (TypeError, ValueError):
            self.is_critical = False
            self.is_abnormal = False
            self.abnormal_flag = None
            return

        self.is_critical   = False
        self.is_abnormal   = False
        self.abnormal_flag = None

        if test.critical_low  is not None and val < float(test.critical_low):
            self.is_critical   = True
            self.abnormal_flag = "LL"
        elif test.critical_high is not None and val > float(test.critical_high):
            self.is_critical   = True
            self.abnormal_flag = "HH"
        elif test.normal_low  is not None and val < float(test.normal_low):
            self.is_abnormal   = True
            self.abnormal_flag = "L"
        elif test.normal_high is not None and val > float(test.normal_high):
            self.is_abnormal   = True
            self.abnormal_flag = "H"


class LabApproval(db.Model):
    """
    Stage 4 — Report approved by authorised user → all results locked.
    Only superadmin can unlock (is_unlocked=True) for re-editing.
    """
    __tablename__ = "lab_approvals"
    id            = db.Column(db.Integer, primary_key=True)
    order_id      = db.Column(db.Integer, db.ForeignKey("lab_orders.id"),
                               nullable=False, unique=True)
    branch_id     = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    approved_by   = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    approved_at   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    approver_note = db.Column(db.Text)

    is_unlocked   = db.Column(db.Boolean, default=False)
    unlocked_by   = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    unlocked_at   = db.Column(db.DateTime, nullable=True)
    unlock_reason = db.Column(db.Text)

    approver  = db.relationship("User", foreign_keys=[approved_by],
                                 backref="lab_approvals_given")
    unlocker  = db.relationship("User", foreign_keys=[unlocked_by],
                                 backref="lab_approvals_unlocked")
