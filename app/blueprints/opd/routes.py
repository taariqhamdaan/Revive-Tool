# Rivive SCH - app/blueprints/opd/routes.py
# OPD: Appointments list with calendar date-picker + N/O/R filters,
# Consultation with all 8 tabs, Doctor management.

from datetime import date, datetime, timezone, timedelta
import calendar as cal_mod
from flask import (Blueprint, render_template, redirect, url_for,
                   request, flash, jsonify, current_app)
from flask_login import login_required, current_user
from sqlalchemy import func, extract

from app.extensions import db
from app.models.opd import (Doctor, DoctorSchedule, Appointment, Consultation,
                             Prescription, PrescriptionItem, Referral,
                             PatientHistoryChiefComplaint, PatientHistoryPastMedical,
                             PatientHistoryDrug, PatientHistoryPastInvestigation,
                             PatientHistoryDevelopment, PatientHistoryCrossConsult,
                             PatientHistoryPhysio, PatientHistoryBirth,
                             PatientHistoryNutrition, PatientHistoryOther,
                             PatientHistoryImmunization, PatientHistoryExamination)
from app.models.patients import Patient, PatientAllergy
from app.models.foundation import Branch, Department
from app.utils.decorators import require_permission
from app.utils.audit import log_action
from app.utils.generators import generate_token_number

opd_bp = Blueprint("opd", __name__)


# ── OPD List — Calendar + N/O/R filters ──────────────────────────────────────

@opd_bp.route("/")
@login_required
@require_permission("opd", "view")
def index():
    branch_id  = current_user.branch_id
    today      = date.today()
    tab        = request.args.get("tab", "op_list")

    # Calendar navigation
    cal_year  = request.args.get("cal_year",  today.year,  type=int)
    cal_month = request.args.get("cal_month", today.month, type=int)

    # Date filter — clicking a calendar day
    filter_date_str = request.args.get("date", today.isoformat())
    try:
        filter_date = datetime.strptime(filter_date_str, "%Y-%m-%d").date()
    except ValueError:
        filter_date = today

    # Visit type filter — N / O / R
    visit_type_filter = request.args.get("visit_type", "")   # new / followup / review / ""

    # Build calendar data: count appointments per day in the month
    cal_start = date(cal_year, cal_month, 1)
    last_day  = cal_mod.monthrange(cal_year, cal_month)[1]
    cal_end   = date(cal_year, cal_month, last_day)

    day_counts = {}
    counts_q = db.session.query(
        Appointment.appointment_date,
        func.count(Appointment.id).label("cnt")
    ).filter(
        Appointment.appointment_date.between(cal_start, cal_end),
        Appointment.is_deleted == False,
        *([Appointment.branch_id == branch_id] if branch_id else []),
    ).group_by(Appointment.appointment_date).all()

    for row in counts_q:
        day_counts[row.appointment_date] = row.cnt

    # Calendar matrix (6-week grid)
    cal_matrix = cal_mod.monthcalendar(cal_year, cal_month)

    # ── Appointment query ──────────────────────────────────────────
    q = Appointment.query.filter(
        Appointment.appointment_date == filter_date,
        Appointment.is_deleted == False,
    )
    if branch_id:
        q = q.filter(Appointment.branch_id == branch_id)
    if visit_type_filter:
        q = q.filter(Appointment.visit_type == visit_type_filter)

    # IP list tab
    if tab == "ip_list":
        from app.models.ipd import Admission
        adm_q = Admission.query.filter(
            Admission.status == "admitted",
            Admission.is_deleted == False,
            *([Admission.branch_id == branch_id] if branch_id else []),
        )
        rows = adm_q.order_by(Admission.admission_date).all()
    else:
        rows = q.order_by(Appointment.token_number).all()

    # N / O / R counts for today
    def _count(vtype):
        cq = Appointment.query.filter(
            Appointment.appointment_date == today,
            Appointment.is_deleted == False,
        )
        if branch_id:
            cq = cq.filter(Appointment.branch_id == branch_id)
        if vtype:
            cq = cq.filter(Appointment.visit_type == vtype)
        return cq.count()

    counts = type("C", (), {
        "op_list":   _count(""),
        "ip_list":   0,
        "all":       _count(""),
        "new":       _count("new"),
        "followup":  _count("followup"),
        "review":    _count("review"),
        "completed": Appointment.query.filter(
            Appointment.appointment_date == today,
            Appointment.status == "completed",
            Appointment.is_deleted == False,
        ).count(),
        "cancelled": Appointment.query.filter(
            Appointment.appointment_date == today,
            Appointment.status == "cancelled",
            Appointment.is_deleted == False,
        ).count(),
    })()

    # Previous/next month navigation
    if cal_month == 1:
        prev_year, prev_month = cal_year - 1, 12
    else:
        prev_year, prev_month = cal_year, cal_month - 1
    if cal_month == 12:
        next_year, next_month = cal_year + 1, 1
    else:
        next_year, next_month = cal_year, cal_month + 1

    month_name = cal_mod.month_name[cal_month]

    return render_template("opd/index.html",
        tab=tab, rows=rows, today=today,
        filter_date=filter_date, visit_type_filter=visit_type_filter,
        cal_year=cal_year, cal_month=cal_month,
        cal_matrix=cal_matrix, day_counts=day_counts,
        month_name=month_name,
        prev_year=prev_year, prev_month=prev_month,
        next_year=next_year, next_month=next_month,
        counts=counts)


