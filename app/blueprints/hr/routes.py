# Revive - app/blueprints/hr/routes.py
# HR Module: Employee list, register, edit, attendance, leave management.

from datetime import date, datetime, timezone
from flask import (Blueprint, render_template, redirect, url_for,
                   request, flash, send_file, current_app)
from flask_login import login_required, current_user
from app.extensions import db
from app.models.hr import Employee, Attendance, LeaveType, LeaveRequest, Shift
from app.models.foundation import Department, Designation, Branch
from app.utils.decorators import require_permission
from app.utils.audit import log_action
from app.utils.generators import generate_employee_code
from app.utils.bulk_upload import process_bulk_upload, generate_upload_template
import os
from werkzeug.utils import secure_filename

hr_bp = Blueprint("hr", __name__)


@hr_bp.route("/")
@login_required
@require_permission("hr", "view")
def index():
    tab       = request.args.get("tab", "employees")
    branch_id = current_user.branch_id
    page      = request.args.get("page", 1, type=int)
    search    = request.args.get("q", "").strip()

    if tab == "attendance":
        att_date = request.args.get("att_date", date.today().isoformat())
        records = _get_attendance(branch_id, att_date)
        employees = Employee.query.filter_by(branch_id=branch_id, is_active=True, is_deleted=False).all()
        return render_template("hr/index.html", tab=tab, records=records,
                               employees=employees, att_date=att_date)

    elif tab == "leave":
        leaves = LeaveRequest.query.join(Employee).filter(
            Employee.branch_id == branch_id if branch_id else True,
            LeaveRequest.is_deleted == False,
        ).order_by(LeaveRequest.applied_at.desc()).limit(100).all()
        leave_types = LeaveType.query.filter_by(branch_id=branch_id, is_deleted=False).all()
        return render_template("hr/index.html", tab=tab, leaves=leaves, leave_types=leave_types)

    # Default: employees list
    q = Employee.query.filter(Employee.is_deleted == False)
    if branch_id:
        q = q.filter(Employee.branch_id == branch_id)
    if search:
        like = f"%{search}%"
        q = q.filter(db.or_(Employee.first_name.ilike(like), Employee.last_name.ilike(like),
                             Employee.employee_code.ilike(like), Employee.phone.ilike(like)))
    employees = q.order_by(Employee.first_name).paginate(page=page, per_page=25)
    return render_template("hr/index.html", tab=tab, employees=employees, search=search)


