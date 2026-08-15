# Rivive SCH - app/blueprints/lab/routes.py  v4.2
# 6 stages + Settings (test master CRUD with reference ranges)

from datetime import datetime, timezone, date
from decimal import Decimal
from flask import (Blueprint, render_template, redirect, url_for,
                   request, flash, jsonify)
from flask_login import login_required, current_user
from sqlalchemy import func, or_
from app.extensions import db
from app.models.lab import (TestMaster, LabCategory, LabOrder, LabOrderItem,
                             SampleCollection, LabResult, LabApproval)

lab_bp = Blueprint("lab", __name__)

# ── helpers ──────────────────────────────────────────────────────────

def _bid():
    return current_user.branch_id

def _order_no(branch_id):
    seq = LabOrder.query.filter_by(branch_id=branch_id).count() + 1
    return f"LAB/{date.today().strftime('%y%m')}/{seq:04d}"

def _bill_no(branch_id):
    from app.models.foundation import Bill
    seq = Bill.query.filter_by(branch_id=branch_id).count() + 1
    return f"LB/{date.today().strftime('%y')}/{seq:04d}"

def _phlebotomists(branch_id):
    from app.models.foundation import User, Role
    role = Role.query.filter(Role.name.ilike("%phlebotomist%")).first()
    if role:
        return User.query.filter_by(role_id=role.id, branch_id=branch_id,
                                    is_active=True).all()
    return User.query.filter_by(branch_id=branch_id, is_active=True).limit(30).all()

# ── MAIN TABBED INDEX ─────────────────────────────────────────────────

@lab_bp.route("/")
@login_required
def index():
    tab = request.args.get("tab", "registration")
    bid = _bid()
    today = date.today()
    page  = request.args.get("page", 1, type=int)

    if tab == "registration":
        q   = request.args.get("q","").strip()
        qry = LabOrder.query.filter(
            LabOrder.branch_id == bid,
            LabOrder.is_deleted == False,
            func.date(LabOrder.ordered_at) == today,
        )
        if q:
            from app.models.foundation import Patient
            pids = [p.id for p in Patient.query.filter(
                or_(Patient.full_name.ilike(f"%{q}%"),
                    Patient.uhid.ilike(f"%{q}%"))).all()]
            qry = qry.filter(LabOrder.patient_id.in_(pids))
        orders = qry.order_by(LabOrder.ordered_at.desc()).paginate(page=page, per_page=30)
        return render_template("lab/index.html", tab=tab, orders=orders,
                               search=q, today=today)

    elif tab == "collection":
        orders = LabOrder.query.filter_by(branch_id=bid, status="ordered",
                                          is_deleted=False)\
                               .order_by(LabOrder.priority.desc(),
                                         LabOrder.ordered_at).all()
        phlebotomists = _phlebotomists(bid)
        return render_template("lab/index.html", tab=tab, orders=orders,
                               phlebotomists=phlebotomists, today=today)

    elif tab == "results":
        orders = LabOrder.query.filter_by(branch_id=bid, status="sample_collected",
                                          is_deleted=False)\
                               .order_by(LabOrder.ordered_at)\
                               .paginate(page=page, per_page=25)
        return render_template("lab/index.html", tab=tab, orders=orders, today=today)

    elif tab == "approval":
        orders = LabOrder.query.filter_by(branch_id=bid, status="resulted",
                                          is_deleted=False)\
                               .order_by(LabOrder.ordered_at)\
                               .paginate(page=page, per_page=25)
        return render_template("lab/index.html", tab=tab, orders=orders, today=today)

    elif tab == "pending":
        orders = LabOrder.query.filter(
            LabOrder.branch_id == bid,
            LabOrder.status.in_(["ordered","sample_collected","resulted"]),
            LabOrder.is_deleted == False,
        ).order_by(LabOrder.priority.desc(), LabOrder.ordered_at)\
         .paginate(page=page, per_page=30)
        return render_template("lab/index.html", tab=tab, orders=orders, today=today)

    elif tab == "approved":
        d_from = request.args.get("date_from", today.isoformat())
        d_to   = request.args.get("date_to",   today.isoformat())
        try:
            df = datetime.strptime(d_from, "%Y-%m-%d").date()
            dt = datetime.strptime(d_to,   "%Y-%m-%d").date()
        except ValueError:
            df = dt = today
        orders = LabOrder.query.filter(
            LabOrder.branch_id == bid,
            LabOrder.status == "approved",
            LabOrder.is_deleted == False,
            func.date(LabOrder.ordered_at).between(df, dt),
        ).order_by(LabOrder.ordered_at.desc()).paginate(page=page, per_page=30)
        return render_template("lab/index.html", tab=tab, orders=orders,
                               d_from=d_from, d_to=d_to, today=today)

    elif tab == "settings":
        subtab = request.args.get("subtab","tests")
        q      = request.args.get("q","").strip()
        if subtab == "categories":
            cats = LabCategory.query.filter_by(branch_id=bid).all()
            return render_template("lab/index.html", tab=tab, subtab=subtab,
                                   categories=cats, today=today)
        else:
            qry = TestMaster.query.filter_by(branch_id=bid, is_deleted=False)
            if q:
                qry = qry.filter(or_(TestMaster.test_name.ilike(f"%{q}%"),
                                     TestMaster.test_code.ilike(f"%{q}%")))
            tests = qry.order_by(TestMaster.test_name).paginate(page=page, per_page=25)
            cats  = LabCategory.query.filter_by(branch_id=bid, is_active=True).all()
            return render_template("lab/index.html", tab=tab, subtab=subtab,
                                   tests=tests, categories=cats, search=q, today=today)

    return redirect(url_for("lab.index", tab="registration"))

