# MediCore - app/blueprints/ipd/routes.py
# IPD: Ward/Bed management, Admissions, Daily notes, Discharge summaries.
# Logic summary per tab:
#   beds       — ward and bed master, bed status board (visual occupancy grid)
#   admissions — active admissions list with admit/transfer/discharge actions
#   notes      — daily progress notes entry for admitted patients
#   discharge  — discharge summary creation and print
#   history    — past admissions list with search

from datetime import date, datetime, timezone
from flask import (Blueprint, render_template, redirect, url_for,
                   request, flash, jsonify, current_app)
from flask_login import login_required, current_user
from app.extensions import db
from app.models.ipd import Ward, Bed, Admission, DailyNote, DischargeSummary
from app.models.patients import Patient
from app.models.opd import Doctor
from app.models.foundation import Branch, Department
from app.utils.decorators import require_permission
from app.utils.audit import log_action
from app.utils.generators import generate_ip_number

ipd_bp = Blueprint("ipd", __name__)


@ipd_bp.route("/")
@login_required
@require_permission("ipd", "view")
def index():
    tab       = request.args.get("tab", "admissions")
    branch_id = current_user.branch_id
    page      = request.args.get("page", 1, type=int)
    search    = request.args.get("q", "").strip()
    today     = date.today()

    if tab == "beds":
        return _beds_view(branch_id)
    elif tab == "notes":
        return _notes_view(branch_id, page)
    elif tab == "discharge":
        return _discharge_view(branch_id, page)
    elif tab == "history":
        return _history_view(branch_id, search, page)

    # Default: active admissions
    q = Admission.query.filter(
        Admission.status == "admitted",
        Admission.is_deleted == False,
    )
    if branch_id:
        q = q.filter(Admission.branch_id == branch_id)
    if search:
        like = f"%{search}%"
        q = q.join(Patient).filter(
            db.or_(Patient.first_name.ilike(like), Patient.uhid.ilike(like),
                   Admission.ip_number.ilike(like))
        )
    admissions = q.order_by(Admission.admission_date.desc()).paginate(page=page, per_page=25)

    # Data for new admission modal
    doctors = Doctor.query.filter_by(branch_id=branch_id, is_active=True, is_deleted=False).all()
    wards   = Ward.query.filter_by(branch_id=branch_id, is_active=True, is_deleted=False).all()

    # Bed occupancy stats
    total_beds    = Bed.query.filter_by(branch_id=branch_id, is_active=True, is_deleted=False).count()
    occupied_beds = Bed.query.filter_by(branch_id=branch_id, status="occupied", is_deleted=False).count()
    avail_beds    = total_beds - occupied_beds

    return render_template("ipd/index.html",
                           tab=tab, admissions=admissions, doctors=doctors,
                           wards=wards, search=search, today=today,
                           total_beds=total_beds, occupied_beds=occupied_beds,
                           avail_beds=avail_beds)


def _beds_view(branch_id):
    wards = Ward.query.filter_by(branch_id=branch_id, is_active=True, is_deleted=False).order_by(Ward.ward_code).all()
    total_beds    = Bed.query.filter_by(branch_id=branch_id, is_active=True, is_deleted=False).count()
    occupied_beds = Bed.query.filter_by(branch_id=branch_id, status="occupied", is_deleted=False).count()
    avail_beds    = total_beds - occupied_beds
    return render_template("ipd/index.html", tab="beds", wards=wards,
                           total_beds=total_beds, occupied_beds=occupied_beds, avail_beds=avail_beds)


def _notes_view(branch_id, page):
    # Show today's admitted patients for note entry
    admissions = Admission.query.filter(
        Admission.status == "admitted",
        Admission.is_deleted == False,
        *([Admission.branch_id == branch_id] if branch_id else []),
    ).order_by(Admission.admission_date).paginate(page=page, per_page=25)
    return render_template("ipd/index.html", tab="notes", admissions=admissions)


