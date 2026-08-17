# MediCore - app/models/payroll.py
# Payroll: Salary structure components, payroll run master, payroll line items.
# Supports earnings (Basic, HRA, DA, Allowances) and deductions (PF, ESI, TDS, LOP).

from datetime import datetime, timezone
from app.extensions import db


class SalaryComponent(db.Model):
    """
    Master list of salary components.
    type: earning or deduction
    calc_type: fixed, percentage_of_basic, percentage_of_gross, formula
    """
    __tablename__ = "salary_components"

    id            = db.Column(db.Integer, primary_key=True)
    branch_id     = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=True)   # NULL = global
    code          = db.Column(db.String(20), nullable=False)  # BASIC, HRA, PF, ESI, TDS
    name          = db.Column(db.String(100), nullable=False)
    name_ta       = db.Column(db.String(100))
    type          = db.Column(db.String(20), nullable=False)   # earning, deduction
    calc_type     = db.Column(db.String(30), default="fixed")
    calc_value    = db.Column(db.Numeric(10, 4), default=0)    # % or fixed amount
    is_taxable    = db.Column(db.Boolean, default=False)
    is_pf_applicable = db.Column(db.Boolean, default=False)
    is_esi_applicable = db.Column(db.Boolean, default=False)
    is_active     = db.Column(db.Boolean, default=True)
    is_deleted    = db.Column(db.Boolean, default=False)
    sort_order    = db.Column(db.Integer, default=0)


class SalaryStructure(db.Model):
    """
    Salary structure template assigned to an employee.
    Contains the breakdown of CTC into components.
    """
    __tablename__ = "salary_structures"

    id           = db.Column(db.Integer, primary_key=True)
    branch_id    = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    employee_id  = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    effective_from = db.Column(db.Date, nullable=False)
    effective_to = db.Column(db.Date, nullable=True)
    gross_salary = db.Column(db.Numeric(12, 2), nullable=False)
    ctc          = db.Column(db.Numeric(12, 2))
    is_active    = db.Column(db.Boolean, default=True)
    is_deleted   = db.Column(db.Boolean, default=False)
    created_by   = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    employee   = db.relationship("Employee", backref="salary_structures")
    components = db.relationship("SalaryStructureItem", backref="structure", lazy="dynamic")


class SalaryStructureItem(db.Model):
    """Individual component in a salary structure."""
    __tablename__ = "salary_structure_items"

    id                  = db.Column(db.Integer, primary_key=True)
    structure_id        = db.Column(db.Integer, db.ForeignKey("salary_structures.id"), nullable=False)
    component_id        = db.Column(db.Integer, db.ForeignKey("salary_components.id"), nullable=False)
    amount              = db.Column(db.Numeric(12, 2), nullable=False)   # computed/stored amount
    is_deleted          = db.Column(db.Boolean, default=False)

    component = db.relationship("SalaryComponent")


class PayrollRun(db.Model):
    """
    Payroll processing run for a branch for a specific month.
    One run per branch per month. Status tracks processing stage.
    """
    __tablename__ = "payroll_runs"

    id           = db.Column(db.Integer, primary_key=True)
    branch_id    = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    month        = db.Column(db.Integer, nullable=False)   # 1–12
    year         = db.Column(db.Integer, nullable=False)
    status       = db.Column(db.String(20), default="draft")
    # status: draft, processing, review, approved, paid, locked
    total_gross  = db.Column(db.Numeric(14, 2), default=0)
    total_deductions = db.Column(db.Numeric(14, 2), default=0)
    total_net    = db.Column(db.Numeric(14, 2), default=0)
    employee_count = db.Column(db.Integer, default=0)
    processed_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    processed_at = db.Column(db.DateTime)
    approved_by  = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    approved_at  = db.Column(db.DateTime, nullable=True)
    notes        = db.Column(db.Text)
    is_deleted   = db.Column(db.Boolean, default=False)
    created_at   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (db.UniqueConstraint("branch_id", "month", "year", name="uq_payroll_month"),)

    slips = db.relationship("PaySlip", backref="run", lazy="dynamic")


class PaySlip(db.Model):
    """
    Individual employee pay slip within a payroll run.
    Stores all computed values at time of processing (snapshot — not recalculated later).
    """
    __tablename__ = "pay_slips"

    id               = db.Column(db.Integer, primary_key=True)
    run_id           = db.Column(db.Integer, db.ForeignKey("payroll_runs.id"), nullable=False)
    employee_id      = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    branch_id        = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)

    # Working days
    working_days     = db.Column(db.Integer)
    present_days     = db.Column(db.Numeric(5, 1))
    leave_days       = db.Column(db.Numeric(5, 1), default=0)
    lop_days         = db.Column(db.Numeric(5, 1), default=0)    # Loss of Pay

    # Amounts
    gross_earnings   = db.Column(db.Numeric(12, 2), default=0)
    total_deductions = db.Column(db.Numeric(12, 2), default=0)
    net_salary       = db.Column(db.Numeric(12, 2), default=0)

    # Tax
    tds_amount       = db.Column(db.Numeric(12, 2), default=0)
    pf_employee      = db.Column(db.Numeric(12, 2), default=0)
    pf_employer      = db.Column(db.Numeric(12, 2), default=0)
    esi_employee     = db.Column(db.Numeric(12, 2), default=0)
    esi_employer     = db.Column(db.Numeric(12, 2), default=0)

    # Payment
    payment_mode     = db.Column(db.String(30))    # bank_transfer, cash, cheque
    payment_date     = db.Column(db.Date)
    payment_ref      = db.Column(db.String(100))
    is_paid          = db.Column(db.Boolean, default=False)
    is_deleted       = db.Column(db.Boolean, default=False)

    employee = db.relationship("Employee", backref="pay_slips")
    items    = db.relationship("PaySlipItem", backref="slip", lazy="dynamic")


class PaySlipItem(db.Model):
    """Earnings and deduction line items within a pay slip."""
    __tablename__ = "pay_slip_items"

    id           = db.Column(db.Integer, primary_key=True)
    slip_id      = db.Column(db.Integer, db.ForeignKey("pay_slips.id"), nullable=False)
    component_id = db.Column(db.Integer, db.ForeignKey("salary_components.id"), nullable=False)
    amount       = db.Column(db.Numeric(12, 2), nullable=False)
    is_deleted   = db.Column(db.Boolean, default=False)

    component = db.relationship("SalaryComponent")