# ── Book Appointment ──────────────────────────────────────────────────────────

@opd_bp.route("/book", methods=["GET", "POST"])
@login_required
@require_permission("opd", "create")
def book():
    branch_id = current_user.branch_id
    doctors   = Doctor.query.filter_by(branch_id=branch_id, is_active=True, is_deleted=False).all()
    today     = date.today()

    if request.method == "POST":
        try:
            patient_id = int(request.form.get("patient_id"))
            doctor_id  = int(request.form.get("doctor_id"))
            appt_date  = datetime.strptime(request.form.get("appointment_date"), "%Y-%m-%d").date()
            visit_type = request.form.get("visit_type", "new")
            slot_time_str = request.form.get("slot_time", "")

            token = generate_token_number(branch_id, appt_date)
            appt = Appointment(
                branch_id=branch_id,
                patient_id=patient_id,
                doctor_id=doctor_id,
                appointment_date=appt_date,
                visit_type=visit_type,
                token_number=token,
                slot_time=datetime.strptime(slot_time_str, "%H:%M").time() if slot_time_str else None,
                reason=request.form.get("reason", "").strip(),
                status="booked",
            )
            db.session.add(appt)
            db.session.commit()
            log_action("CREATE", "opd", record_id=appt.id, record_type="Appointment",
                       new_value={"patient_id": patient_id, "date": str(appt_date), "token": token})
            flash(f"Appointment booked. Token #{token}", "success")
            return redirect(url_for("opd.index", date=appt_date.isoformat()))
        except Exception as e:
            db.session.rollback()
            flash(f"Booking failed: {e}", "danger")

    return render_template("opd/book.html", doctors=doctors, today=today.isoformat())


# ── Consultation ──────────────────────────────────────────────────────────────

