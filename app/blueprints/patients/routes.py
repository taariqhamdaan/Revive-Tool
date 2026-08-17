# Rivive - app/blueprints/patients/routes.py
# Patient management: register, view, edit, search, bulk upload, download template.
# Logic summary:
#   - List: paginated, filtered by name/phone/UHID, branch-scoped
#   - Register: form with auto UHID generation, allergy and contact sub-forms
#   - View: full profile with history, allergies, appointments, admissions, bills
#   - Edit: same form, pre-populated
#   - Bulk upload: Excel file → process → show result report
#   - Download template: returns blank Excel for bulk upload

import os
from datetime import datetime, timezone
from flask import (Blueprint, render_template, redirect, url_for,
                   request, flash, send_file, current_app, jsonify)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models.patients import Patient, PatientContact, PatientAllergy, PatientHistory, PatientDocument
from app.models.foundation import Branch
from app.utils.decorators import require_permission
from app.utils.audit import log_action
from app.utils.generators import generate_uhid
from app.utils.bulk_upload import process_bulk_upload, generate_upload_template

patients_bp = Blueprint("patients", __name__)


# ── List ──────────────────────────────────────────────────────────────────────

@patients_bp.route("/")
@login_required
@require_permission("patients", "view")
def index():
    page     = request.args.get("page", 1, type=int)
    search   = request.args.get("q", "").strip()
    per_page = current_app.config.get("RECORDS_PER_PAGE", 25)

    query = Patient.query.filter(Patient.is_deleted == False)

    if not current_user.is_superadmin:
        query = query.filter(Patient.branch_id == current_user.branch_id)

    if search:
        like = f"%{search}%"
        query = query.filter(
            db.or_(
                Patient.first_name.ilike(like),
                Patient.last_name.ilike(like),
                Patient.uhid.ilike(like),
                Patient.phone.ilike(like),
            )
        )

    patients = query.order_by(Patient.created_at.desc()).paginate(page=page, per_page=per_page)
    return render_template("patients/index.html", patients=patients, search=search)


# ── Register ──────────────────────────────────────────────────────────────────

@patients_bp.route("/register", methods=["GET", "POST"])
@login_required
@require_permission("patients", "create")
def register():
    branch_id = current_user.branch_id
    branch    = Branch.query.get(branch_id) if branch_id else None

    if request.method == "POST":
        try:
            uhid = generate_uhid(branch.code if branch else "GEN")

            patient = Patient(
                branch_id   = branch_id,
                uhid        = uhid,
                first_name  = request.form.get("first_name", "").strip(),
                last_name   = request.form.get("last_name", "").strip() or None,
                first_name_ta = request.form.get("first_name_ta", "").strip() or None,
                date_of_birth = _parse_date(request.form.get("date_of_birth")),
                age_years   = _safe_int(request.form.get("age_years")),
                gender      = request.form.get("gender"),
                blood_group = request.form.get("blood_group") or None,
                marital_status = request.form.get("marital_status") or None,
                religion    = request.form.get("religion") or None,
                occupation  = request.form.get("occupation") or None,
                phone       = request.form.get("phone", "").strip(),
                phone_alt   = request.form.get("phone_alt", "").strip() or None,
                email       = request.form.get("email", "").strip() or None,
                address     = request.form.get("address", "").strip() or None,
                city        = request.form.get("city", "").strip() or None,
                state       = request.form.get("state", "").strip() or None,
                pincode     = request.form.get("pincode", "").strip() or None,
                abha_number = request.form.get("abha_number", "").strip() or None,
                referred_by = request.form.get("referred_by", "").strip() or None,
                registration_type = request.form.get("registration_type", "walkin"),
                created_by  = current_user.id,
            )

            # Aadhaar — encrypt and mask
            aadhaar = request.form.get("aadhaar", "").strip()
            if aadhaar:
                from app.utils.encryption import encrypt, mask_aadhaar
                patient.aadhaar_encrypted = encrypt(aadhaar)
                patient.aadhaar_masked    = mask_aadhaar(aadhaar)

            db.session.add(patient)
            db.session.flush()

            # Emergency contact
            contact_name = request.form.get("contact_name", "").strip()
            contact_phone = request.form.get("contact_phone", "").strip()
            if contact_name and contact_phone:
                contact = PatientContact(
                    patient_id=patient.id,
                    name=contact_name,
                    relationship=request.form.get("contact_relationship", ""),
                    phone=contact_phone,
                    is_primary=True,
                )
                db.session.add(contact)

            # Known allergy
            allergy = request.form.get("allergy", "").strip()
            if allergy:
                pa = PatientAllergy(
                    patient_id=patient.id,
                    allergy_type=request.form.get("allergy_type", "Drug"),
                    allergen=allergy,
                    severity=request.form.get("allergy_severity", "Mild"),
                    noted_by=current_user.id,
                )
                db.session.add(pa)

            db.session.commit()
            log_action("CREATE", "patients", record_id=patient.id, record_type="Patient",
                       new_value={"uhid": patient.uhid, "name": patient.full_name})
            flash(f"Patient registered successfully. UHID: {uhid}", "success")
            return redirect(url_for("patients.view", patient_id=patient.id))

        except Exception as e:
            db.session.rollback()
            flash(f"Error registering patient: {e}", "danger")

    return render_template("patients/register.html", branch=branch)


