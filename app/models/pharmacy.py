# Revive - app/models/pharmacy.py
# Pharmacy: Drug master, categories, suppliers, purchase orders,
# GRN (Goods Received Note), stock ledger, dispensing.

from datetime import datetime, timezone
from app.extensions import db


class DrugCategory(db.Model):
    __tablename__ = "drug_categories"
    id         = db.Column(db.Integer, primary_key=True)
    branch_id  = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    name       = db.Column(db.String(100), nullable=False)
    name_ta    = db.Column(db.String(100))
    is_active  = db.Column(db.Boolean, default=True)
    is_deleted = db.Column(db.Boolean, default=False)


class DrugMaster(db.Model):
    """
    Drug/medicine master record. One entry per drug per branch.
    Tracks multiple units (tablet, strip, bottle) via unit_of_measure.
    """
    __tablename__ = "drug_master"

    id                = db.Column(db.Integer, primary_key=True)
    branch_id         = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    category_id       = db.Column(db.Integer, db.ForeignKey("drug_categories.id"))
    drug_code         = db.Column(db.String(30))
    generic_name      = db.Column(db.String(255), nullable=False)
    brand_name        = db.Column(db.String(255))
    composition       = db.Column(db.String(500))   # active ingredients
    strength          = db.Column(db.String(100))   # 500mg, 5mg/5ml
    form              = db.Column(db.String(50))    # tablet, capsule, syrup, injection, etc.
    unit_of_measure   = db.Column(db.String(30))    # tablet, ml, strip
    unit_per_pack     = db.Column(db.Integer, default=1)
    schedule          = db.Column(db.String(10))    # H, H1, X, OTC (India drug schedule)
    hsn_code          = db.Column(db.String(20))    # for GST
    gst_percent       = db.Column(db.Numeric(5, 2), default=12)
    reorder_level     = db.Column(db.Integer, default=10)
    current_stock     = db.Column(db.Integer, default=0)   # updated by stock ledger triggers
    mrp               = db.Column(db.Numeric(10, 2))
    purchase_rate     = db.Column(db.Numeric(10, 2))
    sale_rate         = db.Column(db.Numeric(10, 2))
    is_active         = db.Column(db.Boolean, default=True)
    is_deleted        = db.Column(db.Boolean, default=False)
    created_at        = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    branch   = db.relationship("Branch", backref="drugs")
    category = db.relationship("DrugCategory", backref="drugs")

    def __repr__(self):
        return f"<Drug {self.drug_code}: {self.generic_name}>"


class Supplier(db.Model):
    """Pharma suppliers / distributors."""
    __tablename__ = "suppliers"

    id           = db.Column(db.Integer, primary_key=True)
    branch_id    = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    supplier_code = db.Column(db.String(20))
    name         = db.Column(db.String(200), nullable=False)
    contact_name = db.Column(db.String(150))
    phone        = db.Column(db.String(20))
    email        = db.Column(db.String(120))
    address      = db.Column(db.Text)
    gstin        = db.Column(db.String(20))
    drug_license = db.Column(db.String(50))
    payment_terms = db.Column(db.String(100))
    is_active    = db.Column(db.Boolean, default=True)
    is_deleted   = db.Column(db.Boolean, default=False)
    created_at   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class PurchaseOrder(db.Model):
    """Purchase order header raised to a supplier."""
    __tablename__ = "purchase_orders"

    id             = db.Column(db.Integer, primary_key=True)
    branch_id      = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    supplier_id    = db.Column(db.Integer, db.ForeignKey("suppliers.id"), nullable=False)
    po_number      = db.Column(db.String(30), unique=True, nullable=False)
    po_date        = db.Column(db.Date, nullable=False)
    expected_date  = db.Column(db.Date)
    status         = db.Column(db.String(30), default="draft")
    # status: draft, sent, partial, received, cancelled
    subtotal       = db.Column(db.Numeric(12, 2), default=0)
    gst_amount     = db.Column(db.Numeric(12, 2), default=0)
    total_amount   = db.Column(db.Numeric(12, 2), default=0)
    notes          = db.Column(db.Text)
    created_by     = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at     = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_deleted     = db.Column(db.Boolean, default=False)

    supplier = db.relationship("Supplier", backref="purchase_orders")
    items    = db.relationship("POItem", backref="po", lazy="dynamic")


class POItem(db.Model):
    """Individual drug line item in a purchase order."""
    __tablename__ = "po_items"

    id           = db.Column(db.Integer, primary_key=True)
    po_id        = db.Column(db.Integer, db.ForeignKey("purchase_orders.id"), nullable=False)
    drug_id      = db.Column(db.Integer, db.ForeignKey("drug_master.id"), nullable=False)
    qty_ordered  = db.Column(db.Integer, nullable=False)
    qty_received = db.Column(db.Integer, default=0)
    unit_rate    = db.Column(db.Numeric(10, 2))
    gst_percent  = db.Column(db.Numeric(5, 2), default=12)
    total        = db.Column(db.Numeric(12, 2))
    is_deleted   = db.Column(db.Boolean, default=False)

    drug = db.relationship("DrugMaster", backref="po_items")


