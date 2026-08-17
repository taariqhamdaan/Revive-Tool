# Revive - app/blueprints/reports/routes.py
# Reports — matches Rivive Hospital PDF spec exactly.
# Sections: OP Service, IP Service, Appointment, Patient, Referral, Insurance
# Each section has sub-reports with date-range filters + Excel/PDF export.

from datetime import date, datetime, timedelta
from flask import (Blueprint, render_template, redirect, url_for,
                   request, flash, send_file, jsonify, current_app)
from flask_login import login_required, current_user
from sqlalchemy import func, text
import io

from app.extensions import db
from app.models.opd import Appointment, Consultation, Doctor, Referral
from app.models.ipd import Admission, DischargeSummary
from app.models.patients import Patient
from app.models.billing import BillMaster, Payment, InsuranceClaim
from app.utils.decorators import require_permission
from app.utils.audit import log_action

reports_bp = Blueprint("reports", __name__)


@reports_bp.route("/")
@login_required
@require_permission("reports", "view")
def index():
    return render_template("reports/index.html")


# ── OP Service Reports ────────────────────────────────────────────────────

@reports_bp.route("/op-service")
@login_required
@require_permission("reports", "view")
def op_service():
    sub      = request.args.get("sub", "detailed")
    df, dt   = _date_range()
    branch_id = current_user.branch_id

    data = []
    if sub == "detailed":
        # OP Service Detailed — all consultations in range
        q = db.session.query(Appointment, Patient, Doctor).join(
            Patient, Patient.id == Appointment.patient_id
        ).join(Doctor, Doctor.id == Appointment.doctor_id).filter(
            Appointment.appointment_date.between(df, dt),
            Appointment.is_deleted == False,
        )
        if branch_id:
            q = q.filter(Appointment.branch_id == branch_id)
        data = q.order_by(Appointment.appointment_date, Appointment.token_number).all()

    elif sub == "overview":
        # Daily count summary
        q = db.session.query(
            Appointment.appointment_date,
            func.count(Appointment.id).label("total"),
            func.sum(db.case((Appointment.status == "completed", 1), else_=0)).label("completed"),
            func.sum(db.case((Appointment.status == "cancelled", 1), else_=0)).label("cancelled"),
            func.sum(db.case((Appointment.visit_type == "new", 1), else_=0)).label("new_pts"),
        ).filter(
            Appointment.appointment_date.between(df, dt),
            Appointment.is_deleted == False,
        )
        if branch_id:
            q = q.filter(Appointment.branch_id == branch_id)
        data = q.group_by(Appointment.appointment_date).order_by(Appointment.appointment_date).all()

    elif sub == "audit":
        from app.models.users import AuditLog
        q = AuditLog.query.filter(
            func.date(AuditLog.timestamp).between(df, dt),
            AuditLog.module == "opd",
        )
        if branch_id:
            q = q.filter(AuditLog.branch_id == branch_id)
        data = q.order_by(AuditLog.timestamp.desc()).limit(500).all()

    elif sub == "consultation_wise":
        q = db.session.query(
            Doctor.full_name, Doctor.specialisation,
            func.count(Appointment.id).label("total"),
            func.sum(db.case((Appointment.status == "completed", 1), else_=0)).label("done"),
        ).join(Appointment, Appointment.doctor_id == Doctor.id).filter(
            Appointment.appointment_date.between(df, dt),
            Appointment.is_deleted == False,
        )
        if branch_id:
            q = q.filter(Appointment.branch_id == branch_id)
        data = q.group_by(Doctor.id).order_by(func.count(Appointment.id).desc()).all()

    return render_template("reports/op_service.html",
                           sub=sub, data=data, date_from=df, date_to=dt)


# ── IP Service Reports ────────────────────────────────────────────────────