@opd_bp.route("/consultation/<int:appt_id>", methods=["GET", "POST"])
@login_required
@require_permission("opd", "create")
def consultation(appt_id):
    appt    = Appointment.query.get_or_404(appt_id)
    patient = Patient.query.get_or_404(appt.patient_id)
    doctor  = Doctor.query.get_or_404(appt.doctor_id)
    branch  = Branch.query.get(appt.branch_id)

    # Existing consultation or new
    consult = Consultation.query.filter_by(
        appointment_id=appt_id, is_deleted=False).first()

    # Existing prescription items
    rx_items = []
    if consult and consult.prescription:
        rx_items = consult.prescription.items.filter_by(is_deleted=False).all()

    # Allergies
    allergies = PatientAllergy.query.filter_by(
        patient_id=patient.id, is_deleted=False).all()

    # Previous consultations for timeline (last 5)
    prev_consults = Consultation.query.filter(
        Consultation.patient_id == patient.id,
        Consultation.id != (consult.id if consult else 0),
        Consultation.is_deleted == False,
    ).order_by(Consultation.created_at.desc()).limit(5).all()

    # Previous vitals for comparison
    prev_vitals = prev_consults[0] if prev_consults else None

    # History entries for this consultation
    hist_data = {}
    if consult:
        hist_data = {
            "chief_complaints":    consult.chief_complaints.filter_by(is_deleted=False).all(),
            "past_medical":        consult.past_medical.filter_by(is_deleted=False).all(),
            "drug_history":        consult.drug_history.filter_by(is_deleted=False).all(),
            "past_investigations": consult.past_investigations.filter_by(is_deleted=False).all(),
            "development":         consult.development_history.filter_by(is_deleted=False).all(),
            "cross_consults":      consult.cross_consults.filter_by(is_deleted=False).all(),
            "physio":              consult.physio_history.filter_by(is_deleted=False).all(),
            "birth":               consult.birth_history.filter_by(is_deleted=False).all(),
            "nutrition":           consult.nutrition_history.filter_by(is_deleted=False).all(),
            "other":               consult.other_history.filter_by(is_deleted=False).all(),
            "immunization":        consult.immunization.filter_by(is_deleted=False).all(),
            "examination":         consult.examination.filter_by(is_deleted=False).all(),
        }

    # Surgical doctors for surgery tab
    surgical_doctors = Doctor.query.filter_by(
        branch_id=appt.branch_id, is_active=True, is_deleted=False).all()

    if request.method == "POST":
        return _save_consultation(appt, patient, doctor, consult)

    return render_template("opd/consultation.html",
        appt=appt, patient=patient, doctor=doctor,
        branch=branch, consult=consult, rx_items=rx_items,
        allergies=allergies, prev_consults=prev_consults,
        prev_vitals=prev_vitals, hist_data=hist_data,
        surgical_doctors=surgical_doctors,
        today=date.today())


