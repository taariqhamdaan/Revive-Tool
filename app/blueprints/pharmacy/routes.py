# MediCore - app/blueprints/pharmacy/routes.py
# Pharmacy: Drug master, categories, suppliers, purchase orders,
# GRN, stock ledger, dispensing, expiry alerts, bulk upload.
# Logic summary per tab:
#   drugs      — drug master list, add/edit, bulk upload, download template
#   stock      — current stock levels, reorder alerts, batch-wise view
#   purchase   — purchase orders CRUD, send to supplier
#   grn        — goods received note against PO or direct
#   dispensing — dispense drugs linked to prescription or direct sale
#   expiry     — drugs expiring within configured days
#   suppliers  — supplier master CRUD

from datetime import date, datetime, timezone, timedelta
from flask import (Blueprint, render_template, redirect, url_for,
                   request, flash, send_file, jsonify, current_app)
from flask_login import login_required, current_user
from sqlalchemy import func
import os
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models.pharmacy import (DrugMaster, DrugCategory, Supplier,
                                  PurchaseOrder, POItem, GRN, GRNItem,
                                  StockLedger, Dispensing, DispensingItem)
from app.models.patients import Patient
from app.models.opd import Prescription, PrescriptionItem
from app.models.foundation import Branch
from app.utils.decorators import require_permission
from app.utils.audit import log_action
from app.utils.generators import generate_grn_number, generate_po_number
from app.utils.bulk_upload import process_bulk_upload, generate_upload_template

pharmacy_bp = Blueprint("pharmacy", __name__)


# ── Index / Drug Master ───────────────────────────────────────────────────

@pharmacy_bp.route("/")
@login_required
@require_permission("pharmacy", "view")
def index():
    tab       = request.args.get("tab", "drugs")
    branch_id = current_user.branch_id
    page      = request.args.get("page", 1, type=int)
    search    = request.args.get("q", "").strip()

    if tab == "stock":
        return _stock_view(branch_id, search, page)
    elif tab == "purchase":
        return _purchase_view(branch_id, page)
    elif tab == "grn":
        return _grn_view(branch_id, page)
    elif tab == "dispensing":
        return _dispensing_view(branch_id, page)
    elif tab == "expiry":
        return _expiry_view(branch_id)
    elif tab == "suppliers":
        return _suppliers_view(branch_id, page)

    # Default: drugs
    q = DrugMaster.query.filter(DrugMaster.is_deleted == False)
    if branch_id:
        q = q.filter(DrugMaster.branch_id == branch_id)
    if search:
        like = f"%{search}%"
        q = q.filter(db.or_(
            DrugMaster.generic_name.ilike(like),
            DrugMaster.brand_name.ilike(like),
            DrugMaster.drug_code.ilike(like),
        ))
    drugs = q.order_by(DrugMaster.generic_name).paginate(page=page, per_page=25)
    categories = DrugCategory.query.filter_by(branch_id=branch_id, is_deleted=False).all()
    return render_template("pharmacy/index.html", tab=tab, drugs=drugs,
                           categories=categories, search=search)


def _stock_view(branch_id, search, page):
    q = DrugMaster.query.filter(DrugMaster.is_deleted == False, DrugMaster.is_active == True)
    if branch_id:
        q = q.filter(DrugMaster.branch_id == branch_id)
    if search:
        like = f"%{search}%"
        q = q.filter(db.or_(DrugMaster.generic_name.ilike(like), DrugMaster.brand_name.ilike(like)))
    drugs = q.order_by(DrugMaster.generic_name).paginate(page=page, per_page=25)
    return render_template("pharmacy/index.html", tab="stock", drugs=drugs, search=search)


def _purchase_view(branch_id, page):
    q = PurchaseOrder.query.filter(PurchaseOrder.is_deleted == False)
    if branch_id:
        q = q.filter(PurchaseOrder.branch_id == branch_id)
    pos = q.order_by(PurchaseOrder.po_date.desc()).paginate(page=page, per_page=25)
    suppliers = Supplier.query.filter_by(branch_id=branch_id, is_deleted=False).all()
    drugs = DrugMaster.query.filter_by(branch_id=branch_id, is_deleted=False, is_active=True).all()
    return render_template("pharmacy/index.html", tab="purchase", pos=pos,
                           suppliers=suppliers, drugs=drugs)