# ── STAGE 1: REGISTER ORDER ───────────────────────────────────────────

@lab_bp.route("/register", methods=["GET","POST"])
@login_required
def register_order():
    bid = _bid()
    if request.method == "POST":
        try:
            from app.models.foundation import Bill
            f          = request.form
            patient_id = int(f.get("patient_id"))
            doctor_id  = f.get("doctor_id") or None
            priority   = f.get("priority","routine")
            visit_type = f.get("visit_type","op")
            clinical   = f.get("clinical_info","").strip()

            order = LabOrder(
                branch_id=bid, patient_id=patient_id,
                doctor_id=int(doctor_id) if doctor_id else None,
                ordered_by=current_user.id,
                order_number=_order_no(bid),
                priority=priority, visit_type=visit_type,
                clinical_info=clinical, status="ordered",
            )
            db.session.add(order)
            db.session.flush()

            test_ids     = f.getlist("test_id[]")
            total_amount = Decimal("0")

            for tid in test_ids:
                if not tid: continue
                test = TestMaster.query.get(int(tid))
                if not test: continue
                gst_a = (test.price or Decimal("0")) * \
                        (test.gst_percent or Decimal("0")) / 100
                total = (test.price or Decimal("0")) + gst_a
                item  = LabOrderItem(
                    order_id=order.id, test_id=test.id, branch_id=bid,
                    test_name=test.test_name,
                    test_code=test.test_code or "",
                    sample_type=test.sample_type or "",
                    price=test.price or 0,
                    gst_percent=test.gst_percent or 0,
                    gst_amount=gst_a, total=total, status="pending",
                )
                db.session.add(item)
                total_amount += total

            order.total_amount = total_amount

            # Create Bill (module_type='lab')
            payment_mode = f.get("payment_mode","cash")
            paid_now     = Decimal(f.get("paid_amount","0") or "0")
            bill_status  = ("paid" if paid_now >= total_amount
                            else ("partial" if paid_now > 0 else "credit"))
            bill = Bill(
                branch_id=bid, patient_id=patient_id,
                doctor_id=int(doctor_id) if doctor_id else None,
                created_by=current_user.id,
                bill_number=_bill_no(bid),
                module_type="lab", bill_type="regular",
                billed_from="lab",
                subtotal=total_amount,
                gross_total=total_amount,
                payable_amount=total_amount,
                paid_amount=paid_now,
                balance_amount=total_amount - paid_now,
                received_amount=paid_now,
                payment_mode=payment_mode,
                status=bill_status,
            )
            db.session.add(bill)
            db.session.flush()

            order.bill_id        = bill.id
            order.payment_status = bill_status

            db.session.commit()
            flash(f"Order {order.order_number} registered. Bill {bill.bill_number}.", "success")
            return redirect(url_for("lab.index", tab="collection"))

        except Exception as e:
            db.session.rollback()
            flash(f"Registration failed: {e}", "danger")

    # GET
    tests      = TestMaster.query.filter_by(branch_id=bid, is_active=True,
                                             is_deleted=False).all()
    from app.models.foundation import Doctor
    doctors    = Doctor.query.filter_by(branch_id=bid, is_active=True,
                                        is_deleted=False).all()
    categories = LabCategory.query.filter_by(branch_id=bid, is_active=True).all()
    return render_template("lab/register.html",
        tests=tests, doctors=doctors, categories=categories, today=date.today())

