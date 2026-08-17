# Rivive - app/utils/generators.py
# Auto-generation of all system IDs: UHID, IP number, bill number, etc.
# All generators are branch-scoped and zero-padded for consistent sorting.

from datetime import datetime
from app.extensions import db


def generate_uhid(branch_code: str) -> str:
    """
    Generate next UHID for a branch.
    Format: BR001-P-000001
    Thread-safe: uses DB sequence query with row lock.
    """
    from app.models.patients import Patient
    from app.models.foundation import Branch

    last = (
        Patient.query
        .filter(Patient.uhid.like(f"{branch_code}-P-%"), Patient.is_deleted == False)
        .order_by(Patient.id.desc())
        .first()
    )
    if last and last.uhid:
        try:
            seq = int(last.uhid.split("-P-")[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1
    return f"{branch_code}-P-{seq:06d}"


def generate_ip_number(branch_code: str) -> str:
    """
    Generate next IPD admission number.
    Format: BR001-IP-2024-000001 (resets each year)
    """
    from app.models.ipd import Admission

    year = datetime.now().year
    prefix = f"{branch_code}-IP-{year}-"
    last = (
        Admission.query
        .filter(Admission.ip_number.like(f"{prefix}%"))
        .order_by(Admission.id.desc())
        .first()
    )
    if last and last.ip_number:
        try:
            seq = int(last.ip_number.split("-")[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1
    return f"{prefix}{seq:06d}"


def generate_bill_number(branch_code: str, bill_type: str = "B") -> str:
    """
    Generate next bill number.
    Format: BR001-B-2024-000001
    bill_type: B=general, PH=pharmacy, L=lab, R=radiology
    """
    from app.models.billing import BillMaster

    year = datetime.now().year
    prefix = f"{branch_code}-{bill_type}-{year}-"
    last = (
        BillMaster.query
        .filter(BillMaster.bill_number.like(f"{prefix}%"))
        .order_by(BillMaster.id.desc())
        .first()
    )
    seq = 1
    if last and last.bill_number:
        try:
            seq = int(last.bill_number.split("-")[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    return f"{prefix}{seq:06d}"


def generate_receipt_number(branch_code: str) -> str:
    from app.models.billing import Receipt
    year = datetime.now().year
    prefix = f"{branch_code}-REC-{year}-"
    last = Receipt.query.filter(Receipt.receipt_number.like(f"{prefix}%")).order_by(Receipt.id.desc()).first()
    seq = int(last.receipt_number.split("-")[-1]) + 1 if last and last.receipt_number else 1
    return f"{prefix}{seq:06d}"


def generate_order_number(branch_code: str, prefix_code: str) -> str:
    """Generic order number: BR001-LAB-2024-000001 or BR001-RAD-2024-000001"""
    year = datetime.now().year
    prefix = f"{branch_code}-{prefix_code}-{year}-"
    # Count all orders with this prefix from any table using raw query
    from sqlalchemy import text
    result = db.session.execute(
        text(f"SELECT COUNT(*) FROM lab_orders WHERE order_number LIKE :p")
        if prefix_code == "LAB" else
        text(f"SELECT COUNT(*) FROM radiology_orders WHERE order_number LIKE :p"),
        {"p": f"{prefix}%"}
    ).scalar()
    return f"{prefix}{(result or 0) + 1:06d}"


def generate_rx_number(branch_code: str) -> str:
    from app.models.opd import Prescription
    year = datetime.now().year
    prefix = f"{branch_code}-RX-{year}-"
    last = Prescription.query.filter(Prescription.rx_number.like(f"{prefix}%")).order_by(Prescription.id.desc()).first()
    seq = int(last.rx_number.split("-")[-1]) + 1 if last and last.rx_number else 1
    return f"{prefix}{seq:06d}"


def generate_grn_number(branch_code: str) -> str:
    from app.models.pharmacy import GRN
    year = datetime.now().year
    prefix = f"{branch_code}-GRN-{year}-"
    last = GRN.query.filter(GRN.grn_number.like(f"{prefix}%")).order_by(GRN.id.desc()).first()
    seq = int(last.grn_number.split("-")[-1]) + 1 if last and last.grn_number else 1
    return f"{prefix}{seq:06d}"


def generate_po_number(branch_code: str) -> str:
    from app.models.pharmacy import PurchaseOrder
    year = datetime.now().year
    prefix = f"{branch_code}-PO-{year}-"
    last = PurchaseOrder.query.filter(PurchaseOrder.po_number.like(f"{prefix}%")).order_by(PurchaseOrder.id.desc()).first()
    seq = int(last.po_number.split("-")[-1]) + 1 if last and last.po_number else 1
    return f"{prefix}{seq:06d}"


def generate_employee_code(branch_code: str) -> str:
    from app.models.hr import Employee
    prefix = f"{branch_code}-EMP-"
    last = Employee.query.filter(Employee.employee_code.like(f"{prefix}%")).order_by(Employee.id.desc()).first()
    seq = int(last.employee_code.split("-")[-1]) + 1 if last and last.employee_code else 1
    return f"{prefix}{seq:04d}"


def generate_token_number(branch_id: int, appt_date) -> int:
    """Auto-incrementing daily token number per branch."""
    from app.models.opd import Appointment
    from sqlalchemy import func
    max_token = Appointment.query.filter_by(
        branch_id=branch_id, appointment_date=appt_date, is_deleted=False
    ).with_entities(func.max(Appointment.token_number)).scalar()
    return (max_token or 0) + 1
