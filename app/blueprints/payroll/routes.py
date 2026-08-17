# MediCore - app/blueprints/payroll/routes.py
# Payroll: salary components, structures, monthly run, payslip generation.

from datetime import date, datetime, timezone
from flask import (Blueprint, render_template, redirect, url_for,
                   request, flash, send_file, current_app)
from flask_login import login_required, current_user
from app.extensions import db
from app.models.payroll import (SalaryComponent, SalaryStructure, SalaryStructureItem,
                                 PayrollRun, PaySlip, PaySlipItem)
from app.models.hr import Employee, Attendance, LeaveType, LeaveRequest
from app.models.foundation import Branch
from app.utils.decorators import require_permission
from app.utils.audit import log_action

payroll_bp = Blueprint("payroll", __name__)


@payroll_bp.route("/")
@login_required
@require_permission("payroll","view")
def index():
    tab       = request.args.get("tab","runs")
    branch_id = current_user.branch_id

    if tab == "components":
        components = SalaryComponent.query.filter(
            db.or_(SalaryComponent.branch_id==branch_id, SalaryComponent.branch_id==None),
            SalaryComponent.is_deleted==False,
        ).order_by(SalaryComponent.sort_order, SalaryComponent.type).all()
        return render_template("payroll/index.html", tab=tab, components=components)

    elif tab == "structures":
        structures = SalaryStructure.query.join(Employee).filter(
            Employee.branch_id == branch_id if branch_id else True,
            SalaryStructure.is_deleted==False, SalaryStructure.is_active==True,
        ).order_by(Employee.first_name).all()
        employees = Employee.query.filter_by(branch_id=branch_id, is_active=True, is_deleted=False).all()
        components = SalaryComponent.query.filter(
            db.or_(SalaryComponent.branch_id==branch_id, SalaryComponent.branch_id==None),
            SalaryComponent.is_deleted==False, SalaryComponent.is_active==True,
        ).order_by(SalaryComponent.sort_order).all()
        return render_template("payroll/index.html", tab=tab, structures=structures,
                               employees=employees, components=components)

    elif tab == "slips":
        run_id = request.args.get("run_id", type=int)
        slips  = []
        if run_id:
            slips = PaySlip.query.filter_by(run_id=run_id, is_deleted=False).all()
        runs = PayrollRun.query.filter(
            PayrollRun.is_deleted==False,
            *([PayrollRun.branch_id==branch_id] if branch_id else []),
        ).order_by(PayrollRun.year.desc(), PayrollRun.month.desc()).all()
        return render_template("payroll/index.html", tab=tab, slips=slips,
                               runs=runs, selected_run_id=run_id)

    # Default: runs
    runs = PayrollRun.query.filter(
        PayrollRun.is_deleted==False,
        *([PayrollRun.branch_id==branch_id] if branch_id else []),
    ).order_by(PayrollRun.year.desc(), PayrollRun.month.desc()).all()
    return render_template("payroll/index.html", tab=tab, runs=runs)


@payroll_bp.route("/component/save", methods=["POST"])
@login_required
@require_permission("payroll","create")
def component_save():
    comp_id = request.form.get("comp_id")
    branch_id = current_user.branch_id
    if comp_id:
        c = SalaryComponent.query.get_or_404(int(comp_id))
    else:
        c = SalaryComponent(branch_id=branch_id)
        db.session.add(c)
    c.code       = request.form.get("code","").upper().strip()
    c.name       = request.form.get("name","").strip()
    c.type       = request.form.get("type","earning")
    c.calc_type  = request.form.get("calc_type","fixed")
    c.calc_value = request.form.get("calc_value",0) or 0
    c.is_taxable = request.form.get("is_taxable") == "on"
    c.is_pf_applicable  = request.form.get("is_pf_applicable") == "on"
    c.is_esi_applicable = request.form.get("is_esi_applicable") == "on"
    c.sort_order = request.form.get("sort_order",0) or 0
    db.session.commit()
    flash("Salary component saved.","success")
    return redirect(url_for("payroll.index", tab="components"))