# ── View ──────────────────────────────────────────────────────────────────────

@patients_bp.route("/<int:patient_id>")
@login_required
@require_permission("patients", "view")
def view(patient_id):
    patient = _get_patient_or_404(patient_id)
    return render_template(
        "patients/view.html",
        patient=patient,
        contacts=patient.contacts.filter_by(is_deleted=False).all(),
        allergies=patient.allergies.filter_by(is_deleted=False, is_active=True).all(),
        history=patient.history.filter_by(is_deleted=False).order_by(db.text("noted_at DESC")).all(),
        documents=patient.documents.filter_by(is_deleted=False).all(),
        appointments=patient.appointments[:10],
        insurance=patient.insurance_list.filter_by(is_deleted=False).all(),
    )


# ── Edit ──────────────────────────────────────────────────────────────────────

@patients_bp.route("/<int:patient_id>/edit", methods=["GET", "POST"])
@login_required
@require_permission("patients", "edit")
def edit(patient_id):
    patient = _get_patient_or_404(patient_id)

    if request.method == "POST":
        try:
            old = patient.to_dict()
            patient.first_name   = request.form.get("first_name", "").strip()
            patient.last_name    = request.form.get("last_name", "").strip() or None
            patient.gender       = request.form.get("gender")
            patient.date_of_birth = _parse_date(request.form.get("date_of_birth"))
            patient.blood_group  = request.form.get("blood_group") or None
            patient.phone        = request.form.get("phone", "").strip()
            patient.phone_alt    = request.form.get("phone_alt", "").strip() or None
            patient.email        = request.form.get("email", "").strip() or None
            patient.address      = request.form.get("address", "").strip() or None
            patient.city         = request.form.get("city", "").strip() or None
            patient.state        = request.form.get("state", "").strip() or None
            patient.pincode      = request.form.get("pincode", "").strip() or None
            patient.abha_number  = request.form.get("abha_number", "").strip() or None
            patient.occupation   = request.form.get("occupation", "").strip() or None

            db.session.commit()
            log_action("UPDATE", "patients", record_id=patient.id, record_type="Patient",
                       old_value=old, new_value=patient.to_dict())
            flash("Patient record updated.", "success")
            return redirect(url_for("patients.view", patient_id=patient.id))

        except Exception as e:
            db.session.rollback()
            flash(f"Update failed: {e}", "danger")

    return render_template("patients/edit.html", patient=patient)


# ── Soft Delete ───────────────────────────────────────────────────────────────

@patients_bp.route("/<int:patient_id>/delete", methods=["POST"])
@login_required
@require_permission("patients", "delete")
def delete(patient_id):
    patient = _get_patient_or_404(patient_id)
    patient.is_deleted = True
    db.session.commit()
    log_action("DELETE", "patients", record_id=patient.id, record_type="Patient",
               notes=f"Soft deleted by {current_user.username}")
    flash("Patient record deactivated.", "info")
    return redirect(url_for("patients.index"))


# ── Bulk Upload ───────────────────────────────────────────────────────────────

@patients_bp.route("/bulk-upload", methods=["GET", "POST"])
@login_required
@require_permission("patients", "create")
def bulk_upload():
    if request.method == "POST":
        file = request.files.get("file")
        if not file or not file.filename:
            flash("No file selected.", "danger")
            return redirect(request.url)

        ext = file.filename.rsplit(".", 1)[-1].lower()
        if ext not in ("xlsx", "xls", "csv"):
            flash("Only xlsx, xls, csv files are allowed.", "danger")
            return redirect(request.url)

        filename = secure_filename(f"bulk_patients_{datetime.now().strftime('%Y%m%d%H%M%S')}.{ext}")
        save_path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
        file.save(save_path)

        result = process_bulk_upload(save_path, "patients", current_user.branch_id, current_user.id)
        os.remove(save_path)

        return render_template("patients/bulk_result.html", result=result)

    return render_template("patients/bulk_upload.html")


# ── Download Template ─────────────────────────────────────────────────────────

@patients_bp.route("/download-template")
@login_required
def download_template():
    import io
    data = generate_upload_template("patients")
    return send_file(
        io.BytesIO(data),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="Patient_Upload_Template.xlsx",
    )


# ── AJAX Search (for appointment/billing quick-pick) ─────────────────────────

@patients_bp.route("/search-json")
@login_required
def search_json():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])

    like = f"%{q}%"
    query = Patient.query.filter(
        Patient.is_deleted == False,
        db.or_(
            Patient.first_name.ilike(like),
            Patient.last_name.ilike(like),
            Patient.uhid.ilike(like),
            Patient.phone.ilike(like),
        )
    )
    if not current_user.is_superadmin:
        query = query.filter(Patient.branch_id == current_user.branch_id)

    results = [{
        "id": p.id,
        "uhid": p.uhid,
        "name": p.full_name,
        "phone": p.phone,
        "age": p.age_years or "",
        "gender": p.gender or "",
    } for p in query.limit(10).all()]

    return jsonify(results)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_patient_or_404(patient_id):
    from flask import abort
    patient = Patient.query.filter_by(id=patient_id, is_deleted=False).first()
    if not patient:
        abort(404)
    if not current_user.is_superadmin and patient.branch_id != current_user.branch_id:
        abort(403)
    return patient


def _parse_date(value):
    from datetime import date
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