def _grn_view(branch_id, page):
    q = GRN.query.filter(GRN.is_deleted == False)
    if branch_id:
        q = q.filter(GRN.branch_id == branch_id)
    grns = q.order_by(GRN.grn_date.desc()).paginate(page=page, per_page=25)
    suppliers = Supplier.query.filter_by(branch_id=branch_id, is_deleted=False).all()
    pos = PurchaseOrder.query.filter(
        PurchaseOrder.branch_id == branch_id if branch_id else True,
        PurchaseOrder.status.in_(["sent","partial"]),
        PurchaseOrder.is_deleted == False,
    ).all()
    drugs = DrugMaster.query.filter_by(branch_id=branch_id, is_deleted=False, is_active=True).all()
    return render_template("pharmacy/index.html", tab="grn", grns=grns,
                           suppliers=suppliers, pos=pos, drugs=drugs)


def _dispensing_view(branch_id, page):
    q = Dispensing.query.filter(Dispensing.is_deleted == False)
    if branch_id:
        q = q.filter(Dispensing.branch_id == branch_id)
    dispensings = q.order_by(Dispensing.dispensed_at.desc()).paginate(page=page, per_page=25)
    drugs = DrugMaster.query.filter(
        DrugMaster.is_deleted == False, DrugMaster.is_active == True,
        DrugMaster.current_stock > 0,
        *([DrugMaster.branch_id == branch_id] if branch_id else []),
    ).order_by(DrugMaster.generic_name).all()
    return render_template("pharmacy/index.html", tab="dispensing",
                           dispensings=dispensings, drugs=drugs)


def _expiry_view(branch_id):
    days = int(current_app.config.get("EXPIRY_ALERT_DAYS", 90))
    cutoff = date.today() + timedelta(days=days)
    q = GRNItem.query.join(DrugMaster).filter(
        GRNItem.expiry_date <= cutoff,
        GRNItem.expiry_date >= date.today(),
        GRNItem.qty_received > 0,
        GRNItem.is_deleted == False,
    )
    if branch_id:
        q = q.filter(DrugMaster.branch_id == branch_id)
    expiring = q.order_by(GRNItem.expiry_date).all()

    expired = GRNItem.query.join(DrugMaster).filter(
        GRNItem.expiry_date < date.today(),
        GRNItem.qty_received > 0,
        GRNItem.is_deleted == False,
        *([DrugMaster.branch_id == branch_id] if branch_id else []),
    ).order_by(GRNItem.expiry_date).all()

    return render_template("pharmacy/index.html", tab="expiry",
                           expiring=expiring, expired=expired, cutoff_days=days)


def _suppliers_view(branch_id, page):
    q = Supplier.query.filter(Supplier.is_deleted == False)
    if branch_id:
        q = q.filter(Supplier.branch_id == branch_id)
    suppliers = q.order_by(Supplier.name).paginate(page=page, per_page=25)
    return render_template("pharmacy/index.html", tab="suppliers", suppliers=suppliers)


# ── Drug CRUD ─────────────────────────────────────────────────────────────

@pharmacy_bp.route("/drug/save", methods=["POST"])
@login_required
@require_permission("pharmacy", "create")
def drug_save():
    branch_id = current_user.branch_id
    drug_id   = request.form.get("drug_id")

    if drug_id:
        drug = DrugMaster.query.get_or_404(int(drug_id))
    else:
        drug = DrugMaster(branch_id=branch_id)
        db.session.add(drug)

    drug.generic_name    = request.form.get("generic_name", "").strip()
    drug.brand_name      = request.form.get("brand_name", "").strip() or None
    drug.category_id     = request.form.get("category_id") or None
    drug.strength        = request.form.get("strength", "").strip() or None
    drug.form            = request.form.get("form", "").strip() or None
    drug.unit_of_measure = request.form.get("unit_of_measure", "").strip() or None
    drug.schedule        = request.form.get("schedule", "").strip() or None
    drug.hsn_code        = request.form.get("hsn_code", "").strip() or None
    drug.gst_percent     = float(request.form.get("gst_percent", 12) or 12)
    drug.reorder_level   = int(request.form.get("reorder_level", 10) or 10)
    drug.mrp             = float(request.form.get("mrp", 0) or 0)
    drug.purchase_rate   = float(request.form.get("purchase_rate", 0) or 0)
    drug.sale_rate       = float(request.form.get("sale_rate", 0) or 0)
    drug.is_active       = True

    db.session.commit()
    log_action("CREATE" if not drug_id else "UPDATE", "pharmacy",
               record_id=drug.id, record_type="DrugMaster",
               new_value={"name": drug.generic_name})
    flash(f"Drug '{drug.generic_name}' saved.", "success")
    return redirect(url_for("pharmacy.index", tab="drugs"))


