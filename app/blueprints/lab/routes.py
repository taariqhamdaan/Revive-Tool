# Revive - app/blueprints/lab/routes.py
# Laboratory: test master, panels, lab orders, sample collection,
# result entry, result verification, report generation.
# Logic summary per tab:
#   tests      — test master CRUD + bulk upload
#   orders     — lab orders list, filter by status/date
#   results    — result entry per order item
#   pending    — sample collected but awaiting results
#   critical   — critical values flagged
#   reports    — generated reports viewer

from datetime import date, datetime, timezone
from flask import (Blueprint, render_template, redirect, url_for,
                   request, flash, jsonify, send_file, current_app)
from flask_login import login_required, current_user
from app.extensions import db
from app.models.lab import (TestMaster, TestCategory, TestPanel, TestPanelItem,
                             LabOrder, LabOrderItem, LabResult)
from app.models.patients import Patient
from app.models.opd import Doctor
from app.models.foundation import Branch
from app.utils.decorators import require_permission
from app.utils.audit import log_action
from app.utils.bulk_upload import process_bulk_upload, generate_upload_template
import os
from werkzeug.utils import secure_filename

lab_bp = Blueprint("lab", __name__)


@lab_bp.route("/")
@login_required
@require_permission("lab", "view")
def index():
    tab       = request.args.get("tab", "orders")
    branch_id = current_user.branch_id
    page      = request.args.get("page", 1, type=int)
    search    = request.args.get("q", "").strip()
    today     = date.today()

    if tab == "tests":
        return _tests_view(branch_id, search, page)
    elif tab == "results":
        return _results_view(branch_id, page)
    elif tab == "pending":
        return _pending_view(branch_id)
    elif tab == "critical":
        return _critical_view(branch_id)

    # Default: orders
    q = LabOrder.query.filter(LabOrder.is_deleted == False)
    if branch_id:
        q = q.filter(LabOrder.branch_id == branch_id)
    if search:
        like = f"%{search}%"
        q = q.join(Patient).filter(
            db.or_(Patient.first_name.ilike(like), Patient.uhid.ilike(like),
                   LabOrder.order_number.ilike(like))
        )
    date_filter = request.args.get("date_filter", today.isoformat())
    if date_filter:
        try:
            d = datetime.strptime(date_filter, "%Y-%m-%d").date()
            q = q.filter(db.func.date(LabOrder.ordered_at) == d)
        except ValueError:
            pass

    orders = q.order_by(LabOrder.ordered_at.desc()).paginate(page=page, per_page=25)
    tests  = TestMaster.query.filter_by(branch_id=branch_id, is_deleted=False, is_active=True).all()
    panels = TestPanel.query.filter_by(branch_id=branch_id, is_deleted=False, is_active=True).all()
    doctors = Doctor.query.filter_by(branch_id=branch_id, is_active=True, is_deleted=False).all()

    return render_template("lab/index.html", tab=tab, orders=orders,
                           tests=tests, panels=panels, doctors=doctors,
                           search=search, date_filter=date_filter, today=today)


def _tests_view(branch_id, search, page):
    q = TestMaster.query.filter(TestMaster.is_deleted == False)
    if branch_id:
        q = q.filter(TestMaster.branch_id == branch_id)
    if search:
        like = f"%{search}%"
        q = q.filter(db.or_(TestMaster.name.ilike(like), TestMaster.test_code.ilike(like)))
    tests = q.order_by(TestMaster.name).paginate(page=page, per_page=25)
    categories = TestCategory.query.filter_by(branch_id=branch_id, is_deleted=False).all()
    return render_template("lab/index.html", tab="tests", tests=tests,
                           categories=categories, search=search)


def _results_view(branch_id, page):
    q = LabOrder.query.filter(
        LabOrder.status.in_(["sample_collected", "processing"]),
        LabOrder.is_deleted == False,
    )
    if branch_id:
        q = q.filter(LabOrder.branch_id == branch_id)
    orders = q.order_by(LabOrder.ordered_at).paginate(page=page, per_page=25)
    return render_template("lab/index.html", tab="results", orders=orders)


def _pending_view(branch_id):
    q = LabOrder.query.filter(
        LabOrder.status == "ordered",
        LabOrder.is_deleted == False,
    )
    if branch_id:
        q = q.filter(LabOrder.branch_id == branch_id)
    orders = q.order_by(LabOrder.ordered_at).all()
    return render_template("lab/index.html", tab="pending", orders=orders)


def _critical_view(branch_id):
    q = LabResult.query.filter(
        LabResult.is_critical == True,
        LabResult.is_deleted == False,
    )
    results = q.order_by(LabResult.resulted_at.desc()).limit(100).all()
    return render_template("lab/index.html", tab="critical", results=results)


# ── Create Lab Order ──────────────────────────────────────────────────────