def _discharge_view(branch_id, page):
    admissions = Admission.query.filter(
        Admission.status == "admitted",
        Admission.is_deleted == False,
        *([Admission.branch_id == branch_id] if branch_id else []),
    ).order_by(Admission.admission_date).paginate(page=page, per_page=25)
    return render_template("ipd/index.html", tab="discharge", admissions=admissions)


def _history_view(branch_id, search, page):
    q = Admission.query.filter(
        Admission.status.in_(["discharged", "transferred", "deceased"]),
        Admission.is_deleted == False,
    )
    if branch_id:
        q = q.filter(Admission.branch_id == branch_id)
    if search:
        like = f"%{search}%"
        q = q.join(Patient).filter(
            db.or_(Patient.first_name.ilike(like), Patient.uhid.ilike(like),
                   Admission.ip_number.ilike(like))
        )
    admissions = q.order_by(Admission.discharge_date.desc()).paginate(page=page, per_page=25)
    return render_template("ipd/index.html", tab="history", admissions=admissions, search=search)


# ── New Admission ─────────────────────────────────────────────────────────

@ipd_bp.route("/admit", methods=["POST"])
@login_required
@require_permission("ipd", "create")
def admit():
    branch_id  = current_user.branch_id
    branch     = Branch.query.get(branch_id) if branch_id else None

    try:
        patient_id     = int(request.form.get("patient_id"))
        doctor_id      = int(request.form.get("doctor_id"))
        bed_id         = int(request.form.get("bed_id"))
        admission_type = request.form.get("admission_type", "elective")
        reason         = request.form.get("reason", "").strip()
        prov_diagnosis = request.form.get("provisional_diagnosis", "").strip()

        bed = Bed.query.get_or_404(bed_id)
        if bed.status != "available":
            flash("Selected bed is not available.", "danger")
            return redirect(url_for("ipd.index"))

        ip_number = generate_ip_number(branch.code if branch else "GEN")

        adm = Admission(
            branch_id=branch_id,
            patient_id=patient_id,
            doctor_id=doctor_id,
            bed_id=bed_id,
            ward_id=bed.ward_id,
            ip_number=ip_number,
            admission_date=datetime.now(timezone.utc),
            admission_type=admission_type,
            reason=reason,
            provisional_diagnosis=prov_diagnosis,
            status="admitted",
            admitted_by=current_user.id,
        )
        db.session.add(adm)

        # Mark bed as occupied
        bed.status = "occupied"

        db.session.commit()
        log_action("CREATE", "ipd", record_id=adm.id, record_type="Admission",
                   new_value={"ip_number": ip_number, "patient_id": patient_id})
        flash(f"Patient admitted. IP Number: {ip_number}", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Admission failed: {e}", "danger")

    return redirect(url_for("ipd.index", tab="admissions"))


# ── Transfer Bed ──────────────────────────────────────────────────────────

@ipd_bp.route("/admission/<int:adm_id>/transfer", methods=["POST"])
@login_required
@require_permission("ipd", "edit")
def transfer_bed(adm_id):
    adm        = Admission.query.get_or_404(adm_id)
    new_bed_id = int(request.form.get("new_bed_id"))
    new_bed    = Bed.query.get_or_404(new_bed_id)

    if new_bed.status != "available":
        flash("Target bed is not available.", "danger")
        return redirect(url_for("ipd.index"))

    # Release old bed
    old_bed = Bed.query.get(adm.bed_id)
    if old_bed:
        old_bed.status = "available"

    # Assign new bed
    adm.bed_id  = new_bed_id
    adm.ward_id = new_bed.ward_id
    new_bed.status = "occupied"

    db.session.commit()
    log_action("UPDATE", "ipd", record_id=adm_id, record_type="Admission",
               new_value={"bed_transferred_to": new_bed_id})
    flash("Bed transferred.", "success")
    return redirect(url_for("ipd.index"))


# ── Daily Notes ───────────────────────────────────────────────────────────

@ipd_bp.route("/admission/<int:adm_id>/notes", methods=["GET", "POST"])
@login_required
@require_permission("ipd", "create")
def daily_notes(adm_id):
    adm     = Admission.query.get_or_404(adm_id)
    patient = Patient.query.get(adm.patient_id)
    notes   = DailyNote.query.filter_by(admission_id=adm_id, is_deleted=False)\
                             .order_by(DailyNote.note_date.desc(), DailyNote.note_time.desc()).all()

    if request.method == "POST":
        try:
            note_date = datetime.strptime(request.form.get("note_date"), "%Y-%m-%d").date()
            note_time_str = request.form.get("note_time", "")
            note = DailyNote(
                admission_id=adm_id,
                patient_id=adm.patient_id,
                noted_by=current_user.id,
                note_type=request.form.get("note_type", "progress"),
                note_date=note_date,
                note_time=datetime.strptime(note_time_str, "%H:%M").time() if note_time_str else None,
                bp_systolic=request.form.get("bp_systolic") or None,
                bp_diastolic=request.form.get("bp_diastolic") or None,
                pulse_bpm=request.form.get("pulse_bpm") or None,
                temp_celsius=request.form.get("temp_celsius") or None,
                spo2_percent=request.form.get("spo2_percent") or None,
                notes=request.form.get("notes", "").strip(),
                orders=request.form.get("orders", "").strip(),
            )
            db.session.add(note)
            db.session.commit()
            log_action("CREATE", "ipd", record_id=note.id, record_type="DailyNote")
            flash("Progress note saved.", "success")
            return redirect(url_for("ipd.daily_notes", adm_id=adm_id))
        except Exception as e:
            db.session.rollback()
            flash(f"Error: {e}", "danger")

    return render_template("ipd/daily_notes.html",
                           adm=adm, patient=patient, notes=notes,
                           today=date.today())


# ── Discharge ─────────────────────────────────────────────────────────────

@ipd_bp.route("/admission/<int:adm_id>/discharge", methods=["GET", "POST"])
@login_required
@require_permission("ipd", "edit")
def discharge(adm_id):
    adm     = Admission.query.get_or_404(adm_id)
    patient = Patient.query.get(adm.patient_id)
    doctor  = Doctor.query.get(adm.doctor_id) if adm.doctor_id else None
    branch  = Branch.query.get(adm.branch_id) if adm.branch_id else None

    existing_summary = DischargeSummary.query.filter_by(
        admission_id=adm_id, is_deleted=False).first()

    if request.method == "POST":
        try:
            discharge_type = request.form.get("discharge_type", "regular")
            final_diag     = request.form.get("final_diagnosis", "").strip()

            if not existing_summary:
                summary = DischargeSummary(
                    admission_id=adm_id,
                    patient_id=adm.patient_id,
                    doctor_id=adm.doctor_id,
                    branch_id=adm.branch_id,
                    prepared_by=current_user.id,
                )
                db.session.add(summary)
            else:
                summary = existing_summary

            summary.admission_diagnosis     = request.form.get("admission_diagnosis", "")
            summary.final_diagnosis         = final_diag
            summary.procedures_done         = request.form.get("procedures_done", "")
            summary.investigations          = request.form.get("investigations", "")
            summary.treatment_given         = request.form.get("treatment_given", "")
            summary.condition_on_discharge  = request.form.get("condition_on_discharge", "stable")
            summary.discharge_advice        = request.form.get("discharge_advice", "")
            summary.medications_on_discharge = request.form.get("medications_on_discharge", "")
            fu_date = request.form.get("follow_up_date", "")
            summary.follow_up_date = datetime.strptime(fu_date, "%Y-%m-%d").date() if fu_date else None
            summary.follow_up_instructions  = request.form.get("follow_up_instructions", "")

            # Discharge the admission
            adm.status         = "discharged"
            adm.discharge_date = datetime.now(timezone.utc)
            adm.discharge_type = discharge_type
            adm.final_diagnosis = final_diag
            adm.discharged_by  = current_user.id

            # Release bed
            bed = Bed.query.get(adm.bed_id)
            if bed:
                bed.status = "available"

            db.session.commit()
            log_action("UPDATE", "ipd", record_id=adm_id, record_type="Admission",
                       new_value={"status": "discharged", "discharge_type": discharge_type})
            flash(f"Patient discharged. IP: {adm.ip_number}", "success")
            return redirect(url_for("ipd.discharge_summary", adm_id=adm_id))

        except Exception as e:
            db.session.rollback()
            flash(f"Discharge failed: {e}", "danger")

    return render_template("ipd/discharge_form.html",
                           adm=adm, patient=patient, doctor=doctor, branch=branch,
                           summary=existing_summary, today=date.today())


@ipd_bp.route("/admission/<int:adm_id>/discharge-summary")
@login_required
@require_permission("ipd", "view")
def discharge_summary(adm_id):
    adm     = Admission.query.get_or_404(adm_id)
    patient = Patient.query.get(adm.patient_id)
    doctor  = Doctor.query.get(adm.doctor_id) if adm.doctor_id else None
    branch  = Branch.query.get(adm.branch_id) if adm.branch_id else None
    summary = DischargeSummary.query.filter_by(admission_id=adm_id, is_deleted=False).first()
    notes   = DailyNote.query.filter_by(admission_id=adm_id, is_deleted=False)\
                             .order_by(DailyNote.note_date).all()
    return render_template("ipd/discharge_summary.html",
                           adm=adm, patient=patient, doctor=doctor,
                           branch=branch, summary=summary, notes=notes)


# ── Ward & Bed CRUD ───────────────────────────────────────────────────────

@ipd_bp.route("/ward/save", methods=["POST"])
@login_required
@require_permission("ipd", "create")
def ward_save():
    branch_id = current_user.branch_id
    ward_id   = request.form.get("ward_id")

    if ward_id:
        w = Ward.query.get_or_404(int(ward_id))
    else:
        seq = Ward.query.filter_by(branch_id=branch_id).count() + 1
        w = Ward(branch_id=branch_id, ward_code=f"W{seq:03d}")
        db.session.add(w)

    w.name            = request.form.get("name", "").strip()
    w.name_ta         = request.form.get("name_ta", "").strip() or None
    w.ward_type       = request.form.get("ward_type", "general")
    w.floor           = request.form.get("floor", "").strip() or None
    w.charge_per_day  = float(request.form.get("charge_per_day", 0) or 0)

    db.session.flush()

    # Create beds
    bed_count = int(request.form.get("bed_count", 0) or 0)
    existing  = Bed.query.filter_by(ward_id=w.id).count()
    for i in range(existing + 1, existing + bed_count + 1):
        bed = Bed(ward_id=w.id, branch_id=branch_id,
                  bed_number=str(i), status="available",
                  bed_type=request.form.get("bed_type", "standard"))
        db.session.add(bed)

    w.total_beds = Bed.query.filter_by(ward_id=w.id).count()
    db.session.commit()
    log_action("CREATE" if not ward_id else "UPDATE", "ipd",
               record_id=w.id, record_type="Ward", new_value={"name": w.name})
    flash(f"Ward '{w.name}' saved with {bed_count} new beds.", "success")
    return redirect(url_for("ipd.index", tab="beds"))


# ── Available beds AJAX ───────────────────────────────────────────────────

@ipd_bp.route("/available-beds")
@login_required
def available_beds():
    branch_id = current_user.branch_id
    ward_id   = request.args.get("ward_id", type=int)
    q = Bed.query.filter_by(status="available", is_active=True, is_deleted=False)
    if branch_id:
        q = q.filter_by(branch_id=branch_id)
    if ward_id:
        q = q.filter_by(ward_id=ward_id)
    beds = q.order_by(Bed.bed_number).all()
    return jsonify([{
        "id": b.id,
        "number": b.bed_number,
        "type": b.bed_type or "standard",
        "ward": b.ward.name if b.ward else "",
    } for b in beds])