def _save_consultation(appt, patient, doctor, consult):
    """Save all consultation tabs in one POST."""
    try:
        if not consult:
            consult = Consultation(
                appointment_id=appt.id,
                patient_id=patient.id,
                doctor_id=doctor.id,
                branch_id=appt.branch_id,
            )
            db.session.add(consult)
            db.session.flush()

        f = request.form

        # ── Vitals ────────────────────────────────────────────────
        def _num(k, cast=float):
            v = f.get(k, "").strip()
            try: return cast(v) if v else None
            except: return None

        consult.bp_systolic    = _num("bp_systolic", int)
        consult.bp_diastolic   = _num("bp_diastolic", int)
        consult.bp_arm         = f.get("bp_arm", "L")
        consult.pulse_bpm      = _num("pulse_bpm", int)
        consult.heart_rate_bpm = _num("heart_rate", int)
        consult.weight_kg      = _num("weight_kg")
        consult.height_cm      = _num("height_cm")
        consult.bmi            = _num("bmi")
        consult.temp_celsius   = _num("temp_celsius")
        consult.spo2_percent   = _num("spo2_percent", int)
        consult.cbg_mg_dl      = _num("cbg")
        consult.blood_group    = f.get("blood_group_vitals", "").strip() or None

        # ── Clinical summary ───────────────────────────────────────
        consult.chief_complaint    = f.get("chief_complaint", "").strip()
        consult.duration_days      = f.get("duration_days", "").strip()
        consult.duration_months    = f.get("duration_months", "").strip()
        consult.diagnosis          = f.get("diagnosis", "").strip()
        consult.icd10_primary      = f.get("icd10_primary", "").strip()
        consult.examination_notes  = f.get("examination_notes", "").strip()
        consult.treatment_plan     = f.get("treatment_plan", "").strip()
        consult.advice             = f.get("advice", "").strip()
        consult.special_advice     = f.get("special_advice", "").strip()
        consult.test_request       = f.get("test_request", "").strip()
        if f.get("follow_up_days"):
            consult.follow_up_days = int(f.get("follow_up_days"))
        if f.get("next_review_date"):
            consult.follow_up_date = datetime.strptime(
                f.get("next_review_date"), "%Y-%m-%d").date()

        # ── Lab Investigation ──────────────────────────────────────
        ordered = f.getlist("ordered_tests[]")
        custom  = [t.strip() for t in f.getlist("custom_test[]") if t.strip()]
        consult.lab_ordered_tests  = ",".join(ordered + custom)
        consult.lab_sample_type    = f.get("lab_sample_type", "blood")
        consult.lab_fasting        = f.get("lab_fasting", "non_fasting")
        consult.lab_special_instructions = f.get("lab_special_instructions", "").strip()
        if f.get("lab_collection_date"):
            consult.lab_collection_date = datetime.strptime(
                f.get("lab_collection_date"), "%Y-%m-%d").date()

        # ── Scan ──────────────────────────────────────────────────
        for scan in ["xray", "usg", "mri", "ct"]:
            setattr(consult, f"scan_{scan}_ordered",
                    f.get(f"scan_{scan}") == "1")
            setattr(consult, f"scan_{scan}_organ",
                    f.get(f"scan_{scan}_organ", "").strip() or None)
            setattr(consult, f"scan_{scan}_position",
                    f.get(f"scan_{scan}_position", "").strip() or None)
            setattr(consult, f"scan_{scan}_desc",
                    f.get(f"scan_{scan}_desc", "").strip() or None)
            setattr(consult, f"scan_{scan}_config",
                    f.get(f"scan_{scan}_config", "").strip() or None)
        consult.scan_organisation = f.get("scan_organisation", "").strip() or None
        if f.get("scan_collection_date"):
            consult.scan_collection_date = datetime.strptime(
                f.get("scan_collection_date"), "%Y-%m-%d").date()

        # ── Surgery ───────────────────────────────────────────────
        consult.surgery_plan     = f.get("surgery_plan", "").strip() or None
        consult.surgery_procedure = f.get("surgery_procedure", "").strip() or None
        consult.surgeon_id       = _num("surgeon_id", int)
        consult.anaesthesia_type = f.get("anaesthesia_type", "").strip() or None
        consult.surgery_ward_ot  = f.get("surgery_ward_ot", "").strip() or None
        consult.preop_tests      = f.get("preop_tests", "").strip() or None
        consult.surgery_notes    = f.get("surgery_notes", "").strip() or None
        consult.surgery_night_notes = f.get("surgery_night_notes", "").strip() or None
        if f.get("surgery_scheduled_date"):
            consult.surgery_scheduled_date = datetime.strptime(
                f.get("surgery_scheduled_date"), "%Y-%m-%d").date()

        # ── Patient History (12 tables) ────────────────────────────
        _save_history(f, consult)

        # ── Prescription / Medicines ───────────────────────────────
        _save_prescription(f, consult, appt)

        # ── Appointment status ─────────────────────────────────────
        action = f.get("action", "save")
        if action == "complete":
            appt.status = "completed"

        db.session.commit()
        log_action("UPDATE" if consult.id else "CREATE", "opd",
                   record_id=consult.id, record_type="Consultation")
        flash("Consultation saved." if action == "save" else "Consultation completed.", "success")
        return redirect(url_for("opd.index", date=appt.appointment_date.isoformat()))

    except Exception as e:
        db.session.rollback()
        flash(f"Save failed: {e}", "danger")
        return redirect(url_for("opd.consultation", appt_id=appt.id))