@lab_bp.route("/order/save", methods=["POST"])
@login_required
@require_permission("lab", "create")
def order_save():
    branch_id  = current_user.branch_id
    branch     = Branch.query.get(branch_id) if branch_id else None
    patient_id = int(request.form.get("patient_id"))
    doctor_id  = request.form.get("doctor_id") or None
    priority   = request.form.get("priority", "routine")
    clinical   = request.form.get("clinical_info", "").strip()

    try:
        from app.utils.generators import generate_order_number
        order_num = f"{branch.code if branch else 'GEN'}-LAB-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        order = LabOrder(
            branch_id=branch_id,
            patient_id=patient_id,
            doctor_id=int(doctor_id) if doctor_id else None,
            order_number=order_num,
            priority=priority,
            clinical_info=clinical,
            status="ordered",
        )
        db.session.add(order)
        db.session.flush()

        test_ids  = request.form.getlist("test_id[]")
        panel_ids = request.form.getlist("panel_id[]")
        total     = 0

        for tid in test_ids:
            if not tid: continue
            test = TestMaster.query.get(int(tid))
            if not test: continue
            item = LabOrderItem(
                order_id=order.id, test_id=int(tid),
                status="ordered", price=float(test.price or 0),
            )
            db.session.add(item)
            total += float(test.price or 0)

        for pid in panel_ids:
            if not pid: continue
            panel = TestPanel.query.get(int(pid))
            if not panel: continue
            for pitem in panel.tests.all():
                item = LabOrderItem(
                    order_id=order.id, test_id=pitem.test_id,
                    panel_id=int(pid), status="ordered",
                    price=float(panel.price or 0) / max(1, panel.tests.count()),
                )
                db.session.add(item)
            total += float(panel.price or 0)

        order.total_amount = total
        db.session.commit()
        log_action("CREATE", "lab", record_id=order.id, record_type="LabOrder",
                   new_value={"order_number": order_num, "patient_id": patient_id})
        flash(f"Lab order {order_num} created.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "danger")

    return redirect(url_for("lab.index", tab="orders"))


# ── Sample Collection ─────────────────────────────────────────────────────

@lab_bp.route("/order/<int:order_id>/collect", methods=["POST"])
@login_required
@require_permission("lab", "edit")
def collect_sample(order_id):
    order = LabOrder.query.get_or_404(order_id)
    order.status = "sample_collected"
    LabOrderItem.query.filter_by(order_id=order_id, status="ordered").update(
        {"status": "sample_collected", "collected_at": datetime.now(timezone.utc),
         "collected_by": current_user.id}
    )
    db.session.commit()
    log_action("UPDATE", "lab", record_id=order_id, record_type="LabOrder",
               new_value={"status": "sample_collected"})
    flash("Sample collected.", "success")
    return redirect(url_for("lab.index", tab="pending"))


# ── Result Entry ──────────────────────────────────────────────────────────

@lab_bp.route("/order/<int:order_id>/results", methods=["GET", "POST"])
@login_required
@require_permission("lab", "edit")
def enter_results(order_id):
    order = LabOrder.query.get_or_404(order_id)
    items = order.items.filter_by(is_deleted=False).all()
    patient = Patient.query.get(order.patient_id)

    if request.method == "POST":
        try:
            for item in items:
                val     = request.form.get(f"result_{item.id}", "").strip()
                remarks = request.form.get(f"remarks_{item.id}", "").strip()
                if not val:
                    continue

                test = TestMaster.query.get(item.test_id)
                is_critical = False
                is_abnormal = False
                flag        = ""

                # Check critical values
                try:
                    num_val = float(val)
                    if test and test.critical_low and num_val < float(test.critical_low):
                        is_critical = True; is_abnormal = True; flag = "LL"
                    elif test and test.critical_high and num_val > float(test.critical_high):
                        is_critical = True; is_abnormal = True; flag = "HH"
                except (ValueError, TypeError):
                    pass

                existing = LabResult.query.filter_by(
                    order_item_id=item.id, is_deleted=False).first()

                if existing:
                    existing.result_value = val
                    existing.remarks      = remarks
                    existing.is_critical  = is_critical
                    existing.is_abnormal  = is_abnormal
                    existing.abnormal_flag = flag
                    existing.resulted_at  = datetime.now(timezone.utc)
                    existing.resulted_by  = current_user.id
                else:
                    result = LabResult(
                        order_item_id=item.id,
                        order_id=order.id,
                        patient_id=order.patient_id,
                        test_id=item.test_id,
                        result_value=val,
                        result_unit=test.unit if test else "",
                        reference_range=test.normal_range if test else "",
                        is_critical=is_critical,
                        is_abnormal=is_abnormal,
                        abnormal_flag=flag,
                        remarks=remarks,
                        resulted_by=current_user.id,
                    )
                    db.session.add(result)
                item.status = "resulted"

            order.status = "resulted"
            db.session.commit()

            # Send email if configured
            if patient and patient.email:
                try:
                    from app.utils.email import send_lab_report_ready
                    branch = Branch.query.get(order.branch_id)
                    send_lab_report_ready(patient, order, branch)
                except Exception:
                    pass

            log_action("UPDATE", "lab", record_id=order.id, record_type="LabOrder",
                       new_value={"status": "resulted"})
            flash("Results saved successfully.", "success")
            return redirect(url_for("lab.index", tab="results"))

        except Exception as e:
            db.session.rollback()
            flash(f"Save failed: {e}", "danger")

    return render_template("lab/enter_results.html",
                           order=order, items=items, patient=patient)


# ── Verify Results ────────────────────────────────────────────────────────

@lab_bp.route("/order/<int:order_id>/verify", methods=["POST"])
@login_required
@require_permission("lab", "verify")
def verify_results(order_id):
    order = LabOrder.query.get_or_404(order_id)
    LabResult.query.filter_by(order_id=order_id, is_deleted=False).update({
        "verified_by": current_user.id,
        "verified_at": datetime.now(timezone.utc),
    })
    order.status = "reported"
    db.session.commit()
    log_action("UPDATE", "lab", record_id=order_id, record_type="LabOrder",
               new_value={"status": "reported"})
    flash("Results verified and report ready.", "success")
    return redirect(url_for("lab.view_report", order_id=order_id))


# ── View Report ───────────────────────────────────────────────────────────

@lab_bp.route("/order/<int:order_id>/report")
@login_required
@require_permission("lab", "view")
def view_report(order_id):
    order   = LabOrder.query.get_or_404(order_id)
    items   = order.items.filter_by(is_deleted=False).all()
    results = {r.order_item_id: r for r in
               LabResult.query.filter_by(order_id=order_id, is_deleted=False).all()}
    patient = Patient.query.get(order.patient_id)
    doctor  = Doctor.query.get(order.doctor_id) if order.doctor_id else None
    branch  = Branch.query.get(order.branch_id) if order.branch_id else None
    return render_template("lab/report.html",
                           order=order, items=items, results=results,
                           patient=patient, doctor=doctor, branch=branch)


# ── Test CRUD ─────────────────────────────────────────────────────────────

@lab_bp.route("/test/save", methods=["POST"])
@login_required
@require_permission("lab", "create")
def test_save():
    branch_id = current_user.branch_id
    test_id   = request.form.get("test_id")

    if test_id:
        t = TestMaster.query.get_or_404(int(test_id))
    else:
        t = TestMaster(branch_id=branch_id)
        db.session.add(t)

    t.test_code     = request.form.get("test_code", "").strip() or None
    t.name          = request.form.get("name", "").strip()
    t.category_id   = request.form.get("category_id") or None
    t.sample_type   = request.form.get("sample_type", "").strip() or None
    t.method        = request.form.get("method", "").strip() or None
    t.unit          = request.form.get("unit", "").strip() or None
    t.normal_range  = request.form.get("normal_range", "").strip() or None
    t.male_range    = request.form.get("male_range", "").strip() or None
    t.female_range  = request.form.get("female_range", "").strip() or None
    t.critical_low  = request.form.get("critical_low") or None
    t.critical_high = request.form.get("critical_high") or None
    t.turnaround_hrs = int(request.form.get("turnaround_hrs", 24) or 24)
    t.price         = float(request.form.get("price", 0) or 0)
    t.is_active     = True

    db.session.commit()
    log_action("CREATE" if not test_id else "UPDATE", "lab",
               record_id=t.id, record_type="TestMaster")
    flash(f"Test '{t.name}' saved.", "success")
    return redirect(url_for("lab.index", tab="tests"))


# ── Bulk Upload ───────────────────────────────────────────────────────────

@lab_bp.route("/bulk-upload", methods=["GET", "POST"])
@login_required
@require_permission("lab", "create")
def bulk_upload():
    if request.method == "POST":
        file = request.files.get("file")
        if not file or not file.filename:
            flash("No file selected.", "danger")
            return redirect(request.url)
        ext = file.filename.rsplit(".", 1)[-1].lower()
        fname = secure_filename(f"bulk_tests_{datetime.now().strftime('%Y%m%d%H%M%S')}.{ext}")
        spath = os.path.join(current_app.config["UPLOAD_FOLDER"], fname)
        file.save(spath)
        result = process_bulk_upload(spath, "tests", current_user.branch_id, current_user.id)
        os.remove(spath)
        return render_template("lab/bulk_result.html", result=result)
    return render_template("lab/bulk_upload.html")


@lab_bp.route("/download-template")
@login_required
def download_template():
    import io
    data = generate_upload_template("tests")
    return send_file(io.BytesIO(data),
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name="Test_Upload_Template.xlsx")


# ── Test search JSON ──────────────────────────────────────────────────────

@lab_bp.route("/test-search")
@login_required
def test_search():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    like = f"%{q}%"
    tests = TestMaster.query.filter(
        TestMaster.is_deleted == False, TestMaster.is_active == True,
        db.or_(TestMaster.name.ilike(like), TestMaster.test_code.ilike(like)),
        *([TestMaster.branch_id == current_user.branch_id] if current_user.branch_id else []),
    ).limit(10).all()
    return jsonify([{
        "id": t.id, "name": t.name,
        "code": t.test_code or "",
        "sample": t.sample_type or "",
        "price": float(t.price or 0),
        "unit": t.unit or "",
        "range": t.normal_range or "",
    } for t in tests])