class GRN(db.Model):
    """Goods Received Note — records actual stock received against a PO."""
    __tablename__ = "grn"

    id            = db.Column(db.Integer, primary_key=True)
    branch_id     = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    po_id         = db.Column(db.Integer, db.ForeignKey("purchase_orders.id"), nullable=True)
    supplier_id   = db.Column(db.Integer, db.ForeignKey("suppliers.id"), nullable=False)
    grn_number    = db.Column(db.String(30), unique=True, nullable=False)
    grn_date      = db.Column(db.Date, nullable=False)
    invoice_number = db.Column(db.String(100))
    invoice_date  = db.Column(db.Date)
    subtotal      = db.Column(db.Numeric(12, 2), default=0)
    gst_amount    = db.Column(db.Numeric(12, 2), default=0)
    total_amount  = db.Column(db.Numeric(12, 2), default=0)
    notes         = db.Column(db.Text)
    received_by   = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_deleted    = db.Column(db.Boolean, default=False)

    received = db.relationship("User", foreign_keys=[received_by])
    items = db.relationship("GRNItem", backref="grn", lazy="dynamic")


class GRNItem(db.Model):
    """Individual drug received in a GRN entry."""
    __tablename__ = "grn_items"

    id           = db.Column(db.Integer, primary_key=True)
    grn_id       = db.Column(db.Integer, db.ForeignKey("grn.id"), nullable=False)
    drug_id      = db.Column(db.Integer, db.ForeignKey("drug_master.id"), nullable=False)
    batch_number = db.Column(db.String(50))
    expiry_date  = db.Column(db.Date)
    qty_received = db.Column(db.Integer, nullable=False)
    free_qty     = db.Column(db.Integer, default=0)
    purchase_rate = db.Column(db.Numeric(10, 2))
    mrp          = db.Column(db.Numeric(10, 2))
    gst_percent  = db.Column(db.Numeric(5, 2), default=12)
    total        = db.Column(db.Numeric(12, 2))
    is_deleted   = db.Column(db.Boolean, default=False)

    drug = db.relationship("DrugMaster", backref="grn_items")


class StockLedger(db.Model):
    """
    Every stock movement is recorded here.
    IN: purchase (GRN), return from dispensing
    OUT: dispensing, expiry write-off, damage
    """
    __tablename__ = "stock_ledger"

    id             = db.Column(db.Integer, primary_key=True)
    branch_id      = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    drug_id        = db.Column(db.Integer, db.ForeignKey("drug_master.id"), nullable=False)
    batch_number   = db.Column(db.String(50))
    expiry_date    = db.Column(db.Date)
    transaction_type = db.Column(db.String(30))  # grn, dispensing, return, write_off
    reference_id   = db.Column(db.Integer)        # id of source record (grn_item or dispensing_item)
    reference_type = db.Column(db.String(50))     # GRNItem, DispensingItem
    qty_in         = db.Column(db.Integer, default=0)
    qty_out        = db.Column(db.Integer, default=0)
    balance        = db.Column(db.Integer)         # running balance
    rate           = db.Column(db.Numeric(10, 2))
    notes          = db.Column(db.String(255))
    created_by     = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at     = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class Dispensing(db.Model):
    """Dispensing record header. Items linked via DispensingItem."""
    __tablename__ = "dispensing"

    id              = db.Column(db.Integer, primary_key=True)
    branch_id       = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    patient_id      = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    prescription_id = db.Column(db.Integer, db.ForeignKey("prescriptions.id"), nullable=True)
    dispense_number = db.Column(db.String(30), unique=True)
    dispensed_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    dispensed_by    = db.Column(db.Integer, db.ForeignKey("users.id"))
    total_amount    = db.Column(db.Numeric(12, 2), default=0)
    discount_amount = db.Column(db.Numeric(10, 2), default=0)
    net_amount      = db.Column(db.Numeric(12, 2), default=0)
    is_billed       = db.Column(db.Boolean, default=False)
    is_deleted      = db.Column(db.Boolean, default=False)

    items = db.relationship("DispensingItem", backref="dispensing", lazy="dynamic")


class DispensingItem(db.Model):
    """Individual drug dispensed in a dispensing transaction."""
    __tablename__ = "dispensing_items"

    id             = db.Column(db.Integer, primary_key=True)
    dispensing_id  = db.Column(db.Integer, db.ForeignKey("dispensing.id"), nullable=False)
    drug_id        = db.Column(db.Integer, db.ForeignKey("drug_master.id"), nullable=False)
    batch_number   = db.Column(db.String(50))
    expiry_date    = db.Column(db.Date)
    qty            = db.Column(db.Integer, nullable=False)
    rate           = db.Column(db.Numeric(10, 2))
    gst_percent    = db.Column(db.Numeric(5, 2), default=0)
    amount         = db.Column(db.Numeric(12, 2))
    is_deleted     = db.Column(db.Boolean, default=False)

    drug = db.relationship("DrugMaster", backref="dispensing_items")