@reports_bp.route("/ip-service")
@login_required
@require_permission("reports", "view")
def ip_service():
    sub       = request.args.get("sub", "admission_list")
    df, dt    = _date_range()
    branch_id = current_user.branch_id

    q = Admission.query.filter(
        Admission.is_deleted == False,
    )
    if branch_id:
        q = q.filter(Admission.branch_id == branch_id)

    if sub == "admission_list":
        data = q.filter(func.date(Admission.admission_date).between(df, dt)).order_by(Admission.admission_date.desc()).all()
    elif sub == "discharge_list":
        data = q.filter(Admission.status == "discharged",
                        func.date(Admission.discharge_date).between(df, dt)).order_by(Admission.discharge_date.desc()).all()
    elif sub == "occupancy":
        data = q.filter(Admission.status == "admitted").order_by(Admission.admission_date).all()
    elif sub == "payment_due":
        data = q.filter(Admission.status == "admitted").order_by(Admission.admission_date).all()
    else:
        data = q.order_by(Admission.admission_date.desc()).limit(200).all()

    return render_template("reports/ip_service.html",
                           sub=sub, data=data, date_from=df, date_to=dt)


# ── Appointment Reports ───────────────────────────────────────────────────

@reports_bp.route("/appointments")
@login_required
@require_permission("reports", "view")
def appointments():
    sub       = request.args.get("sub", "patients")
    df, dt    = _date_range()
    branch_id = current_user.branch_id

    q = Appointment.query.filter(
        Appointment.appointment_date.between(df, dt),
        Appointment.is_deleted == False,
    )
    if branch_id:
        q = q.filter(Appointment.branch_id == branch_id)

    if sub == "doctors":
        data = db.session.query(
            Doctor.full_name, Doctor.specialisation,
            func.count(Appointment.id).label("total"),
        ).join(Appointment, Appointment.doctor_id == Doctor.id).filter(
            Appointment.appointment_date.between(df, dt),
            Appointment.is_deleted == False,
        ).group_by(Doctor.id).order_by(func.count(Appointment.id).desc()).all()
    elif sub == "type":
        data = db.session.query(
            Appointment.visit_type,
            func.count(Appointment.id).label("total"),
        ).filter(
            Appointment.appointment_date.between(df, dt),
            Appointment.is_deleted == False,
        ).group_by(Appointment.visit_type).all()
    else:
        data = q.order_by(Appointment.appointment_date.desc(), Appointment.token_number).all()

    return render_template("reports/appointments.html",
                           sub=sub, data=data, date_from=df, date_to=dt)


# ── Patient Reports ───────────────────────────────────────────────────────

@reports_bp.route("/patients")
@login_required
@require_permission("reports", "view")
def patient_report():
    sub       = request.args.get("sub", "demographic")
    df, dt    = _date_range()
    branch_id = current_user.branch_id

    q = Patient.query.filter(Patient.is_deleted == False)
    if branch_id:
        q = q.filter(Patient.branch_id == branch_id)

    if sub == "demographic":
        data = q.filter(func.date(Patient.created_at).between(df, dt)).order_by(Patient.created_at.desc()).all()
    elif sub == "purpose_of_visit":
        data = db.session.query(
            Appointment.reason,
            func.count(Appointment.id).label("count"),
        ).filter(
            Appointment.appointment_date.between(df, dt),
            Appointment.reason != None,
            Appointment.reason != "",
        ).group_by(Appointment.reason).order_by(func.count(Appointment.id).desc()).limit(50).all()
    elif sub == "diagnosis":
        data = db.session.query(
            Consultation.diagnosis,
            func.count(Consultation.id).label("count"),
        ).filter(
            Consultation.is_deleted == False,
            Consultation.diagnosis != None,
        ).group_by(Consultation.diagnosis).order_by(func.count(Consultation.id).desc()).limit(50).all()
    elif sub == "concession":
        data = BillMaster.query.filter(
            BillMaster.discount_amount > 0,
            BillMaster.is_deleted == False,
            func.date(BillMaster.bill_date).between(df, dt),
            *([BillMaster.branch_id == branch_id] if branch_id else []),
        ).order_by(BillMaster.bill_date.desc()).all()
    elif sub == "doctor_consultation":
        data = db.session.query(
            Doctor.full_name.label("doctor"),
            func.count(Consultation.id).label("consultations"),
        ).join(Consultation, Consultation.doctor_id == Doctor.id).filter(
            Consultation.is_deleted == False,
        ).group_by(Doctor.id).order_by(func.count(Consultation.id).desc()).all()
    else:
        data = q.order_by(Patient.created_at.desc()).limit(200).all()

    return render_template("reports/patients.html",
                           sub=sub, data=data, date_from=df, date_to=dt)


# ── Referral Reports ──────────────────────────────────────────────────────

