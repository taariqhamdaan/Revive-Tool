# Revive - app/blueprints/insurance/routes.py
# Insurance & TPA: TPA master, pre-auth, claim tracking, settlement.

from datetime import date, datetime, timezone
from flask import (Blueprint, render_template, redirect, url_for,
                   request, flash, jsonify)
from flask_login import login_required, current_user
from app.extensions import db
from app.models.billing import TPAMaster, InsuranceClaim, BillMaster
from app.models.patients import Patient, PatientInsurance
from app.utils.decorators import require_permission
from app.utils.audit import log_action

insurance_bp = Blueprint("insurance", __name__)


@insurance_bp.route("/")
@login_required
@require_permission("insurance", "view")
def index():
    tab       = request.args.get("tab", "claims")
    branch_id = current_user.branch_id
    page      = request.args.get("page", 1, type=int)

    tpas = TPAMaster.query.filter(
        db.or_(TPAMaster.branch_id == branch_id, TPAMaster.branch_id == None),
        TPAMaster.is_deleted == False,
    ).order_by(TPAMaster.name).all()

    if tab == "tpa":
        return render_template("insurance/index.html", tab=tab, tpas=tpas)

    elif tab == "patients":
        ins_list = PatientInsurance.query.join(Patient).filter(
            Patient.branch_id == branch_id if branch_id else True,
            PatientInsurance.is_deleted == False,
            PatientInsurance.is_active == True,
        ).order_by(PatientInsurance.valid_to).paginate(page=page, per_page=25)
        return render_template("insurance/index.html", tab=tab, ins_list=ins_list, tpas=tpas)

    # Default: claims
    q = InsuranceClaim.query.filter(InsuranceClaim.is_deleted == False)
    if branch_id:
        q = q.filter(InsuranceClaim.branch_id == branch_id)
    status_filter = request.args.get("status", "")
    if status_filter:
        q = q.filter(InsuranceClaim.status == status_filter)
    claims = q.order_by(InsuranceClaim.created_at.desc()).paginate(page=page, per_page=25)

    return render_template("insurance/index.html", tab=tab, claims=claims,
                           tpas=tpas, status_filter=status_filter)


@insurance_bp.route("/tpa/save", methods=["POST"])
@login_required
@require_permission("insurance", "create")
def tpa_save():
    tpa_id = request.form.get("tpa_id")
    if tpa_id:
        t = TPAMaster.query.get_or_404(int(tpa_id))
    else:
        t = TPAMaster()
        db.session.add(t)
    t.name         = request.form.get("name", "").strip()
    t.code         = request.form.get("code", "").strip() or None
    t.type         = request.form.get("type", "tpa")
    t.contact_name = request.form.get("contact_name", "").strip() or None
    t.phone        = request.form.get("phone", "").strip() or None
    t.email        = request.form.get("email", "").strip() or None
    t.claim_email  = request.form.get("claim_email", "").strip() or None
    t.portal_url   = request.form.get("portal_url", "").strip() or None
    db.session.commit()
    log_action("CREATE" if not tpa_id else "UPDATE", "insurance",
               record_id=t.id, record_type="TPAMaster")
    flash(f"TPA '{t.name}' saved.", "success")
    return redirect(url_for("insurance.index", tab="tpa"))


@insurance_bp.route("/claim/update/<int:claim_id>", methods=["POST"])
@login_required
@require_permission("insurance", "edit")
def claim_update(claim_id):
    claim = InsuranceClaim.query.get_or_404(claim_id)
    action = request.form.get("action", "")
    if action == "approve":
        claim.status          = "approved"
        claim.approved_amount = float(request.form.get("approved_amount", 0) or 0)
    elif action == "reject":
        claim.status           = "rejected"
        claim.rejection_reason = request.form.get("rejection_reason", "")
    elif action == "settle":
        claim.status         = "settled"
        claim.settled_amount = float(request.form.get("settled_amount", 0) or 0)
        claim.settled_at     = datetime.now(timezone.utc)
    db.session.commit()
    log_action("UPDATE", "insurance", record_id=claim_id, record_type="InsuranceClaim",
               new_value={"status": claim.status})
    flash(f"Claim {action}d.", "success")
    return redirect(url_for("insurance.index", tab="claims"))