# ── STAGE 2: SAMPLE COLLECTION ────────────────────────────────────────

@lab_bp.route("/collect/<int:order_id>", methods=["POST"])
@login_required
def collect_sample(order_id):
    order = LabOrder.query.get_or_404(order_id)
    try:
        f               = request.form
        phlebot_id      = f.get("phlebotomist_id") or None
        is_fasting      = f.get("is_fasting") == "1"
        sample_id       = f.get("sample_id","").strip()
        notes           = f.get("collection_notes","").strip()

        sc = order.sample or SampleCollection(order_id=order.id, branch_id=order.branch_id)
        if not order.sample:
            db.session.add(sc)

        sc.phlebotomist_id  = int(phlebot_id) if phlebot_id else None
        sc.collected_at     = datetime.now(timezone.utc)   # timestamp set HERE
        sc.sample_id        = sample_id
        sc.is_fasting       = is_fasting
        sc.collection_notes = notes

        order.status = "sample_collected"
        LabOrderItem.query.filter_by(order_id=order.id)\
                          .update({"status":"collected"})
        db.session.commit()
        flash(f"Sample collected for {order.order_number}.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Collection failed: {e}", "danger")
    return redirect(url_for("lab.index", tab="collection"))

# ── STAGE 3: RESULT ENTRY ────────────────────────────────────────────

@lab_bp.route("/results/<int:order_id>", methods=["GET","POST"])
@login_required
def enter_results(order_id):
    order = LabOrder.query.get_or_404(order_id)
    locked = (order.status == "approved" and order.approval
              and not order.approval.is_unlocked)

    if request.method == "POST" and not locked:
        try:
            items = order.items.filter_by(is_deleted=False).all()
            any_saved = False
            for item in items:
                val = request.form.get(f"result_{item.id}","").strip()
                rem = request.form.get(f"remarks_{item.id}","").strip()
                if not val:
                    continue

                if item.result:
                    if item.result.is_locked:
                        continue
                    res = item.result
                else:
                    res = LabResult(order_item_id=item.id, order_id=order.id,
                                    branch_id=order.branch_id,
                                    entered_by=current_user.id)
                    db.session.add(res)

                res.result_value    = val
                res.result_unit     = item.test.unit if item.test else ""
                res.reference_range = item.test.normal_range if item.test else ""
                res.remarks         = rem
                res.entered_by      = current_user.id
                res.resulted_at     = datetime.now(timezone.utc)
                if item.test:
                    res.compute_flags(item.test)

                item.status = "resulted"
                any_saved   = True

            if any_saved:
                all_done = all(i.status in ("resulted","approved")
                               for i in order.items.filter_by(is_deleted=False).all())
                if all_done:
                    order.status = "resulted"

            db.session.commit()
            flash("Results saved.", "success")
            return redirect(url_for("lab.index", tab="approval"))

        except Exception as e:
            db.session.rollback()
            flash(f"Save failed: {e}", "danger")

    items = order.items.filter_by(is_deleted=False).all()
    return render_template("lab/enter_results.html",
        order=order, items=items, patient=order.patient,
        locked=locked, today=date.today())

