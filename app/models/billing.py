# Revive - app/models/billing.py
# Billing: Bill master, bill items, payments, receipts, credit notes,
# insurance claims, TPA master. All monetary values in INR (Decimal 12,2).

from datetime import datetime, timezone
from app.extensions import db


class TPAMaster(db.Model):
    """Third Party Administrator (insurance companies, government schemes)."""
    __tablename__ = "tpa_master"

    id           = db.Column(db.Integer, primary_key=True)
    branch_id    = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=True)  # NULL = global
    code         = db.Column(db.String(20))
    name         = db.Column(db.String(200), nullable=False)
    type         = db.Column(db.String(30))   # tpa, insurance, govt_scheme
    contact_name = db.Column(db.String(150))
    phone        = db.Column(db.String(20))
    email        = db.Column(db.String(120))
    address      = db.Column(db.Text)
    claim_email  = db.Column(db.String(120))
    portal_url   = db.Column(db.String(255))
    is_active    = db.Column(db.Boolean, default=True)
    is_deleted   = db.Column(db.Boolean, default=False)


class BillMaster(db.Model):
    """
    Bill header. One bill per patient visit/admission.
    Bill type determines which items are included.
    Bill number is auto-generated: BR001-B-2024-000001.
    """
    __tablename__ = "bill_master"

    id              = db.Column(db.Integer, primary_key=True)
    branch_id       = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    patient_id      = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    bill_number     = db.Column(db.String(40), unique=True, nullable=False)
    bill_date       = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    bill_type       = db.Column(db.String(30))   # opd, ipd, pharmacy, lab, radiology
    visit_id        = db.Column(db.Integer)       # appointment_id or admission_id
    visit_type      = db.Column(db.String(30))    # Appointment or Admission

    # Amounts
    subtotal        = db.Column(db.Numeric(12, 2), default=0)
    discount_percent = db.Column(db.Numeric(5, 2), default=0)
    discount_amount = db.Column(db.Numeric(12, 2), default=0)
    gst_amount      = db.Column(db.Numeric(12, 2), default=0)
    gross_total     = db.Column(db.Numeric(12, 2), default=0)
    paid_amount     = db.Column(db.Numeric(12, 2), default=0)
    balance_amount  = db.Column(db.Numeric(12, 2), default=0)
    credit_amount   = db.Column(db.Numeric(12, 2), default=0)   # insurance credit

    # Status
    status          = db.Column(db.String(30), default="draft")
    # status: draft, generated, partial, paid, credit, cancelled

    # Insurance
    insurance_id    = db.Column(db.Integer, db.ForeignKey("patient_insurance.id"), nullable=True)
    tpa_id          = db.Column(db.Integer, db.ForeignKey("tpa_master.id"), nullable=True)
    pre_auth_number = db.Column(db.String(100))

    notes           = db.Column(db.Text)
    created_by      = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at      = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at      = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                                onupdate=lambda: datetime.now(timezone.utc))
    is_deleted      = db.Column(db.Boolean, default=False)

    patient  = db.relationship("Patient", backref="bills")
    branch   = db.relationship("Branch", backref="bills")
    items    = db.relationship("BillItem", backref="bill", lazy="dynamic")
    payments = db.relationship("Payment", backref="bill", lazy="dynamic")

    def __repr__(self):
        return f"<Bill {self.bill_number}: ₹{self.gross_total}>"


class BillItem(db.Model):
    """Line item within a bill. Can reference any service type."""
    __tablename__ = "bill_items"

    id           = db.Column(db.Integer, primary_key=True)
    bill_id      = db.Column(db.Integer, db.ForeignKey("bill_master.id"), nullable=False)
    item_type    = db.Column(db.String(50))    # consultation, procedure, bed, drug, test, radiology
    item_id      = db.Column(db.Integer)        # ID in the respective table
    description  = db.Column(db.String(255), nullable=False)
    quantity     = db.Column(db.Numeric(10, 3), default=1)
    unit_rate    = db.Column(db.Numeric(12, 2), nullable=False)
    discount_pct = db.Column(db.Numeric(5, 2), default=0)
    gst_percent  = db.Column(db.Numeric(5, 2), default=0)
    gst_amount   = db.Column(db.Numeric(12, 2), default=0)
    amount       = db.Column(db.Numeric(12, 2), nullable=False)
    is_deleted   = db.Column(db.Boolean, default=False)


