# Revive - app/blueprints/billing/routes.py
# Billing — Rivive Hospital PDF design.
# Sub-tabs: Bill Summary, Credit Bills, Saved Bills, Overall Bills,
#           Detailed Receipt Bills, Expense Bills, Insurance Patient
# Table cols: Date/Time, Bill No, Bill Type, Patient Details,
#             Phone/Pts ID, DO, Amount, Cash Received, GPay Received,
#             Discount Amount, Refund Amount, Cancelled Bill,
#             Payment Mode, View Bill, Print Bill
# Day-end denomination + total amount summary.

from datetime import date, datetime, timezone
from flask import (Blueprint, render_template, redirect, url_for,
                   request, flash, jsonify, send_file, current_app)
from flask_login import login_required, current_user
from sqlalchemy import func

from app.extensions import db
from app.models.billing import BillMaster, BillItem, Payment, Receipt, CreditNote, InsuranceClaim, TPAMaster
from app.models.patients import Patient
from app.models.foundation import Branch
from app.utils.decorators import require_permission
from app.utils.audit import log_action
from app.utils.generators import generate_bill_number, generate_receipt_number

billing_bp = Blueprint("billing", __name__)


@billing_bp.route("/")
@login_required
@require_permission("billing", "view")
def index():
    tab       = request.args.get("tab", "summary")
    branch_id = current_user.branch_id
    today     = date.today()
    date_from = request.args.get("date_from", today.isoformat())
    date_to   = request.args.get("date_to",   today.isoformat())

    # Summary stats
    stats = _get_billing_stats(branch_id, date_from, date_to)

    # Bills list per tab
    bills = _get_bills_for_tab(tab, branch_id, date_from, date_to)

    return render_template("billing/index.html",
                           tab=tab, bills=bills, stats=stats,
                           today=today, date_from=date_from, date_to=date_to)


def _get_billing_stats(branch_id, date_from, date_to):
    q = BillMaster.query.filter(BillMaster.is_deleted == False)
    if branch_id:
        q = q.filter(BillMaster.branch_id == branch_id)
    try:
        q = q.filter(func.date(BillMaster.bill_date) >= date_from,
                     func.date(BillMaster.bill_date) <= date_to)
    except Exception:
        pass

    total_bills   = q.count()
    bill_amount   = db.session.query(func.coalesce(func.sum(BillMaster.gross_total),0)).filter(
        BillMaster.is_deleted==False, BillMaster.branch_id==branch_id if branch_id else True).scalar() or 0
    cash_received = db.session.query(func.coalesce(func.sum(Payment.amount),0)).filter(
        Payment.payment_mode=="cash", Payment.is_deleted==False, Payment.is_refunded==False,
        *([Payment.branch_id==branch_id] if branch_id else [])).scalar() or 0
    gpay_received = db.session.query(func.coalesce(func.sum(Payment.amount),0)).filter(
        Payment.payment_mode.in_(["upi","card"]), Payment.is_deleted==False, Payment.is_refunded==False,
        *([Payment.branch_id==branch_id] if branch_id else [])).scalar() or 0
    discount      = db.session.query(func.coalesce(func.sum(BillMaster.discount_amount),0)).filter(
        BillMaster.is_deleted==False, *([BillMaster.branch_id==branch_id] if branch_id else [])).scalar() or 0
    refund        = db.session.query(func.coalesce(func.sum(Payment.amount),0)).filter(
        Payment.is_refunded==True, Payment.is_deleted==False,
        *([Payment.branch_id==branch_id] if branch_id else [])).scalar() or 0

    return {
        "total_bills":    int(total_bills),
        "bill_amount":    float(bill_amount),
        "cash_received":  float(cash_received),
        "gpay_received":  float(gpay_received),
        "discount":       float(discount),
        "refund":         float(refund),
    }


def _get_bills_for_tab(tab, branch_id, date_from, date_to):
    q = BillMaster.query.filter(BillMaster.is_deleted == False)
    if branch_id:
        q = q.filter(BillMaster.branch_id == branch_id)
    try:
        q = q.filter(func.date(BillMaster.bill_date) >= date_from,
                     func.date(BillMaster.bill_date) <= date_to)
    except Exception:
        pass

    if tab == "credit":
        q = q.filter(BillMaster.status == "credit")
    elif tab == "saved":
        q = q.filter(BillMaster.status == "draft")
    elif tab == "cancelled":
        q = q.filter(BillMaster.status == "cancelled")
    elif tab == "insurance":
        q = q.join(InsuranceClaim, InsuranceClaim.bill_id == BillMaster.id, isouter=True).filter(
            BillMaster.tpa_id != None)
    # summary / overall / detailed — all bills

    return q.order_by(BillMaster.bill_date.desc()).limit(200).all()