# ── STAGE 4: APPROVE ─────────────────────────────────────────────────

@lab_bp.route("/approve/<int:order_id>", methods=["POST"])
@login_required
def approve_report(order_id):
    order = LabOrder.query.get_or_404(order_id)
    try:
        if order.approval:
            flash("Already approved.", "info")
            return redirect(url_for("lab.view_report", order_id=order_id))

        apv = LabApproval(
            order_id=order.id, branch_id=order.branch_id,
            approved_by=current_user.id,
            approver_note=request.form.get("approver_note","").strip(),
        )
        db.session.add(apv)

        for item in order.items.filter_by(is_deleted=False).all():
            if item.result:
                item.result.is_locked = True
            item.status = "approved"

        order.status = "approved"
        db.session.commit()
        flash(f"Report {order.order_number} approved and locked.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Approval failed: {e}", "danger")
    return redirect(url_for("lab.index", tab="approved"))

# ── UNLOCK (superadmin only) ──────────────────────────────────────────

@lab_bp.route("/unlock/<int:order_id>", methods=["POST"])
@login_required
def unlock_report(order_id):
    if not current_user.is_superadmin:
        flash("Only superadmin can unlock reports.", "danger")
        return redirect(url_for("lab.view_report", order_id=order_id))
    order = LabOrder.query.get_or_404(order_id)
    if not order.approval:
        flash("No approval record.", "warning")
        return redirect(url_for("lab.view_report", order_id=order_id))
    order.approval.is_unlocked   = True
    order.approval.unlocked_by   = current_user.id
    order.approval.unlocked_at   = datetime.now(timezone.utc)
    order.approval.unlock_reason = request.form.get("unlock_reason","").strip()
    for item in order.items.filter_by(is_deleted=False).all():
        if item.result:
            item.result.is_locked = False
    order.status = "resulted"
    db.session.commit()
    flash(f"Report {order.order_number} unlocked.", "warning")
    return redirect(url_for("lab.enter_results", order_id=order_id))

# ── VIEW / PRINT REPORT ───────────────────────────────────────────────

@lab_bp.route("/report/<int:order_id>")
@login_required
def view_report(order_id):
    order    = LabOrder.query.get_or_404(order_id)
    items    = order.items.filter_by(is_deleted=False).all()
    from app.models.foundation import Branch
    branch   = Branch.query.get(order.branch_id)
    return render_template("lab/report.html",
        order=order, items=items,
        patient=order.patient, doctor=order.doctor,
        sample=order.sample, approval=order.approval,
        branch=branch, now=datetime.now(timezone.utc))

# ── SETTINGS: TEST MASTER ─────────────────────────────────────────────

