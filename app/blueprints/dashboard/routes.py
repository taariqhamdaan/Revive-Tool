# Rivive - app/blueprints/dashboard/routes.py
# Dashboard: main landing page after login.
# Logic summary:
#   - SuperAdmin: sees all-branch aggregated stats
#   - BranchAdmin/others: sees stats for their branch only
#   - Stats: today's appointments, OPD count, admitted patients,
#     bed occupancy, pending lab orders, today's revenue, low stock alerts

from datetime import date, datetime, timezone
from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from sqlalchemy import func
from app.extensions import db

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@dashboard_bp.route("/index")
@login_required
def index():
    branch_id = None if current_user.is_superadmin else current_user.branch_id
    today = date.today()
    stats = _get_dashboard_stats(branch_id, today)
    alerts = _get_alerts(branch_id)
    return render_template("dashboard/index.html", stats=stats, alerts=alerts, today=today)


def _get_dashboard_stats(branch_id, today):
    from app.models.opd import Appointment
    from app.models.ipd import Admission, Bed
    from app.models.lab import LabOrder
    from app.models.billing import Payment
    from app.models.pharmacy import DrugMaster
    from app.models.patients import Patient

    def q_filter(query, model):
        if branch_id:
            return query.filter(model.branch_id == branch_id)
        return query

    # Today appointments
    appt_q = Appointment.query.filter(
        Appointment.appointment_date == today,
        Appointment.is_deleted == False,
    )
    if branch_id:
        appt_q = appt_q.filter(Appointment.branch_id == branch_id)

    # Active admissions
    admit_q = Admission.query.filter(Admission.status == "admitted", Admission.is_deleted == False)
    if branch_id:
        admit_q = admit_q.filter(Admission.branch_id == branch_id)

    # Total beds
    bed_q = Bed.query.filter(Bed.is_active == True, Bed.is_deleted == False)
    if branch_id:
        bed_q = bed_q.filter(Bed.branch_id == branch_id)

    # Pending lab orders
    lab_q = LabOrder.query.filter(
        LabOrder.status.in_(["ordered", "sample_collected", "processing"]),
        LabOrder.is_deleted == False,
    )
    if branch_id:
        lab_q = lab_q.filter(LabOrder.branch_id == branch_id)

    # Today revenue
    rev_q = db.session.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
        func.date(Payment.paid_at) == today,
        Payment.is_deleted == False,
        Payment.is_refunded == False,
    )
    if branch_id:
        rev_q = rev_q.filter(Payment.branch_id == branch_id)

    # Total patients registered
    pat_q = Patient.query.filter(Patient.is_deleted == False)
    if branch_id:
        pat_q = pat_q.filter(Patient.branch_id == branch_id)

    total_beds    = bed_q.count()
    occupied_beds = admit_q.count()

    return {
        "today_appointments": appt_q.count(),
        "opd_completed": appt_q.filter(Appointment.status == "completed").count(),
        "admitted_patients": occupied_beds,
        "total_beds": total_beds,
        "bed_occupancy_pct": round((occupied_beds / total_beds * 100) if total_beds else 0, 1),
        "pending_lab_orders": lab_q.count(),
        "today_revenue": float(rev_q.scalar() or 0),
        "total_patients": pat_q.count(),
    }


def _get_alerts(branch_id):
    from app.models.pharmacy import DrugMaster
    from app.models.lab import LabOrder

    alerts = []

    # Low stock drugs
    low_stock_q = DrugMaster.query.filter(
        DrugMaster.current_stock <= DrugMaster.reorder_level,
        DrugMaster.is_active == True,
        DrugMaster.is_deleted == False,
    )
    if branch_id:
        low_stock_q = low_stock_q.filter(DrugMaster.branch_id == branch_id)
    count = low_stock_q.count()
    if count:
        alerts.append({"type": "warning", "icon": "capsule", "message": f"{count} drug(s) below reorder level", "url": "/pharmacy/stock-alerts"})

    # Expiring drugs (within 90 days)
    from app.models.pharmacy import GRNItem
    from datetime import timedelta
    soon = date.today() + timedelta(days=90)
    exp_q = GRNItem.query.filter(GRNItem.expiry_date <= soon, GRNItem.qty_received > 0, GRNItem.is_deleted == False)
    exp_count = exp_q.count()
    if exp_count:
        alerts.append({"type": "danger", "icon": "exclamation-triangle", "message": f"{exp_count} drug batch(es) expiring within 90 days", "url": "/pharmacy/expiry-alerts"})

    return alerts