@billing_bp.route("/new", methods=["GET","POST"])
@login_required
@require_permission("billing","create")
def new_bill():
    branch_id = current_user.branch_id
    branch    = Branch.query.get(branch_id) if branch_id else None

    if request.method == "POST":
        try:
            patient_id   = int(request.form.get("patient_id"))
            bill_type    = request.form.get("bill_type","opd")
            payment_mode = request.form.get("payment_mode","cash")
            notes        = request.form.get("notes","")

            bill_no = generate_bill_number(branch.code if branch else "GEN", "B")
            bill = BillMaster(
                branch_id=branch_id,
                patient_id=patient_id,
                bill_number=bill_no,
                bill_type=bill_type,
                status="generated",
                notes=notes,
                created_by=current_user.id,
            )
            db.session.add(bill)
            db.session.flush()

            # Bill items
            subtotal = 0
            descs    = request.form.getlist("item_desc[]")
            qtys     = request.form.getlist("item_qty[]")
            rates    = request.form.getlist("item_rate[]")
            gsts     = request.form.getlist("item_gst[]")
            for i, desc in enumerate(descs):
                if not desc.strip(): continue
                qty  = float(qtys[i]) if i<len(qtys) and qtys[i] else 1
                rate = float(rates[i]) if i<len(rates) and rates[i] else 0
                gst  = float(gsts[i])  if i<len(gsts)  and gsts[i]  else 0
                gst_amt = round(rate*qty*gst/100, 2)
                amt  = round(rate*qty + gst_amt, 2)
                subtotal += rate*qty
                item = BillItem(bill_id=bill.id, description=desc.strip(),
                                quantity=qty, unit_rate=rate,
                                gst_percent=gst, gst_amount=gst_amt, amount=amt)
                db.session.add(item)

            discount_pct = float(request.form.get("discount_pct","0") or 0)
            discount_amt = round(subtotal * discount_pct / 100, 2)
            gst_total    = sum(i.gst_amount for i in bill.items)
            gross        = round(subtotal - discount_amt + float(gst_total or 0), 2)

            bill.subtotal        = subtotal
            bill.discount_percent = discount_pct
            bill.discount_amount = discount_amt
            bill.gross_total     = gross
            bill.balance_amount  = gross

            # Record payment
            paid = float(request.form.get("paid_amount","0") or 0)
            if paid > 0:
                pmt = Payment(branch_id=branch_id, bill_id=bill.id,
                              patient_id=patient_id, payment_mode=payment_mode,
                              amount=paid, reference_no=request.form.get("reference_no",""),
                              received_by=current_user.id)
                db.session.add(pmt)
                bill.paid_amount    = paid
                bill.balance_amount = round(gross - paid, 2)
                bill.status = "paid" if bill.balance_amount <= 0 else "partial"

            db.session.commit()
            log_action("CREATE","billing",record_id=bill.id,record_type="BillMaster",
                       new_value={"bill_number":bill_no,"amount":gross})
            flash(f"Bill {bill_no} created. Total: ₹{gross:,.2f}","success")
            return redirect(url_for("billing.view_bill", bill_id=bill.id))

        except Exception as e:
            db.session.rollback()
            flash(f"Error creating bill: {e}","danger")

    return render_template("billing/new_bill.html", branch=branch)


@billing_bp.route("/bill/<int:bill_id>")
@login_required
@require_permission("billing","view")
def view_bill(bill_id):
    bill = BillMaster.query.get_or_404(bill_id)
    items = bill.items.filter_by(is_deleted=False).all()
    payments = bill.payments.filter_by(is_deleted=False).all()
    return render_template("billing/view_bill.html", bill=bill, items=items, payments=payments)


@billing_bp.route("/bill/<int:bill_id>/cancel", methods=["POST"])
@login_required
@require_permission("billing","edit")
def cancel_bill(bill_id):
    bill = BillMaster.query.get_or_404(bill_id)
    bill.status = "cancelled"
    db.session.commit()
    log_action("UPDATE","billing",record_id=bill_id,record_type="BillMaster",
               new_value={"status":"cancelled"})
    flash("Bill cancelled.","info")
    return redirect(url_for("billing.index"))


@billing_bp.route("/bill/<int:bill_id>/print")
@login_required
@require_permission("billing","view")
def print_bill(bill_id):
    bill  = BillMaster.query.get_or_404(bill_id)
    items = bill.items.filter_by(is_deleted=False).all()
    payments = bill.payments.filter_by(is_deleted=False).all()
    branch = Branch.query.get(bill.branch_id) if bill.branch_id else None
    return render_template("billing/print_bill.html", bill=bill, items=items,
                           payments=payments, branch=branch)


@billing_bp.route("/patient-search")
@login_required
def patient_search():
    q = request.args.get("q","").strip()
    if len(q) < 2:
        return jsonify([])
    like = f"%{q}%"
    pts = Patient.query.filter(
        Patient.is_deleted==False,
        db.or_(Patient.first_name.ilike(like), Patient.last_name.ilike(like),
               Patient.uhid.ilike(like), Patient.phone.ilike(like))
    )
    if current_user.branch_id:
        pts = pts.filter(Patient.branch_id == current_user.branch_id)
    return jsonify([{"id":p.id,"uhid":p.uhid,"name":p.full_name,"phone":p.phone} for p in pts.limit(10).all()])
