# MediCore - app/blueprints/radiology/routes.py
# Radiology: Investigation master, orders, report entry.

from datetime import date, datetime, timezone
from flask import (Blueprint, render_template, redirect, url_for,
                   request, flash, jsonify)
from flask_login import login_required, current_user
from app.extensions import db
from app.models.radiology import InvestigationMaster, RadiologyOrder, RadiologyReport
from app.models.patients import Patient
from app.models.opd import Doctor
from app.models.foundation import Branch
from app.utils.decorators import require_permission
from app.utils.audit import log_action

radiology_bp = Blueprint("radiology", __name__)


@radiology_bp.route("/")
@login_required
@require_permission("radiology", "view")
def index():
    tab       = request.args.get("tab", "orders")
    branch_id = current_user.branch_id
    page      = request.args.get("page", 1, type=int)
    today     = date.today()

    investigations = InvestigationMaster.query.filter_by(
        branch_id=branch_id, is_active=True, is_deleted=False).all()
    doctors = Doctor.query.filter_by(branch_id=branch_id, is_active=True, is_deleted=False).all()

    if tab == "investigations":
        inv_page = InvestigationMaster.query.filter(
            InvestigationMaster.is_deleted == False,
            *([InvestigationMaster.branch_id == branch_id] if branch_id else []),
        ).paginate(page=page, per_page=25)
        return render_template("radiology/index.html", tab=tab,
                               investigations=inv_page, doctors=doctors)

    elif tab == "reports":
        q = RadiologyOrder.query.filter(
            RadiologyOrder.status.in_(["in_progress", "ordered"]),
            RadiologyOrder.is_deleted == False,
            *([RadiologyOrder.branch_id == branch_id] if branch_id else []),
        )
        orders = q.order_by(RadiologyOrder.ordered_at).paginate(page=page, per_page=25)
        return render_template("radiology/index.html", tab=tab, orders=orders,
                               investigations=investigations, doctors=doctors)

    # Default: orders list
    q = RadiologyOrder.query.filter(RadiologyOrder.is_deleted == False)
    if branch_id:
        q = q.filter(RadiologyOrder.branch_id == branch_id)
    date_filter = request.args.get("date_filter", today.isoformat())
    try:
        d = datetime.strptime(date_filter, "%Y-%m-%d").date()
        q = q.filter(db.func.date(RadiologyOrder.ordered_at) == d)
    except ValueError:
        pass
    orders = q.order_by(RadiologyOrder.ordered_at.desc()).paginate(page=page, per_page=25)
    return render_template("radiology/index.html", tab=tab, orders=orders,
                           investigations=investigations, doctors=doctors,
                           date_filter=date_filter, today=today)


@radiology_bp.route("/order/save", methods=["POST"])
@login_required
@require_permission("radiology", "create")
def order_save():
    branch_id      = current_user.branch_id
    branch         = Branch.query.get(branch_id) if branch_id else None
    patient_id     = int(request.form.get("patient_id"))
    inv_id         = int(request.form.get("investigation_id"))
    investigation  = InvestigationMaster.query.get_or_404(inv_id)
    try:
        order_num = f"{branch.code if branch else 'GEN'}-RAD-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        order = RadiologyOrder(
            branch_id=branch_id, patient_id=patient_id,
            doctor_id=request.form.get("doctor_id") or None,
            investigation_id=inv_id,
            order_number=order_num,
            priority=request.form.get("priority", "routine"),
            clinical_info=request.form.get("clinical_info", "").strip(),
            price=float(investigation.price or 0),
            status="ordered",
        )
        db.session.add(order)
        db.session.commit()
        log_action("CREATE", "radiology", record_id=order.id, record_type="RadiologyOrder")
        flash(f"Radiology order {order_num} created.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "danger")
    return redirect(url_for("radiology.index"))


@radiology_bp.route("/order/<int:order_id>/report", methods=["GET", "POST"])
@login_required
@require_permission("radiology", "create")
def enter_report(order_id):
    order   = RadiologyOrder.query.get_or_404(order_id)
    patient = Patient.query.get(order.patient_id)
    report  = RadiologyReport.query.filter_by(order_id=order_id, is_deleted=False).first()

    if request.method == "POST":
        try:
            if not report:
                report = RadiologyReport(order_id=order_id, patient_id=order.patient_id,
                                         reported_by=current_user.id)
                db.session.add(report)
            report.findings   = request.form.get("findings", "").strip()
            report.impression = request.form.get("impression", "").strip()
            report.reported_at = datetime.now(timezone.utc)
            order.status = "reported"
            db.session.commit()
            log_action("CREATE" if not report.id else "UPDATE", "radiology",
                       record_id=order_id, record_type="RadiologyReport")
            flash("Report saved.", "success")
            return redirect(url_for("radiology.index", tab="orders"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error: {e}", "danger")

    return render_template("radiology/report_form.html",
                           order=order, patient=patient, report=report)


@radiology_bp.route("/investigation/save", methods=["POST"])
@login_required
@require_permission("radiology", "create")
def investigation_save():
    branch_id = current_user.branch_id
    inv_id    = request.form.get("inv_id")
    if inv_id:
        inv = InvestigationMaster.query.get_or_404(int(inv_id))
    else:
        inv = InvestigationMaster(branch_id=branch_id)
        db.session.add(inv)
    inv.code        = request.form.get("code", "").strip() or None
    inv.name        = request.form.get("name", "").strip()
    inv.category    = request.form.get("category", "xray")
    inv.price       = float(request.form.get("price", 0) or 0)
    inv.preparation = request.form.get("preparation", "").strip() or None
    db.session.commit()
    flash(f"Investigation '{inv.name}' saved.", "success")
    return redirect(url_for("radiology.index", tab="investigations"))