@pharmacy_bp.route("/drug/<int:drug_id>/toggle", methods=["POST"])
@login_required
@require_permission("pharmacy", "edit")
def drug_toggle(drug_id):
    drug = DrugMaster.query.get_or_404(drug_id)
    drug.is_active = not drug.is_active
    db.session.commit()
    flash(f"Drug {'activated' if drug.is_active else 'deactivated'}.", "info")
    return redirect(url_for("pharmacy.index", tab="drugs"))


# ── Purchase Order ────────────────────────────────────────────────────────

@pharmacy_bp.route("/po/save", methods=["POST"])
@login_required
@require_permission("pharmacy", "purchase")
def po_save():
    branch_id   = current_user.branch_id
    branch      = Branch.query.get(branch_id) if branch_id else None
    supplier_id = int(request.form.get("supplier_id"))
    po_date     = datetime.strptime(request.form.get("po_date"), "%Y-%m-%d").date()
    exp_date_str = request.form.get("expected_date", "")

    try:
        po = PurchaseOrder(
            branch_id=branch_id,
            supplier_id=supplier_id,
            po_number=generate_po_number(branch.code if branch else "GEN"),
            po_date=po_date,
            expected_date=datetime.strptime(exp_date_str, "%Y-%m-%d").date() if exp_date_str else None,
            notes=request.form.get("notes", ""),
            status="draft",
            created_by=current_user.id,
        )
        db.session.add(po)
        db.session.flush()

        drug_ids  = request.form.getlist("po_drug_id[]")
        qtys      = request.form.getlist("po_qty[]")
        rates     = request.form.getlist("po_rate[]")
        gsts      = request.form.getlist("po_gst[]")
        subtotal  = 0

        for i, did in enumerate(drug_ids):
            if not did: continue
            qty  = int(qtys[i]) if i < len(qtys) and qtys[i] else 0
            rate = float(rates[i]) if i < len(rates) and rates[i] else 0
            gst  = float(gsts[i]) if i < len(gsts) and gsts[i] else 0
            total = round(qty * rate * (1 + gst / 100), 2)
            subtotal += qty * rate
            item = POItem(po_id=po.id, drug_id=int(did),
                          qty_ordered=qty, unit_rate=rate,
                          gst_percent=gst, total=total)
            db.session.add(item)

        gst_amount   = round(subtotal * 0.12, 2)
        po.subtotal  = subtotal
        po.gst_amount = gst_amount
        po.total_amount = round(subtotal + gst_amount, 2)

        db.session.commit()
        log_action("CREATE", "pharmacy", record_id=po.id, record_type="PurchaseOrder",
                   new_value={"po_number": po.po_number, "total": float(po.total_amount)})
        flash(f"Purchase Order {po.po_number} created.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "danger")

    return redirect(url_for("pharmacy.index", tab="purchase"))


@pharmacy_bp.route("/po/<int:po_id>/send", methods=["POST"])
@login_required
@require_permission("pharmacy", "purchase")
def po_send(po_id):
    po = PurchaseOrder.query.get_or_404(po_id)
    po.status = "sent"
    db.session.commit()
    flash(f"PO {po.po_number} marked as sent.", "success")
    return redirect(url_for("pharmacy.index", tab="purchase"))


# ── GRN ──────────────────────────────────────────────────────────────────

@pharmacy_bp.route("/grn/save", methods=["POST"])
@login_required
@require_permission("pharmacy", "purchase")
def grn_save():
    branch_id   = current_user.branch_id
    branch      = Branch.query.get(branch_id) if branch_id else None
    supplier_id = int(request.form.get("supplier_id"))
    grn_date    = datetime.strptime(request.form.get("grn_date"), "%Y-%m-%d").date()
    po_id       = request.form.get("po_id") or None

    try:
        grn = GRN(
            branch_id=branch_id,
            supplier_id=supplier_id,
            po_id=int(po_id) if po_id else None,
            grn_number=generate_grn_number(branch.code if branch else "GEN"),
            grn_date=grn_date,
            invoice_number=request.form.get("invoice_number", "").strip() or None,
            notes=request.form.get("notes", ""),
            received_by=current_user.id,
        )
        db.session.add(grn)
        db.session.flush()

        drug_ids  = request.form.getlist("grn_drug_id[]")
        batches   = request.form.getlist("grn_batch[]")
        expiries  = request.form.getlist("grn_expiry[]")
        qtys      = request.form.getlist("grn_qty[]")
        rates     = request.form.getlist("grn_rate[]")
        mrps      = request.form.getlist("grn_mrp[]")
        subtotal  = 0

        for i, did in enumerate(drug_ids):
            if not did: continue
            qty  = int(qtys[i]) if i < len(qtys) and qtys[i] else 0
            rate = float(rates[i]) if i < len(rates) and rates[i] else 0
            mrp  = float(mrps[i]) if i < len(mrps) and mrps[i] else 0
            exp  = datetime.strptime(expiries[i], "%Y-%m-%d").date() if i < len(expiries) and expiries[i] else None
            total = round(qty * rate, 2)
            subtotal += total

            item = GRNItem(
                grn_id=grn.id, drug_id=int(did),
                batch_number=batches[i] if i < len(batches) else "",
                expiry_date=exp, qty_received=qty,
                purchase_rate=rate, mrp=mrp, total=total,
            )
            db.session.add(item)

            # Update drug current_stock
            drug = DrugMaster.query.get(int(did))
            if drug:
                drug.current_stock = (drug.current_stock or 0) + qty
                drug.purchase_rate = rate
                if mrp: drug.mrp = mrp

            # Stock ledger entry
            ledger = StockLedger(
                branch_id=branch_id, drug_id=int(did),
                batch_number=batches[i] if i < len(batches) else "",
                expiry_date=exp,
                transaction_type="grn",
                qty_in=qty, qty_out=0,
                balance=(drug.current_stock if drug else qty),
                rate=rate, created_by=current_user.id,
            )
            db.session.add(ledger)

        grn.subtotal    = subtotal
        grn.total_amount = subtotal

        # Update PO status if linked
        if po_id:
            po = PurchaseOrder.query.get(int(po_id))
            if po:
                po.status = "received"

        db.session.commit()
        log_action("CREATE", "pharmacy", record_id=grn.id, record_type="GRN",
                   new_value={"grn_number": grn.grn_number})
        flash(f"GRN {grn.grn_number} saved. Stock updated.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "danger")

    return redirect(url_for("pharmacy.index", tab="grn"))


# ── Dispensing ────────────────────────────────────────────────────────────

@pharmacy_bp.route("/dispense/save", methods=["POST"])
@login_required
@require_permission("pharmacy", "create")
def dispense_save():
    branch_id      = current_user.branch_id
    patient_id     = int(request.form.get("patient_id"))
    prescription_id = request.form.get("prescription_id") or None

    try:
        import secrets
        disp = Dispensing(
            branch_id=branch_id,
            patient_id=patient_id,
            prescription_id=int(prescription_id) if prescription_id else None,
            dispense_number=f"DIS-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            dispensed_by=current_user.id,
        )
        db.session.add(disp)
        db.session.flush()

        drug_ids = request.form.getlist("disp_drug_id[]")
        qtys     = request.form.getlist("disp_qty[]")
        rates    = request.form.getlist("disp_rate[]")
        total_amount = 0

        for i, did in enumerate(drug_ids):
            if not did: continue
            qty  = int(qtys[i]) if i < len(qtys) and qtys[i] else 1
            rate = float(rates[i]) if i < len(rates) and rates[i] else 0
            amt  = round(qty * rate, 2)
            total_amount += amt

            item = DispensingItem(
                dispensing_id=disp.id, drug_id=int(did),
                qty=qty, rate=rate, amount=amt,
            )
            db.session.add(item)

            # Deduct stock
            drug = DrugMaster.query.get(int(did))
            if drug:
                drug.current_stock = max(0, (drug.current_stock or 0) - qty)
                # Check low stock and send alert
                if drug.current_stock <= drug.reorder_level:
                    _send_low_stock_alert(drug, branch_id)

            # Stock ledger
            ledger = StockLedger(
                branch_id=branch_id, drug_id=int(did),
                transaction_type="dispensing",
                qty_in=0, qty_out=qty,
                balance=(drug.current_stock if drug else 0),
                rate=rate, created_by=current_user.id,
            )
            db.session.add(ledger)

        discount  = float(request.form.get("discount_amount", 0) or 0)
        disp.total_amount   = total_amount
        disp.discount_amount = discount
        disp.net_amount     = round(total_amount - discount, 2)
        disp.is_billed      = False

        db.session.commit()
        log_action("CREATE", "pharmacy", record_id=disp.id, record_type="Dispensing")
        flash(f"Dispensing {disp.dispense_number} saved. ₹{disp.net_amount:,.2f}", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "danger")

    return redirect(url_for("pharmacy.index", tab="dispensing"))


def _send_low_stock_alert(drug, branch_id):
    try:
        from app.utils.email import send_stock_alert_email
        branch = Branch.query.get(branch_id)
        if branch and branch.email:
            send_stock_alert_email(drug, drug.current_stock, drug.reorder_level, branch)
    except Exception:
        pass


# ── Supplier CRUD ─────────────────────────────────────────────────────────

@pharmacy_bp.route("/supplier/save", methods=["POST"])
@login_required
@require_permission("pharmacy", "purchase")
def supplier_save():
    branch_id = current_user.branch_id
    sup_id    = request.form.get("sup_id")

    if sup_id:
        s = Supplier.query.get_or_404(int(sup_id))
    else:
        seq = Supplier.query.filter_by(branch_id=branch_id).count() + 1
        s = Supplier(branch_id=branch_id, supplier_code=f"SUP{seq:04d}")
        db.session.add(s)

    s.name         = request.form.get("name", "").strip()
    s.contact_name = request.form.get("contact_name", "").strip() or None
    s.phone        = request.form.get("phone", "").strip() or None
    s.email        = request.form.get("email", "").strip() or None
    s.address      = request.form.get("address", "").strip() or None
    s.gstin        = request.form.get("gstin", "").strip() or None
    s.drug_license = request.form.get("drug_license", "").strip() or None

    db.session.commit()
    flash(f"Supplier '{s.name}' saved.", "success")
    return redirect(url_for("pharmacy.index", tab="suppliers"))


# ── Bulk Upload ───────────────────────────────────────────────────────────

@pharmacy_bp.route("/bulk-upload", methods=["GET", "POST"])
@login_required
@require_permission("pharmacy", "create")
def bulk_upload():
    if request.method == "POST":
        file = request.files.get("file")
        if not file or not file.filename:
            flash("No file selected.", "danger")
            return redirect(request.url)
        ext = file.filename.rsplit(".", 1)[-1].lower()
        filename = secure_filename(f"bulk_drugs_{datetime.now().strftime('%Y%m%d%H%M%S')}.{ext}")
        save_path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
        file.save(save_path)
        result = process_bulk_upload(save_path, "drugs", current_user.branch_id, current_user.id)
        os.remove(save_path)
        return render_template("pharmacy/bulk_result.html", result=result)
    return render_template("pharmacy/bulk_upload.html")


@pharmacy_bp.route("/download-template")
@login_required
def download_template():
    import io
    data = generate_upload_template("drugs")
    return send_file(io.BytesIO(data),
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name="Drug_Upload_Template.xlsx")


# ── Drug search JSON (for dispensing/prescription) ────────────────────────

@pharmacy_bp.route("/drug-search")
@login_required
def drug_search():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    like = f"%{q}%"
    drugs = DrugMaster.query.filter(
        DrugMaster.is_deleted == False, DrugMaster.is_active == True,
        db.or_(DrugMaster.generic_name.ilike(like), DrugMaster.brand_name.ilike(like)),
        *([DrugMaster.branch_id == current_user.branch_id] if current_user.branch_id else []),
    ).limit(10).all()
    return jsonify([{
        "id": d.id, "name": d.generic_name,
        "brand": d.brand_name or "",
        "strength": d.strength or "",
        "form": d.form or "",
        "stock": d.current_stock or 0,
        "rate": float(d.sale_rate or 0),
        "mrp": float(d.mrp or 0),
    } for d in drugs])