def _save_history(f, consult):
    """Save all 12 patient history sections."""
    # Chief Complaints — multiple entries from ⊕ rows
    _replace_history(
        consult, PatientHistoryChiefComplaint, "cc",
        lambda i, f: PatientHistoryChiefComplaint(
            patient_id=consult.patient_id,
            consultation_id=consult.id,
            entry_type=f.getlist("cc_type[]")[i] if i < len(f.getlist("cc_type[]")) else "",
            description=f.getlist("cc_desc[]")[i],
            duration_days=int(f.getlist("cc_days[]")[i]) if f.getlist("cc_days[]") and i < len(f.getlist("cc_days[]")) and f.getlist("cc_days[]")[i] else None,
        ), f
    )

    # Past Medical/Surgical
    _replace_history_simple(consult, PatientHistoryPastMedical,
        "pm_type[]", "pm_desc[]", f)

    # Drug History — extra drug_name field
    for i, desc in enumerate(f.getlist("dh_drug[]")):
        if not desc.strip(): continue
        types = f.getlist("dh_type[]")
        sev   = f.getlist("dh_severity[]")
        entry = PatientHistoryDrug(
            patient_id=consult.patient_id,
            consultation_id=consult.id,
            drug_name=desc.strip(),
            entry_type=types[i] if i < len(types) else "Current Medication",
            severity=sev[i] if i < len(sev) else "",
            description=f.getlist("dh_desc[]")[i] if i < len(f.getlist("dh_desc[]")) else "",
        )
        db.session.add(entry)

    # Past Investigation
    for i, tname in enumerate(f.getlist("pi_test[]")):
        if not tname.strip(): continue
        entry = PatientHistoryPastInvestigation(
            patient_id=consult.patient_id,
            consultation_id=consult.id,
            test_name=tname.strip(),
            result_value=f.getlist("pi_result[]")[i] if i < len(f.getlist("pi_result[]")) else "",
            description=f.getlist("pi_desc[]")[i] if i < len(f.getlist("pi_desc[]")) else "",
            test_date=datetime.strptime(f.getlist("pi_date[]")[i], "%Y-%m-%d").date()
                      if i < len(f.getlist("pi_date[]")) and f.getlist("pi_date[]")[i] else None,
            entry_type=f.getlist("pi_type[]")[i] if i < len(f.getlist("pi_type[]")) else "Lab",
        )
        db.session.add(entry)

    # Simple history sections
    for prefix, Model in [
        ("dev", PatientHistoryDevelopment),
        ("cc2", PatientHistoryCrossConsult),
        ("ph",  PatientHistoryPhysio),
        ("bh",  PatientHistoryBirth),
        ("nh",  PatientHistoryNutrition),
        ("oh",  PatientHistoryOther),
    ]:
        _replace_history_simple(consult, Model,
            f"{prefix}_type[]", f"{prefix}_desc[]", f)

    # Immunization
    for i, vname in enumerate(f.getlist("imm_vaccine[]")):
        if not vname.strip(): continue
        entry = PatientHistoryImmunization(
            patient_id=consult.patient_id,
            consultation_id=consult.id,
            vaccine_name=vname.strip(),
            dose_number=f.getlist("imm_dose[]")[i] if i < len(f.getlist("imm_dose[]")) else "",
            description=f.getlist("imm_desc[]")[i] if i < len(f.getlist("imm_desc[]")) else "",
            given_date=datetime.strptime(f.getlist("imm_date[]")[i], "%Y-%m-%d").date()
                       if i < len(f.getlist("imm_date[]")) and f.getlist("imm_date[]")[i] else None,
            entry_type=f.getlist("imm_type[]")[i] if i < len(f.getlist("imm_type[]")) else "",
        )
        db.session.add(entry)

    # Examination
    for i, desc in enumerate(f.getlist("ex_desc[]")):
        if not desc.strip(): continue
        entry = PatientHistoryExamination(
            patient_id=consult.patient_id,
            consultation_id=consult.id,
            description=desc.strip(),
            system=f.getlist("ex_system[]")[i] if i < len(f.getlist("ex_system[]")) else "",
            entry_type=f.getlist("ex_type[]")[i] if i < len(f.getlist("ex_type[]")) else "General",
        )
        db.session.add(entry)


def _replace_history(consult, Model, prefix, factory, f):
    """Replace all entries for a model type in this consultation."""
    Model.query.filter_by(consultation_id=consult.id).update({"is_deleted": True})
    for i, desc in enumerate(f.getlist(f"{prefix}_desc[]")):
        if not desc.strip(): continue
        db.session.add(factory(i, f))


def _replace_history_simple(consult, Model, type_key, desc_key, f):
    """Save simple type+description history rows."""
    Model.query.filter_by(consultation_id=consult.id).update({"is_deleted": True})
    types = f.getlist(type_key)
    descs = f.getlist(desc_key)
    for i, desc in enumerate(descs):
        if not desc.strip(): continue
        entry = Model(
            patient_id=consult.patient_id,
            consultation_id=consult.id,
            entry_type=types[i] if i < len(types) else "",
            description=desc.strip(),
        )
        db.session.add(entry)