@lab_bp.route("/settings/test/save", methods=["POST"])
@login_required
def test_save():
    bid     = _bid()
    test_id = request.form.get("test_id")
    try:
        f = request.form
        def _dec(k):
            v = f.get(k,"").strip()
            return Decimal(v) if v else None

        if test_id:
            test = TestMaster.query.get(int(test_id))
        else:
            test = TestMaster(branch_id=bid, created_by=current_user.id)
            db.session.add(test)

        test.test_code         = f.get("test_code","").strip().upper() or None
        test.test_name         = f.get("test_name","").strip()
        test.test_short_name   = f.get("test_short_name","").strip() or None
        test.category_id       = int(f.get("category_id")) if f.get("category_id") else None
        test.sample_type       = f.get("sample_type","").strip() or None
        test.method            = f.get("method","").strip() or None
        test.department        = f.get("department","").strip() or None
        test.unit              = f.get("unit","").strip() or None
        test.normal_range      = f.get("normal_range","").strip() or None
        test.normal_range_text = f.get("normal_range_text","").strip() or None
        test.male_range        = f.get("male_range","").strip() or None
        test.female_range      = f.get("female_range","").strip() or None
        test.normal_low        = _dec("normal_low")
        test.normal_high       = _dec("normal_high")
        test.critical_low      = _dec("critical_low")
        test.critical_high     = _dec("critical_high")
        test.price             = Decimal(f.get("price","0") or "0")
        test.gst_percent       = Decimal(f.get("gst_percent","0") or "0")
        test.turnaround_hrs    = int(f.get("turnaround_hrs","24") or "24")
        test.print_note        = f.get("print_note","").strip() or None

        db.session.commit()
        flash(f"Test '{test.test_name}' saved.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Save failed: {e}", "danger")
    return redirect(url_for("lab.index", tab="settings"))

@lab_bp.route("/settings/test/delete/<int:test_id>", methods=["POST"])
@login_required
def test_delete(test_id):
    t = TestMaster.query.get_or_404(test_id)
    t.is_deleted = True
    db.session.commit()
    flash("Test removed.", "info")
    return redirect(url_for("lab.index", tab="settings"))

@lab_bp.route("/settings/category/save", methods=["POST"])
@login_required
def category_save():
    bid = _bid()
    try:
        cat = LabCategory(
            branch_id=bid,
            name=request.form.get("name","").strip(),
            code=request.form.get("code","").strip().upper() or None,
        )
        db.session.add(cat)
        db.session.commit()
        flash(f"Category '{cat.name}' added.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Failed: {e}", "danger")
    return redirect(url_for("lab.index", tab="settings", subtab="categories"))

# ── AJAX ──────────────────────────────────────────────────────────────

@lab_bp.route("/test-search")
@login_required
def test_search():
    bid = _bid()
    q   = request.args.get("q","").strip()
    if len(q) < 1:
        return jsonify([])
    tests = TestMaster.query.filter(
        TestMaster.branch_id == bid,
        TestMaster.is_active == True,
        TestMaster.is_deleted == False,
        or_(TestMaster.test_name.ilike(f"%{q}%"),
            TestMaster.test_code.ilike(f"%{q}%"))
    ).limit(20).all()
    return jsonify([{
        "id":      t.id,
        "code":    t.test_code or "",
        "name":    t.test_name,
        "sample":  t.sample_type or "",
        "unit":    t.unit or "",
        "range":   t.normal_range or "",
        "price":   float(t.price or 0),
        "gst":     float(t.gst_percent or 0),
        "tat_hrs": t.turnaround_hrs or 24,
        "cat_id":  t.category_id or "",
    } for t in tests])

@lab_bp.route("/patient-search")
@login_required
def patient_search():
    from app.models.foundation import Patient
    bid = _bid()
    q   = request.args.get("q","").strip()
    if len(q) < 2:
        return jsonify([])
    pts = Patient.query.filter(
        Patient.branch_id == bid,
        Patient.is_deleted == False,
        or_(Patient.first_name.ilike(f"%{q}%"),
            Patient.last_name.ilike(f"%{q}%"),
            Patient.uhid.ilike(f"%{q}%"),
            Patient.phone.ilike(f"%{q}%"))
    ).limit(15).all()
    return jsonify([{
        "id":     p.id, "name": p.full_name,
        "uhid":   p.uhid, "phone": p.phone,
        "age":    p.age_years or "",
        "gender": p.gender[0] if p.gender else "",
    } for p in pts])