@reports_bp.route("/referrals")
@login_required
@require_permission("reports", "view")
def referrals():
    sub       = request.args.get("sub", "referral")
    df, dt    = _date_range()
    branch_id = current_user.branch_id

    q = Referral.query.filter(
        Referral.is_deleted == False,
        func.date(Referral.referred_at).between(df, dt),
    )
    data = q.order_by(Referral.referred_at.desc()).all()
    return render_template("reports/referrals.html",
                           sub=sub, data=data, date_from=df, date_to=dt)


# ── Insurance Reports ─────────────────────────────────────────────────────

@reports_bp.route("/insurance")
@login_required
@require_permission("reports", "view")
def insurance():
    sub       = request.args.get("sub", "patient")
    df, dt    = _date_range()
    branch_id = current_user.branch_id

    q = InsuranceClaim.query.filter(
        InsuranceClaim.is_deleted == False,
        func.date(InsuranceClaim.created_at).between(df, dt),
    )
    if branch_id:
        q = q.filter(InsuranceClaim.branch_id == branch_id)

    if sub == "claim_amount":
        data = db.session.query(
            InsuranceClaim.tpa_id,
            func.count(InsuranceClaim.id).label("claims"),
            func.sum(InsuranceClaim.claimed_amount).label("claimed"),
            func.sum(InsuranceClaim.approved_amount).label("approved"),
            func.sum(InsuranceClaim.settled_amount).label("settled"),
        ).group_by(InsuranceClaim.tpa_id).all()
    else:
        data = q.order_by(InsuranceClaim.created_at.desc()).all()

    return render_template("reports/insurance.html",
                           sub=sub, data=data, date_from=df, date_to=dt)


# ── Excel Export ──────────────────────────────────────────────────────────

@reports_bp.route("/export")
@login_required
@require_permission("reports", "export")
def export():
    report_type = request.args.get("type","op_service")
    df, dt = _date_range()
    branch_id = current_user.branch_id

    import pandas as pd
    df_data = _build_export_df(report_type, df, dt, branch_id)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        df_data.to_excel(writer, index=False, sheet_name=report_type)
        ws = writer.sheets[report_type]
        for i, col in enumerate(df_data.columns):
            ws.set_column(i, i, max(len(str(col))+4, 14))
    buf.seek(0)

    log_action("EXPORT","reports",notes=f"Exported {report_type} {df}–{dt}")
    fname = f"Revive_{report_type}_{df}_{dt}.xlsx"
    return send_file(buf, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name=fname)


def _build_export_df(report_type, df, dt, branch_id):
    import pandas as pd
    if report_type == "op_service":
        rows = db.session.query(
            Appointment.appointment_date, Appointment.token_number,
            Patient.full_name, Patient.uhid, Patient.phone,
            Appointment.visit_type, Appointment.status,
            Doctor.full_name.label("doctor"),
        ).join(Patient, Patient.id==Appointment.patient_id
        ).join(Doctor, Doctor.id==Appointment.doctor_id).filter(
            Appointment.appointment_date.between(df,dt),
            Appointment.is_deleted==False,
            *([Appointment.branch_id==branch_id] if branch_id else []),
        ).all()
        return pd.DataFrame(rows, columns=["Date","Token","Patient","UHID","Phone","Visit Type","Status","Doctor"])
    elif report_type == "ip_service":
        rows = db.session.query(
            Admission.ip_number, Admission.admission_date, Admission.discharge_date,
            Patient.full_name, Patient.uhid, Doctor.full_name.label("doctor"),
            Admission.status, Admission.final_diagnosis,
        ).join(Patient, Patient.id==Admission.patient_id
        ).join(Doctor, Doctor.id==Admission.doctor_id).filter(
            Admission.is_deleted==False,
            *([Admission.branch_id==branch_id] if branch_id else []),
        ).all()
        return pd.DataFrame(rows, columns=["IP No","Admission Date","Discharge Date","Patient","UHID","Doctor","Status","Diagnosis"])
    else:
        return pd.DataFrame({"Message": ["No data available for this report type"]})


# ── Helpers ───────────────────────────────────────────────────────────────

def _date_range():
    today = date.today()
    df = request.args.get("date_from", today.replace(day=1).isoformat())
    dt = request.args.get("date_to",   today.isoformat())
    return df, dt