@hr_bp.route("/employee/new", methods=["GET","POST"])
@login_required
@require_permission("hr","create")
def employee_new():
    branch_id   = current_user.branch_id
    branch      = Branch.query.get(branch_id) if branch_id else None
    departments = Department.query.filter_by(branch_id=branch_id, is_deleted=False).all()
    designations= Designation.query.filter_by(branch_id=branch_id, is_deleted=False).all()

    if request.method == "POST":
        try:
            emp = Employee(
                branch_id=branch_id,
                employee_code=generate_employee_code(branch.code if branch else "GEN"),
                first_name=request.form.get("first_name","").strip(),
                last_name=request.form.get("last_name","").strip() or None,
                department_id=request.form.get("department_id") or None,
                designation_id=request.form.get("designation_id") or None,
                phone=request.form.get("phone","").strip(),
                email=request.form.get("email","").strip() or None,
                gender=request.form.get("gender") or None,
                date_of_birth=_parse_date(request.form.get("date_of_birth")),
                join_date=_parse_date(request.form.get("join_date")) or date.today(),
                employment_type=request.form.get("employment_type","fulltime"),
                pan_number=request.form.get("pan_number","").strip() or None,
                bank_account=request.form.get("bank_account","").strip() or None,
                bank_ifsc=request.form.get("bank_ifsc","").strip() or None,
                bank_name=request.form.get("bank_name","").strip() or None,
                uan_number=request.form.get("uan_number","").strip() or None,
                esi_number=request.form.get("esi_number","").strip() or None,
                emergency_contact_name=request.form.get("emergency_contact_name","").strip() or None,
                emergency_contact_phone=request.form.get("emergency_contact_phone","").strip() or None,
                address=request.form.get("address","").strip() or None,
            )
            db.session.add(emp)
            db.session.commit()
            log_action("CREATE","hr",record_id=emp.id,record_type="Employee",
                       new_value={"code":emp.employee_code,"name":emp.full_name})
            flash(f"Employee {emp.employee_code} registered.","success")
            return redirect(url_for("hr.index"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error: {e}","danger")

    return render_template("hr/employee_form.html",
                           employee=None, departments=departments, designations=designations)


@hr_bp.route("/employee/<int:emp_id>/edit", methods=["GET","POST"])
@login_required
@require_permission("hr","edit")
def employee_edit(emp_id):
    emp         = Employee.query.get_or_404(emp_id)
    branch_id   = current_user.branch_id
    departments = Department.query.filter_by(branch_id=branch_id, is_deleted=False).all()
    designations= Designation.query.filter_by(branch_id=branch_id, is_deleted=False).all()

    if request.method == "POST":
        try:
            emp.first_name       = request.form.get("first_name","").strip()
            emp.last_name        = request.form.get("last_name","").strip() or None
            emp.department_id    = request.form.get("department_id") or None
            emp.designation_id   = request.form.get("designation_id") or None
            emp.phone            = request.form.get("phone","").strip()
            emp.email            = request.form.get("email","").strip() or None
            emp.employment_type  = request.form.get("employment_type","fulltime")
            emp.is_active        = request.form.get("is_active") == "on"
            emp.bank_account     = request.form.get("bank_account","").strip() or None
            emp.bank_ifsc        = request.form.get("bank_ifsc","").strip() or None
            emp.bank_name        = request.form.get("bank_name","").strip() or None
            db.session.commit()
            log_action("UPDATE","hr",record_id=emp.id,record_type="Employee")
            flash("Employee updated.","success")
            return redirect(url_for("hr.index"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error: {e}","danger")

    return render_template("hr/employee_form.html",
                           employee=emp, departments=departments, designations=designations)


@hr_bp.route("/attendance/save", methods=["POST"])
@login_required
@require_permission("hr","create")
def attendance_save():
    branch_id = current_user.branch_id
    att_date  = request.form.get("att_date", date.today().isoformat())
    emp_ids   = request.form.getlist("emp_id[]")
    statuses  = request.form.getlist("status[]")
    check_ins = request.form.getlist("check_in[]")
    check_outs= request.form.getlist("check_out[]")

    for i, emp_id in enumerate(emp_ids):
        status    = statuses[i] if i < len(statuses) else "present"
        check_in  = check_ins[i]  if i < len(check_ins)  else None
        check_out = check_outs[i] if i < len(check_outs) else None

        existing = Attendance.query.filter_by(
            employee_id=int(emp_id),
            attendance_date=datetime.strptime(att_date, "%Y-%m-%d").date()
        ).first()

        if existing:
            existing.status    = status
            existing.check_in  = datetime.strptime(check_in,"%H:%M").time() if check_in else None
            existing.check_out = datetime.strptime(check_out,"%H:%M").time() if check_out else None
            existing.marked_by = current_user.id
        else:
            att = Attendance(
                branch_id=branch_id,
                employee_id=int(emp_id),
                attendance_date=datetime.strptime(att_date,"%Y-%m-%d").date(),
                status=status,
                check_in=datetime.strptime(check_in,"%H:%M").time() if check_in else None,
                check_out=datetime.strptime(check_out,"%H:%M").time() if check_out else None,
                marked_by=current_user.id,
            )
            db.session.add(att)

    db.session.commit()
    flash("Attendance saved.","success")
    return redirect(url_for("hr.index", tab="attendance", att_date=att_date))


@hr_bp.route("/leave/apply", methods=["POST"])
@login_required
@require_permission("hr","create")
def leave_apply():
    branch_id = current_user.branch_id
    try:
        emp_id   = int(request.form.get("employee_id"))
        lt_id    = int(request.form.get("leave_type_id"))
        from_d   = datetime.strptime(request.form.get("from_date"),"%Y-%m-%d").date()
        to_d     = datetime.strptime(request.form.get("to_date"),"%Y-%m-%d").date()
        days     = (to_d - from_d).days + 1
        reason   = request.form.get("reason","").strip()
        lr = LeaveRequest(
            branch_id=branch_id, employee_id=emp_id,
            leave_type_id=lt_id, from_date=from_d, to_date=to_d,
            total_days=days, reason=reason, status="pending",
        )
        db.session.add(lr)
        db.session.commit()
        flash("Leave request submitted.","success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}","danger")
    return redirect(url_for("hr.index", tab="leave"))


@hr_bp.route("/leave/<int:lr_id>/approve", methods=["POST"])
@login_required
@require_permission("hr","edit")
def leave_approve(lr_id):
    lr = LeaveRequest.query.get_or_404(lr_id)
    action = request.form.get("action","approve")
    lr.status      = "approved" if action=="approve" else "rejected"
    lr.reviewed_by = current_user.id
    lr.reviewed_at = datetime.now(timezone.utc)
    lr.review_remarks = request.form.get("remarks","")
    db.session.commit()
    flash(f"Leave {lr.status}.","success")
    return redirect(url_for("hr.index", tab="leave"))


@hr_bp.route("/bulk-upload", methods=["GET","POST"])
@login_required
@require_permission("hr","create")
def bulk_upload():
    if request.method == "POST":
        file = request.files.get("file")
        if not file or not file.filename:
            flash("No file selected.","danger")
            return redirect(request.url)
        ext = file.filename.rsplit(".",1)[-1].lower()
        filename = secure_filename(f"bulk_employees_{datetime.now().strftime('%Y%m%d%H%M%S')}.{ext}")
        save_path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
        file.save(save_path)
        result = process_bulk_upload(save_path, "employees", current_user.branch_id, current_user.id)
        os.remove(save_path)
        return render_template("hr/bulk_result.html", result=result)
    return render_template("hr/bulk_upload.html")


@hr_bp.route("/download-template")
@login_required
def download_template():
    import io
    data = generate_upload_template("employees")
    return send_file(io.BytesIO(data),
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name="Employee_Upload_Template.xlsx")


def _get_attendance(branch_id, att_date):
    d = datetime.strptime(att_date,"%Y-%m-%d").date()
    return Attendance.query.join(Employee).filter(
        Employee.branch_id == branch_id if branch_id else True,
        Attendance.attendance_date == d,
        Attendance.is_deleted == False,
    ).all()


def _parse_date(value):
    if not value: return None
    for fmt in ("%Y-%m-%d","%d/%m/%Y","%d-%m-%Y"):
        try: return datetime.strptime(value, fmt).date()
        except ValueError: continue
    return None
