# MediCore - app/models/ipd.py
# Inpatient Department: Wards, Beds, Admissions, Daily Notes, Discharge Summaries.

from datetime import datetime, timezone
from app.extensions import db


class Ward(db.Model):
    """Ward master. Each branch has multiple wards (General, ICU, Maternity, etc.)"""
    __tablename__ = "wards"

    id           = db.Column(db.Integer, primary_key=True)
    branch_id    = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    ward_code    = db.Column(db.String(20), nullable=False)
    name         = db.Column(db.String(100), nullable=False)
    name_ta      = db.Column(db.String(100))
    ward_type    = db.Column(db.String(50))   # general, icu, maternity, paediatric, private
    floor        = db.Column(db.String(20))
    total_beds   = db.Column(db.Integer, default=0)
    charge_per_day = db.Column(db.Numeric(10, 2), default=0)
    is_active    = db.Column(db.Boolean, default=True)
    is_deleted   = db.Column(db.Boolean, default=False)
    created_at   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    branch = db.relationship("Branch", backref="wards")
    beds   = db.relationship("Bed", backref="ward", lazy="dynamic")

    def __repr__(self):
        return f"<Ward {self.ward_code}: {self.name}>"


class Bed(db.Model):
    """
    Individual bed within a ward. Status tracks real-time occupancy.
    bed_number is unique within a ward.
    """
    __tablename__ = "beds"

    id          = db.Column(db.Integer, primary_key=True)
    ward_id     = db.Column(db.Integer, db.ForeignKey("wards.id"), nullable=False)
    branch_id   = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    bed_number  = db.Column(db.String(20), nullable=False)
    bed_type    = db.Column(db.String(50))     # standard, deluxe, icu, isolation
    status      = db.Column(db.String(20), default="available")
    # status: available, occupied, reserved, maintenance, blocked
    is_active   = db.Column(db.Boolean, default=True)
    is_deleted  = db.Column(db.Boolean, default=False)

    __table_args__ = (db.UniqueConstraint("ward_id", "bed_number", name="uq_ward_bed"),)


class Admission(db.Model):
    """
    IPD Admission record. Links patient → bed → doctor.
    IP number is auto-generated per branch per year.
    """
    __tablename__ = "admissions"

    id              = db.Column(db.Integer, primary_key=True)
    branch_id       = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    patient_id      = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    doctor_id       = db.Column(db.Integer, db.ForeignKey("doctors.id"), nullable=False)
    bed_id          = db.Column(db.Integer, db.ForeignKey("beds.id"), nullable=False)
    ward_id         = db.Column(db.Integer, db.ForeignKey("wards.id"), nullable=False)
    ip_number       = db.Column(db.String(30), unique=True, nullable=False)  # auto-generated

    admission_date  = db.Column(db.DateTime, nullable=False)
    admission_type  = db.Column(db.String(30), default="elective")  # elective, emergency, transfer
    reason          = db.Column(db.Text)
    provisional_diagnosis = db.Column(db.Text)

    # Discharge
    discharge_date  = db.Column(db.DateTime, nullable=True)
    discharge_type  = db.Column(db.String(30))  # regular, against_advice, transfer, death
    final_diagnosis = db.Column(db.Text)

    # Status
    status          = db.Column(db.String(20), default="admitted")
    # status: admitted, discharged, transferred, deceased

    admitted_by     = db.Column(db.Integer, db.ForeignKey("users.id"))
    discharged_by   = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    is_deleted      = db.Column(db.Boolean, default=False)
    created_at      = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    patient = db.relationship("Patient", backref="admissions")
    doctor  = db.relationship("Doctor", backref="admissions")
    bed     = db.relationship("Bed", backref="admissions")
    ward    = db.relationship("Ward", backref="admissions")
    notes   = db.relationship("DailyNote", backref="admission", lazy="dynamic")

    def __repr__(self):
        return f"<Admission {self.ip_number}>"


class DailyNote(db.Model):
    """Doctor / nurse daily progress notes for an admitted patient."""
    __tablename__ = "daily_notes"

    id           = db.Column(db.Integer, primary_key=True)
    admission_id = db.Column(db.Integer, db.ForeignKey("admissions.id"), nullable=False)
    patient_id   = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    noted_by     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    note_type    = db.Column(db.String(30), default="progress")  # progress, nursing, dietary, physio
    note_date    = db.Column(db.Date, nullable=False)
    note_time    = db.Column(db.Time)

    # Vitals (optional per note)
    bp_systolic  = db.Column(db.Integer)
    bp_diastolic = db.Column(db.Integer)
    pulse_bpm    = db.Column(db.Integer)
    temp_celsius = db.Column(db.Numeric(4, 1))
    spo2_percent = db.Column(db.Integer)

    notes        = db.Column(db.Text, nullable=False)
    orders       = db.Column(db.Text)    # doctor orders for nursing
    is_deleted   = db.Column(db.Boolean, default=False)
    created_at   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class DischargeSummary(db.Model):
    """Structured discharge summary generated on patient discharge."""
    __tablename__ = "discharge_summaries"

    id                   = db.Column(db.Integer, primary_key=True)
    admission_id         = db.Column(db.Integer, db.ForeignKey("admissions.id"), nullable=False, unique=True)
    patient_id           = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    doctor_id            = db.Column(db.Integer, db.ForeignKey("doctors.id"), nullable=False)
    branch_id            = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)

    admission_diagnosis  = db.Column(db.Text)
    final_diagnosis      = db.Column(db.Text)
    procedures_done      = db.Column(db.Text)
    investigations       = db.Column(db.Text)
    treatment_given      = db.Column(db.Text)
    condition_on_discharge = db.Column(db.String(50))  # stable, critical, improved
    discharge_advice     = db.Column(db.Text)
    follow_up_date       = db.Column(db.Date)
    follow_up_instructions = db.Column(db.Text)
    medications_on_discharge = db.Column(db.Text)  # JSON list

    prepared_by          = db.Column(db.Integer, db.ForeignKey("users.id"))
    prepared_at          = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_deleted           = db.Column(db.Boolean, default=False)

    admission = db.relationship("Admission", backref="discharge_summary", uselist=False)
    preparer  = db.relationship("User", foreign_keys=[prepared_by])