def _save_prescription(f, consult, appt):
    """Save prescription items (medicines tab)."""
    drug_names = f.getlist("drug_name[]")
    if not any(d.strip() for d in drug_names):
        return

    if not consult.prescription:
        from app.utils.generators import generate_rx_number
        rx = Prescription(
            consultation_id=consult.id,
            patient_id=consult.patient_id,
            doctor_id=consult.doctor_id,
            branch_id=consult.branch_id,
            rx_number=generate_rx_number(consult.branch_id),
        )
        db.session.add(rx)
        db.session.flush()
        consult_rx = rx
    else:
        consult_rx = consult.prescription
        consult_rx.items.update({"is_deleted": True})

    dosages    = f.getlist("dosage[]")
    routes     = f.getlist("route[]")
    mor_qtys   = f.getlist("mor[]")
    mor_times  = f.getlist("mor_timing[]")
    act_qtys   = f.getlist("act[]")
    act_times  = f.getlist("act_timing[]")
    night_qtys = f.getlist("night[]")
    night_times= f.getlist("night_timing[]")
    dur_days   = f.getlist("duration_days[]")
    qtys       = f.getlist("quantity[]")
    instrs     = f.getlist("instructions[]")
    langs      = f.getlist("rx_lang[]")

    for i, dname in enumerate(drug_names):
        if not dname.strip(): continue
        item = PrescriptionItem(
            prescription_id=consult_rx.id,
            drug_name=dname.strip(),
            dosage=dosages[i] if i < len(dosages) else "",
            route=routes[i] if i < len(routes) else "Oral",
            mor_qty=float(mor_qtys[i]) if i < len(mor_qtys) and mor_qtys[i] else 0,
            mor_timing=mor_times[i] if i < len(mor_times) else "AF",
            act_qty=float(act_qtys[i]) if i < len(act_qtys) and act_qtys[i] else 0,
            act_timing=act_times[i] if i < len(act_times) else "AF",
            night_qty=float(night_qtys[i]) if i < len(night_qtys) and night_qtys[i] else 0,
            night_timing=night_times[i] if i < len(night_times) else "AF",
            duration_days=int(dur_days[i]) if i < len(dur_days) and dur_days[i] else None,
            quantity=int(qtys[i]) if i < len(qtys) and qtys[i] else None,
            instructions=instrs[i] if i < len(instrs) else "",
            rx_language=langs[i] if i < len(langs) else "en",
            sort_order=i,
        )
        db.session.add(item)


# ── Status Update ─────────────────────────────────────────────────────────────

@opd_bp.route("/appointment/<int:appt_id>/status", methods=["POST"])
@login_required
@require_permission("opd", "edit")
def update_status(appt_id):
    appt = Appointment.query.get_or_404(appt_id)
    appt.status = request.form.get("status", appt.status)
    db.session.commit()
    log_action("UPDATE", "opd", record_id=appt_id, record_type="Appointment",
               new_value={"status": appt.status})
    return redirect(request.referrer or url_for("opd.index"))


# ── Slot availability AJAX ────────────────────────────────────────────────────

@opd_bp.route("/slots")
@login_required
def slots():
    doctor_id = request.args.get("doctor_id", type=int)
    date_str  = request.args.get("date", "")
    if not doctor_id or not date_str:
        return jsonify([])

    try:
        appt_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify([])

    dow = appt_date.weekday()
    schedule = DoctorSchedule.query.filter_by(
        doctor_id=doctor_id, day_of_week=dow,
        is_active=True, is_deleted=False).first()

    if not schedule:
        return jsonify([])

    # Generate slots
    booked = {
        str(a.slot_time) for a in
        Appointment.query.filter_by(
            doctor_id=doctor_id,
            appointment_date=appt_date,
            is_deleted=False,
        ).filter(Appointment.status != "cancelled").all()
        if a.slot_time
    }

    slots_out = []
    current = datetime.combine(appt_date, schedule.start_time)
    end     = datetime.combine(appt_date, schedule.end_time)
    delta   = timedelta(minutes=schedule.slot_duration)

    while current < end:
        t = current.strftime("%H:%M")
        slots_out.append({"time": t, "available": t not in booked})
        current += delta

    return jsonify(slots_out)


# ── Calendar appointments AJAX (for day-click) ────────────────────────────────