@payroll_bp.route("/structure/save", methods=["POST"])
@login_required
@require_permission("payroll","create")
def structure_save():
    branch_id = current_user.branch_id
    try:
        emp_id = int(request.form.get("employee_id"))
        gross  = float(request.form.get("gross_salary","0") or 0)
        eff_from = datetime.strptime(request.form.get("effective_from"), "%Y-%m-%d").date()

        # Deactivate old structure
        SalaryStructure.query.filter_by(employee_id=emp_id, is_active=True).update({"is_active":False})

        struct = SalaryStructure(
            branch_id=branch_id, employee_id=emp_id,
            effective_from=eff_from, gross_salary=gross, is_active=True,
            created_by=current_user.id,
        )
        db.session.add(struct); db.session.flush()

        comp_ids = request.form.getlist("comp_id[]")
        amounts  = request.form.getlist("comp_amount[]")
        for i, cid in enumerate(comp_ids):
            if not cid: continue
            amt = float(amounts[i]) if i<len(amounts) and amounts[i] else 0
            si = SalaryStructureItem(structure_id=struct.id, component_id=int(cid), amount=amt)
            db.session.add(si)

        db.session.commit()
        log_action("CREATE","payroll",record_id=struct.id,record_type="SalaryStructure")
        flash("Salary structure saved.","success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}","danger")
    return redirect(url_for("payroll.index", tab="structures"))


@payroll_bp.route("/run/create", methods=["POST"])
@login_required
@require_permission("payroll","create")
def run_create():
    branch_id = current_user.branch_id
    try:
        month = int(request.form.get("month"))
        year  = int(request.form.get("year"))

        existing = PayrollRun.query.filter_by(branch_id=branch_id, month=month, year=year, is_deleted=False).first()
        if existing:
            flash("Payroll run already exists for this month.","warning")
            return redirect(url_for("payroll.index"))

        run = PayrollRun(
            branch_id=branch_id, month=month, year=year,
            status="draft", processed_by=current_user.id,
        )
        db.session.add(run); db.session.flush()

        # Auto-generate payslips
        employees = Employee.query.filter_by(branch_id=branch_id, is_active=True, is_deleted=False).all()
        total_gross = total_net = total_deductions = 0

        for emp in employees:
            struct = SalaryStructure.query.filter_by(employee_id=emp.id, is_active=True, is_deleted=False).first()
            if not struct: continue

            gross = float(struct.gross_salary)
            items = struct.components.filter_by(is_deleted=False).all()

            # Calculate working days in month
            import calendar
            working_days = _working_days(year, month)

            # Attendance
            present_days = Attendance.query.filter(
                Attendance.employee_id==emp.id,
                Attendance.status.in_(["present","half_day"]),
                db.extract("month", Attendance.attendance_date)==month,
                db.extract("year",  Attendance.attendance_date)==year,
            ).count()

            lop_days = max(0, working_days - present_days)

            # Earnings and deductions
            earnings = sum(float(i.amount) for i in items if i.component.type=="earning")
            deductions = sum(float(i.amount) for i in items if i.component.type=="deduction")

            # LOP deduction
            lop_deduct = round(gross / working_days * lop_days, 2) if working_days else 0
            net = round(earnings - deductions - lop_deduct, 2)

            slip = PaySlip(
                run_id=run.id, employee_id=emp.id, branch_id=branch_id,
                working_days=working_days, present_days=present_days, lop_days=lop_days,
                gross_earnings=earnings, total_deductions=deductions+lop_deduct,
                net_salary=net,
            )
            db.session.add(slip); db.session.flush()

            for i in items:
                db.session.add(PaySlipItem(slip_id=slip.id, component_id=i.component_id, amount=i.amount))

            total_gross += earnings
            total_deductions += deductions + lop_deduct
            total_net += net

        run.total_gross       = total_gross
        run.total_deductions  = total_deductions
        run.total_net         = total_net
        run.employee_count    = len(employees)
        run.processed_at      = datetime.now(timezone.utc)
        run.status            = "review"

        db.session.commit()
        log_action("CREATE","payroll",record_id=run.id,record_type="PayrollRun",
                   new_value={"month":month,"year":year,"employees":run.employee_count})
        flash(f"Payroll run created for {month}/{year}. {run.employee_count} slips generated.","success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}","danger")
    return redirect(url_for("payroll.index"))


@payroll_bp.route("/run/<int:run_id>/approve", methods=["POST"])
@login_required
@require_permission("payroll","approve")
def run_approve(run_id):
    run = PayrollRun.query.get_or_404(run_id)
    run.status      = "approved"
    run.approved_by = current_user.id
    run.approved_at = datetime.now(timezone.utc)
    db.session.commit()
    log_action("UPDATE","payroll",record_id=run_id,record_type="PayrollRun",new_value={"status":"approved"})
    flash("Payroll approved.","success")
    return redirect(url_for("payroll.index"))


def _working_days(year, month):
    import calendar
    _, days = calendar.monthrange(year, month)
    # Count Mon-Sat (exclude Sunday)
    return sum(1 for d in range(1, days+1)
               if datetime(year, month, d).weekday() != 6)
