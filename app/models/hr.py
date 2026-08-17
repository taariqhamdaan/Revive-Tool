# MediCore - app/models/hr.py
# HR: Employee master, attendance, leave types, leave requests, shifts.

from datetime import datetime, timezone
from app.extensions import db


class Employee(db.Model):
    """
    Staff / employee master record.
    Linked to User account (for those who log in) and Doctor record (for clinical staff).
    Employee code is auto-generated per branch.
    """
    __tablename__ = "employees"

    id               = db.Column(db.Integer, primary_key=True)
    branch_id        = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    department_id    = db.Column(db.Integer, db.ForeignKey("departments.id"))
    designation_id   = db.Column(db.Integer, db.ForeignKey("designations.id"))
    employee_code    = db.Column(db.String(30), unique=True, nullable=False)

    # Personal
    first_name       = db.Column(db.String(100), nullable=False)
    last_name        = db.Column(db.String(100))
    first_name_ta    = db.Column(db.String(100))
    date_of_birth    = db.Column(db.Date)
    gender           = db.Column(db.String(20))
    blood_group      = db.Column(db.String(5))
    nationality      = db.Column(db.String(50), default="Indian")
    marital_status   = db.Column(db.String(20))
    photo_path       = db.Column(db.String(255))

    # Contact
    phone            = db.Column(db.String(20), nullable=False)
    email            = db.Column(db.String(120))
    address          = db.Column(db.Text)
    emergency_contact_name = db.Column(db.String(150))
    emergency_contact_phone = db.Column(db.String(20))

    # Identity (stored as encrypted/masked)
    aadhaar_masked   = db.Column(db.String(20))
    pan_number       = db.Column(db.String(15))
    bank_account     = db.Column(db.String(30))   # store encrypted in production
    bank_ifsc        = db.Column(db.String(15))
    bank_name        = db.Column(db.String(100))
    uan_number       = db.Column(db.String(20))   # UAN for PF
    esi_number       = db.Column(db.String(20))

    # Employment
    join_date        = db.Column(db.Date, nullable=False)
    confirm_date     = db.Column(db.Date)
    exit_date        = db.Column(db.Date, nullable=True)
    employment_type  = db.Column(db.String(30), default="fulltime")
    # types: fulltime, parttime, contract, visiting, intern
    status           = db.Column(db.String(20), default="active")
    # status: active, inactive, resigned, terminated, on_leave

    is_active        = db.Column(db.Boolean, default=True)
    is_deleted       = db.Column(db.Boolean, default=False)
    created_at       = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at       = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                                 onupdate=lambda: datetime.now(timezone.utc))

    branch      = db.relationship("Branch", backref="employees")
    department  = db.relationship("Department", backref="employees")
    designation = db.relationship("Designation", backref="employees")

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name or ''}".strip()

    def __repr__(self):
        return f"<Employee {self.employee_code}: {self.full_name}>"


class Shift(db.Model):
    """Work shift definitions (Morning, Evening, Night, etc.)"""
    __tablename__ = "shifts"

    id           = db.Column(db.Integer, primary_key=True)
    branch_id    = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    name         = db.Column(db.String(50), nullable=False)
    name_ta      = db.Column(db.String(50))
    start_time   = db.Column(db.Time, nullable=False)
    end_time     = db.Column(db.Time, nullable=False)
    duration_hrs = db.Column(db.Numeric(4, 2))
    is_night     = db.Column(db.Boolean, default=False)
    is_active    = db.Column(db.Boolean, default=True)
    is_deleted   = db.Column(db.Boolean, default=False)


class Attendance(db.Model):
    """
    Daily attendance record per employee.
    Can be entered manually or imported from biometric device (future).
    """
    __tablename__ = "attendance"

    id               = db.Column(db.Integer, primary_key=True)
    branch_id        = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    employee_id      = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    shift_id         = db.Column(db.Integer, db.ForeignKey("shifts.id"), nullable=True)
    attendance_date  = db.Column(db.Date, nullable=False)
    status           = db.Column(db.String(20), default="present")
    # status: present, absent, half_day, late, on_leave, holiday, weekly_off
    check_in         = db.Column(db.Time)
    check_out        = db.Column(db.Time)
    work_hours       = db.Column(db.Numeric(4, 2))
    overtime_hours   = db.Column(db.Numeric(4, 2), default=0)
    late_minutes     = db.Column(db.Integer, default=0)
    remarks          = db.Column(db.String(255))
    marked_by        = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at       = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_deleted       = db.Column(db.Boolean, default=False)

    __table_args__ = (db.UniqueConstraint("employee_id", "attendance_date", name="uq_employee_date"),)

    employee = db.relationship("Employee", backref="attendance")


class LeaveType(db.Model):
    """Leave type master (CL, SL, EL, ML, Comp-off, LOP etc.)"""
    __tablename__ = "leave_types"

    id               = db.Column(db.Integer, primary_key=True)
    branch_id        = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    code             = db.Column(db.String(10), nullable=False)   # CL, SL, EL
    name             = db.Column(db.String(100), nullable=False)
    name_ta          = db.Column(db.String(100))
    annual_quota     = db.Column(db.Integer, default=0)    # days allowed per year
    is_paid          = db.Column(db.Boolean, default=True)
    is_carry_forward = db.Column(db.Boolean, default=False)
    max_carry_forward = db.Column(db.Integer, default=0)
    is_active        = db.Column(db.Boolean, default=True)
    is_deleted       = db.Column(db.Boolean, default=False)


class LeaveRequest(db.Model):
    """Leave application raised by or on behalf of an employee."""
    __tablename__ = "leave_requests"

    id              = db.Column(db.Integer, primary_key=True)
    branch_id       = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    employee_id     = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    leave_type_id   = db.Column(db.Integer, db.ForeignKey("leave_types.id"), nullable=False)
    from_date       = db.Column(db.Date, nullable=False)
    to_date         = db.Column(db.Date, nullable=False)
    total_days      = db.Column(db.Numeric(4, 1))
    reason          = db.Column(db.Text)
    status          = db.Column(db.String(20), default="pending")
    # status: pending, approved, rejected, cancelled
    applied_at      = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    reviewed_by     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    reviewed_at     = db.Column(db.DateTime, nullable=True)
    review_remarks  = db.Column(db.String(255))
    is_deleted      = db.Column(db.Boolean, default=False)

    employee   = db.relationship("Employee", backref="leave_requests")
    leave_type = db.relationship("LeaveType", backref="leave_requests")