@opd_bp.route("/calendar-data")
@login_required
def calendar_data():
    """Return appointment counts per day for a given month (AJAX)."""
    year  = request.args.get("year",  type=int)
    month = request.args.get("month", type=int)
    branch_id = current_user.branch_id

    if not year or not month:
        return jsonify({})

    start = date(year, month, 1)
    end   = date(year, month, cal_mod.monthrange(year, month)[1])

    rows = db.session.query(
        Appointment.appointment_date,
        Appointment.visit_type,
        func.count(Appointment.id).label("cnt")
    ).filter(
        Appointment.appointment_date.between(start, end),
        Appointment.is_deleted == False,
        *([Appointment.branch_id == branch_id] if branch_id else []),
    ).group_by(Appointment.appointment_date, Appointment.visit_type).all()

    result = {}
    for row in rows:
        key = str(row.appointment_date)
        if key not in result:
            result[key] = {"total": 0, "new": 0, "followup": 0, "review": 0}
        result[key]["total"] += row.cnt
        result[key][row.visit_type] = result[key].get(row.visit_type, 0) + row.cnt

    return jsonify(result)


# ── Drug history patient search (Answer A — query by drug name) ───────────────

@opd_bp.route("/patients-by-drug")
@login_required
@require_permission("opd", "view")
def patients_by_drug():
    """Find all patients who have a drug in their history (e.g. Penicillin allergy)."""
    drug  = request.args.get("drug", "").strip()
    dtype = request.args.get("type", "")  # e.g. 'Allergy'
    if len(drug) < 2:
        return jsonify([])

    q = PatientHistoryDrug.query.filter(
        PatientHistoryDrug.drug_name.ilike(f"%{drug}%"),
        PatientHistoryDrug.is_deleted == False,
    )
    if dtype:
        q = q.filter(PatientHistoryDrug.entry_type == dtype)

    rows = q.limit(50).all()
    seen = set()
    result = []
    for row in rows:
        if row.patient_id in seen:
            continue
        seen.add(row.patient_id)
        p = Patient.query.get(row.patient_id)
        if p:
            result.append({
                "patient_id": p.id,
                "name":       p.full_name,
                "uhid":       p.uhid,
                "phone":      p.phone,
                "drug":       row.drug_name,
                "type":       row.entry_type,
                "severity":   row.severity or "",
            })
    return jsonify(result)


# ── Doctors ───────────────────────────────────────────────────────────────────

@opd_bp.route("/doctors")
@login_required
@require_permission("opd", "view")
def doctors():
    branch_id   = current_user.branch_id
    doctors_list = Doctor.query.filter_by(branch_id=branch_id, is_deleted=False).all()
    departments  = Department.query.filter_by(branch_id=branch_id, is_deleted=False).all()
    return render_template("opd/doctors.html",
                           doctors=doctors_list, departments=departments)


@opd_bp.route("/doctor/save", methods=["POST"])
@login_required
@require_permission("opd", "create")
def doctor_save():
    branch_id = current_user.branch_id
    doc_id    = request.form.get("doctor_id")

    if doc_id:
        d = Doctor.query.get_or_404(int(doc_id))
    else:
        seq = Doctor.query.filter_by(branch_id=branch_id).count() + 1
        d = Doctor(branch_id=branch_id, doctor_code=f"DR{seq:04d}")
        db.session.add(d)

    d.title            = request.form.get("title", "Dr.")
    d.full_name        = request.form.get("full_name", "").strip()
    d.full_name_ta     = request.form.get("full_name_ta", "").strip() or None
    d.specialisation   = request.form.get("specialisation", "").strip() or None
    d.qualification    = request.form.get("qualification", "").strip() or None
    d.reg_number       = request.form.get("reg_number", "").strip() or None
    d.department_id    = request.form.get("department_id") or None
    d.consultation_fee = float(request.form.get("consultation_fee", 0) or 0)
    d.follow_up_fee    = float(request.form.get("follow_up_fee", 0) or 0)
    d.is_surgical      = request.form.get("is_surgical") == "on"

    db.session.commit()
    log_action("CREATE" if not doc_id else "UPDATE", "opd",
               record_id=d.id, record_type="Doctor")
    flash(f"Dr. {d.full_name} saved.", "success")
    return redirect(url_for("opd.doctors"))