class Payment(db.Model):
    """Payment transaction against a bill. Multiple payments allowed per bill."""
    __tablename__ = "payments"

    id             = db.Column(db.Integer, primary_key=True)
    branch_id      = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    bill_id        = db.Column(db.Integer, db.ForeignKey("bill_master.id"), nullable=False)
    patient_id     = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    payment_mode   = db.Column(db.String(30), nullable=False)
    # modes: cash, upi, card, cheque, neft, insurance, advance_adjustment
    amount         = db.Column(db.Numeric(12, 2), nullable=False)
    reference_no   = db.Column(db.String(100))   # UPI ref, cheque no, etc.
    paid_at        = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    received_by    = db.Column(db.Integer, db.ForeignKey("users.id"))
    remarks        = db.Column(db.String(255))
    is_refunded    = db.Column(db.Boolean, default=False)
    refund_at      = db.Column(db.DateTime, nullable=True)
    is_deleted     = db.Column(db.Boolean, default=False)


class Receipt(db.Model):
    """Official payment receipt linked to one or more payments."""
    __tablename__ = "receipts"

    id             = db.Column(db.Integer, primary_key=True)
    branch_id      = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    bill_id        = db.Column(db.Integer, db.ForeignKey("bill_master.id"), nullable=False)
    receipt_number = db.Column(db.String(40), unique=True, nullable=False)
    receipt_date   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    total_amount   = db.Column(db.Numeric(12, 2), nullable=False)
    generated_by   = db.Column(db.Integer, db.ForeignKey("users.id"))
    is_cancelled   = db.Column(db.Boolean, default=False)
    cancel_reason  = db.Column(db.String(255))
    is_deleted     = db.Column(db.Boolean, default=False)


class CreditNote(db.Model):
    """Credit note issued for bill adjustments or partial refunds."""
    __tablename__ = "credit_notes"

    id             = db.Column(db.Integer, primary_key=True)
    branch_id      = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    bill_id        = db.Column(db.Integer, db.ForeignKey("bill_master.id"), nullable=False)
    cn_number      = db.Column(db.String(40), unique=True, nullable=False)
    cn_date        = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    amount         = db.Column(db.Numeric(12, 2), nullable=False)
    reason         = db.Column(db.Text)
    issued_by      = db.Column(db.Integer, db.ForeignKey("users.id"))
    is_deleted     = db.Column(db.Boolean, default=False)


class InsuranceClaim(db.Model):
    """Insurance claim tracking per bill."""
    __tablename__ = "insurance_claims"

    id              = db.Column(db.Integer, primary_key=True)
    branch_id       = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    bill_id         = db.Column(db.Integer, db.ForeignKey("bill_master.id"), nullable=False)
    patient_id      = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    tpa_id          = db.Column(db.Integer, db.ForeignKey("tpa_master.id"), nullable=False)
    claim_number    = db.Column(db.String(100))
    submitted_at    = db.Column(db.DateTime)
    claimed_amount  = db.Column(db.Numeric(12, 2))
    approved_amount = db.Column(db.Numeric(12, 2), nullable=True)
    settled_amount  = db.Column(db.Numeric(12, 2), nullable=True)
    settled_at      = db.Column(db.DateTime, nullable=True)
    status          = db.Column(db.String(30), default="pending")
    # status: pending, submitted, under_review, approved, rejected, settled, partial
    rejection_reason = db.Column(db.Text)
    notes           = db.Column(db.Text)
    is_deleted      = db.Column(db.Boolean, default=False)
    created_at      = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
