# MediCore/Rivive SCH - app/models/opd.py
# OPD: Doctor, Schedule, Appointment, Consultation, Patient History (12 sections),
# Prescription, Referral. All history sections are queryable individually.

from datetime import datetime, timezone
from app.extensions import db


class Doctor(db.Model):
    __tablename__ = "doctors"
    id               = db.Column(db.Integer, primary_key=True)
    branch_id        = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    employee_id      = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=True)
    user_id          = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    doctor_code      = db.Column(db.String(20), unique=True)
    title            = db.Column(db.String(20))
    full_name        = db.Column(db.String(150), nullable=False)
    full_name_ta     = db.Column(db.String(150))
    specialisation   = db.Column(db.String(150))
    qualification    = db.Column(db.String(255))
    reg_number       = db.Column(db.String(100))
    department_id    = db.Column(db.Integer, db.ForeignKey("departments.id"))
    consultation_fee = db.Column(db.Numeric(10, 2), default=0)
    follow_up_fee    = db.Column(db.Numeric(10, 2), default=0)
    signature_path   = db.Column(db.String(255))
    is_surgical      = db.Column(db.Boolean, default=False)   # for surgery tab surgeon dropdown
    is_active        = db.Column(db.Boolean, default=True)
    is_deleted       = db.Column(db.Boolean, default=False)
    created_at       = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    branch     = db.relationship("Branch", backref="doctors")
    department = db.relationship("Department", backref="doctors")
    schedules  = db.relationship("DoctorSchedule", backref="doctor", lazy="dynamic")

    def __repr__(self):
        return f"<Doctor {self.doctor_code}: {self.full_name}>"


class DoctorSchedule(db.Model):
    __tablename__ = "doctor_schedules"
    id              = db.Column(db.Integer, primary_key=True)
    doctor_id       = db.Column(db.Integer, db.ForeignKey("doctors.id"), nullable=False)
    branch_id       = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    day_of_week     = db.Column(db.Integer, nullable=False)
    start_time      = db.Column(db.Time, nullable=False)
    end_time        = db.Column(db.Time, nullable=False)
    slot_duration   = db.Column(db.Integer, default=15)
    max_patients    = db.Column(db.Integer, default=20)
    schedule_type   = db.Column(db.String(20), default="opd")
    effective_from  = db.Column(db.Date)
    effective_to    = db.Column(db.Date, nullable=True)
    is_active       = db.Column(db.Boolean, default=True)
    is_deleted      = db.Column(db.Boolean, default=False)


class Appointment(db.Model):
    __tablename__ = "appointments"
    id               = db.Column(db.Integer, primary_key=True)
    branch_id        = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    patient_id       = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    doctor_id        = db.Column(db.Integer, db.ForeignKey("doctors.id"), nullable=False)
    appointment_date = db.Column(db.Date, nullable=False, index=True)
    slot_time        = db.Column(db.Time)
    token_number     = db.Column(db.Integer)
    visit_type       = db.Column(db.String(30), default="new")  # new, followup, review
    status           = db.Column(db.String(30), default="booked")
    reason           = db.Column(db.String(500))
    is_deleted       = db.Column(db.Boolean, default=False)
    created_at       = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    patient = db.relationship("Patient", backref="appointments")
    doctor  = db.relationship("Doctor", backref="appointments")

    def __repr__(self):
        return f"<Appointment {self.id}: {self.appointment_date} Token#{self.token_number}>"


class Consultation(db.Model):
    """
    Clinical consultation. Linked 1:1 to an Appointment.
    Vitals + clinical summary stored here.
    Detailed history stored in PatientHistory* child tables (queryable).
    """
    __tablename__ = "consultations"
    id               = db.Column(db.Integer, primary_key=True)
    appointment_id   = db.Column(db.Integer, db.ForeignKey("appointments.id"), nullable=False)
    patient_id       = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    doctor_id        = db.Column(db.Integer, db.ForeignKey("doctors.id"), nullable=False)
    branch_id        = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)

    # ── Vitals ────────────────────────────────────────────────────
    weight_kg        = db.Column(db.Numeric(5, 2))
    height_cm        = db.Column(db.Numeric(5, 2))
    bmi              = db.Column(db.Numeric(4, 2))
    bp_systolic      = db.Column(db.Integer)
    bp_diastolic     = db.Column(db.Integer)
    bp_arm           = db.Column(db.String(5), default="L")   # L or R
    pulse_bpm        = db.Column(db.Integer)
    heart_rate_bpm   = db.Column(db.Integer)
    temp_celsius     = db.Column(db.Numeric(4, 1))
    spo2_percent     = db.Column(db.Integer)
    cbg_mg_dl        = db.Column(db.Numeric(6, 2))            # Capillary Blood Glucose
    rr_per_min       = db.Column(db.Integer)
    blood_group      = db.Column(db.String(5))

    # ── Clinical summary ──────────────────────────────────────────
    chief_complaint    = db.Column(db.Text)
    duration_days      = db.Column(db.String(50))
    duration_months    = db.Column(db.String(50))
    diagnosis          = db.Column(db.Text)
    icd10_primary      = db.Column(db.String(20))
    icd10_secondary    = db.Column(db.Text)
    examination_notes  = db.Column(db.Text)
    treatment_plan     = db.Column(db.Text)       # visit notes
    advice             = db.Column(db.Text)
    special_advice     = db.Column(db.Text)       # remarks
    test_request       = db.Column(db.Text)
    follow_up_date     = db.Column(db.Date)
    follow_up_days     = db.Column(db.Integer)

    # ── Lab Investigation tab fields ───────────────────────────────
    lab_collection_date      = db.Column(db.Date)
    lab_sample_type          = db.Column(db.String(50))
    lab_fasting              = db.Column(db.String(20))       # fasting / non_fasting
    lab_special_instructions = db.Column(db.Text)
    lab_ordered_tests        = db.Column(db.Text)             # comma-separated test names

    # ── Scan tab fields ────────────────────────────────────────────
    scan_xray_ordered   = db.Column(db.Boolean, default=False)
    scan_xray_organ     = db.Column(db.String(200))
    scan_xray_position  = db.Column(db.String(200))
    scan_xray_desc      = db.Column(db.Text)
    scan_xray_config    = db.Column(db.String(200))
    scan_usg_ordered    = db.Column(db.Boolean, default=False)
    scan_usg_organ      = db.Column(db.String(200))
    scan_usg_position   = db.Column(db.String(200))
    scan_usg_desc       = db.Column(db.Text)
    scan_usg_config     = db.Column(db.String(200))
    scan_mri_ordered    = db.Column(db.Boolean, default=False)
    scan_mri_organ      = db.Column(db.String(200))
    scan_mri_position   = db.Column(db.String(200))
    scan_mri_desc       = db.Column(db.Text)
    scan_mri_config     = db.Column(db.String(200))
    scan_ct_ordered     = db.Column(db.Boolean, default=False)
    scan_ct_organ       = db.Column(db.String(200))
    scan_ct_position    = db.Column(db.String(200))
    scan_ct_desc        = db.Column(db.Text)
    scan_ct_config      = db.Column(db.String(200))
    scan_collection_date = db.Column(db.Date)
    scan_organisation   = db.Column(db.String(255))

    # ── Surgery tab fields ─────────────────────────────────────────
    surgery_plan           = db.Column(db.Text)
    surgery_procedure      = db.Column(db.String(255))
    surgeon_id             = db.Column(db.Integer, db.ForeignKey("doctors.id"), nullable=True)
    surgery_scheduled_date = db.Column(db.Date)
    anaesthesia_type       = db.Column(db.String(100))
    surgery_ward_ot        = db.Column(db.String(100))
    preop_tests            = db.Column(db.Text)
    surgery_notes          = db.Column(db.Text)
    surgery_night_notes    = db.Column(db.Text)

    consult_start = db.Column(db.DateTime)
    consult_end   = db.Column(db.DateTime)
    is_deleted    = db.Column(db.Boolean, default=False)
    created_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    appointment  = db.relationship("Appointment",
                                   backref=db.backref("consultation", uselist=False))
    patient      = db.relationship("Patient", backref="consultations")
    doctor       = db.relationship("Doctor", foreign_keys=[doctor_id],
                                   backref="consultations")
    surgeon      = db.relationship("Doctor", foreign_keys=[surgeon_id])
    prescription = db.relationship("Prescription", backref="consultation", uselist=False)

    # ── History child relationships ────────────────────────────────
    chief_complaints    = db.relationship("PatientHistoryChiefComplaint",
                                          backref="consultation", lazy="dynamic",
                                          cascade="all, delete-orphan")
    past_medical        = db.relationship("PatientHistoryPastMedical",
                                          backref="consultation", lazy="dynamic",
                                          cascade="all, delete-orphan")
    drug_history        = db.relationship("PatientHistoryDrug",
                                          backref="consultation", lazy="dynamic",
                                          cascade="all, delete-orphan")
    past_investigations = db.relationship("PatientHistoryPastInvestigation",
                                          backref="consultation", lazy="dynamic",
                                          cascade="all, delete-orphan")
    development_history = db.relationship("PatientHistoryDevelopment",
                                          backref="consultation", lazy="dynamic",
                                          cascade="all, delete-orphan")
    cross_consults      = db.relationship("PatientHistoryCrossConsult",
                                          backref="consultation", lazy="dynamic",
                                          cascade="all, delete-orphan")
    physio_history      = db.relationship("PatientHistoryPhysio",
                                          backref="consultation", lazy="dynamic",
                                          cascade="all, delete-orphan")
    birth_history       = db.relationship("PatientHistoryBirth",
                                          backref="consultation", lazy="dynamic",
                                          cascade="all, delete-orphan")
    nutrition_history   = db.relationship("PatientHistoryNutrition",
                                          backref="consultation", lazy="dynamic",
                                          cascade="all, delete-orphan")
    other_history       = db.relationship("PatientHistoryOther",
                                          backref="consultation", lazy="dynamic",
                                          cascade="all, delete-orphan")
    immunization        = db.relationship("PatientHistoryImmunization",
                                          backref="consultation", lazy="dynamic",
                                          cascade="all, delete-orphan")
    examination         = db.relationship("PatientHistoryExamination",
                                          backref="consultation", lazy="dynamic",
                                          cascade="all, delete-orphan")


# ══════════════════════════════════════════════════════════════════════════════
# Patient History — 12 queryable tables (Answer A: full queryability)
# Each table: patient_id + consultation_id + type + description + created_at
# Indexed on patient_id so "all patients with Penicillin allergy" is fast.
# ══════════════════════════════════════════════════════════════════════════════

class _HistoryBase:
    """Mixin shared by all 12 history tables."""
    id              = db.Column(db.Integer, primary_key=True)
    patient_id      = db.Column(db.Integer, db.ForeignKey("patients.id"),
                                nullable=False, index=True)
    consultation_id = db.Column(db.Integer, db.ForeignKey("consultations.id"),
                                nullable=False, index=True)
    entry_type      = db.Column(db.String(100))   # dropdown value
    description     = db.Column(db.Text, nullable=False)
    onset_date      = db.Column(db.Date, nullable=True)
    is_resolved     = db.Column(db.Boolean, default=False)
    is_deleted      = db.Column(db.Boolean, default=False)
    created_at      = db.Column(db.DateTime,
                                default=lambda: datetime.now(timezone.utc))

    patient = property(lambda self:
        db.relationship("Patient"))  # resolved via backref per table


class PatientHistoryChiefComplaint(_HistoryBase, db.Model):
    """Chief Complaints — queryable. entry_type: Acute/Chronic/Recurring."""
    __tablename__ = "patient_history_chief_complaints"
    id              = db.Column(db.Integer, primary_key=True)
    patient_id      = db.Column(db.Integer, db.ForeignKey("patients.id"),
                                nullable=False, index=True)
    consultation_id = db.Column(db.Integer, db.ForeignKey("consultations.id"),
                                nullable=False, index=True)
    entry_type      = db.Column(db.String(100))
    description     = db.Column(db.Text, nullable=False)
    duration_days   = db.Column(db.Integer)
    duration_months = db.Column(db.Integer)
    onset_date      = db.Column(db.Date, nullable=True)
    is_resolved     = db.Column(db.Boolean, default=False)
    is_deleted      = db.Column(db.Boolean, default=False)
    created_at      = db.Column(db.DateTime,
                                default=lambda: datetime.now(timezone.utc))
    patient = db.relationship("Patient", backref="chief_complaints")


class PatientHistoryPastMedical(_HistoryBase, db.Model):
    """Past Medical & Surgical History. entry_type: Medical/Surgical."""
    __tablename__ = "patient_history_past_medical"
    id              = db.Column(db.Integer, primary_key=True)
    patient_id      = db.Column(db.Integer, db.ForeignKey("patients.id"),
                                nullable=False, index=True)
    consultation_id = db.Column(db.Integer, db.ForeignKey("consultations.id"),
                                nullable=False, index=True)
    entry_type      = db.Column(db.String(100))   # Medical / Surgical
    description     = db.Column(db.Text, nullable=False)
    onset_date      = db.Column(db.Date, nullable=True)
    is_resolved     = db.Column(db.Boolean, default=False)
    is_deleted      = db.Column(db.Boolean, default=False)
    created_at      = db.Column(db.DateTime,
                                default=lambda: datetime.now(timezone.utc))
    patient = db.relationship("Patient", backref="past_medical_history")


class PatientHistoryDrug(_HistoryBase, db.Model):
    """
    Drug History — INDEXED for Penicillin-style queries.
    entry_type: Current Medication / Allergy / Adverse Reaction / Past Medication
    drug_name column is separately indexed for fast search.
    """
    __tablename__ = "patient_history_drug"
    id              = db.Column(db.Integer, primary_key=True)
    patient_id      = db.Column(db.Integer, db.ForeignKey("patients.id"),
                                nullable=False, index=True)
    consultation_id = db.Column(db.Integer, db.ForeignKey("consultations.id"),
                                nullable=False, index=True)
    entry_type      = db.Column(db.String(100), index=True)  # indexed
    drug_name       = db.Column(db.String(255), index=True)  # indexed — enables Penicillin query
    description     = db.Column(db.Text)
    dosage          = db.Column(db.String(100))
    route           = db.Column(db.String(50))
    severity        = db.Column(db.String(50))   # for allergies: Mild/Moderate/Severe
    onset_date      = db.Column(db.Date, nullable=True)
    is_resolved     = db.Column(db.Boolean, default=False)
    is_deleted      = db.Column(db.Boolean, default=False)
    created_at      = db.Column(db.DateTime,
                                default=lambda: datetime.now(timezone.utc))
    patient = db.relationship("Patient", backref="drug_history")


class PatientHistoryPastInvestigation(_HistoryBase, db.Model):
    """Past Investigation results. entry_type: Lab/Scan/ECG/Other."""
    __tablename__ = "patient_history_past_investigation"
    id              = db.Column(db.Integer, primary_key=True)
    patient_id      = db.Column(db.Integer, db.ForeignKey("patients.id"),
                                nullable=False, index=True)
    consultation_id = db.Column(db.Integer, db.ForeignKey("consultations.id"),
                                nullable=False, index=True)
    entry_type      = db.Column(db.String(100))
    test_name       = db.Column(db.String(255), index=True)
    result_value    = db.Column(db.String(255))
    result_unit     = db.Column(db.String(50))
    description     = db.Column(db.Text)
    test_date       = db.Column(db.Date)
    onset_date      = db.Column(db.Date, nullable=True)
    is_resolved     = db.Column(db.Boolean, default=False)
    is_deleted      = db.Column(db.Boolean, default=False)
    created_at      = db.Column(db.DateTime,
                                default=lambda: datetime.now(timezone.utc))
    patient = db.relationship("Patient", backref="past_investigations")


class PatientHistoryDevelopment(_HistoryBase, db.Model):
    """Development History (paediatric). entry_type: Motor/Speech/Social/Cognitive."""
    __tablename__ = "patient_history_development"
    id              = db.Column(db.Integer, primary_key=True)
    patient_id      = db.Column(db.Integer, db.ForeignKey("patients.id"),
                                nullable=False, index=True)
    consultation_id = db.Column(db.Integer, db.ForeignKey("consultations.id"),
                                nullable=False, index=True)
    entry_type      = db.Column(db.String(100))
    description     = db.Column(db.Text, nullable=False)
    milestone_age   = db.Column(db.String(50))
    onset_date      = db.Column(db.Date, nullable=True)
    is_resolved     = db.Column(db.Boolean, default=False)
    is_deleted      = db.Column(db.Boolean, default=False)
    created_at      = db.Column(db.DateTime,
                                default=lambda: datetime.now(timezone.utc))
    patient = db.relationship("Patient", backref="development_history")


class PatientHistoryCrossConsult(_HistoryBase, db.Model):
    """Cross Consult Reports from other specialists."""
    __tablename__ = "patient_history_cross_consult"
    id              = db.Column(db.Integer, primary_key=True)
    patient_id      = db.Column(db.Integer, db.ForeignKey("patients.id"),
                                nullable=False, index=True)
    consultation_id = db.Column(db.Integer, db.ForeignKey("consultations.id"),
                                nullable=False, index=True)
    entry_type      = db.Column(db.String(100))
    specialist_name = db.Column(db.String(255))
    hospital_name   = db.Column(db.String(255))
    description     = db.Column(db.Text, nullable=False)
    report_date     = db.Column(db.Date)
    onset_date      = db.Column(db.Date, nullable=True)
    is_resolved     = db.Column(db.Boolean, default=False)
    is_deleted      = db.Column(db.Boolean, default=False)
    created_at      = db.Column(db.DateTime,
                                default=lambda: datetime.now(timezone.utc))
    patient = db.relationship("Patient", backref="cross_consults")


class PatientHistoryPhysio(_HistoryBase, db.Model):
    """Physiotherapy history. entry_type: Current/Past/Recommended."""
    __tablename__ = "patient_history_physio"
    id              = db.Column(db.Integer, primary_key=True)
    patient_id      = db.Column(db.Integer, db.ForeignKey("patients.id"),
                                nullable=False, index=True)
    consultation_id = db.Column(db.Integer, db.ForeignKey("consultations.id"),
                                nullable=False, index=True)
    entry_type      = db.Column(db.String(100))
    description     = db.Column(db.Text, nullable=False)
    therapist_name  = db.Column(db.String(255))
    sessions_done   = db.Column(db.Integer)
    onset_date      = db.Column(db.Date, nullable=True)
    is_resolved     = db.Column(db.Boolean, default=False)
    is_deleted      = db.Column(db.Boolean, default=False)
    created_at      = db.Column(db.DateTime,
                                default=lambda: datetime.now(timezone.utc))
    patient = db.relationship("Patient", backref="physio_history")


class PatientHistoryBirth(_HistoryBase, db.Model):
    """Birth History (obstetric/neonatal). entry_type: Normal/LSCS/Premature/etc."""
    __tablename__ = "patient_history_birth"
    id              = db.Column(db.Integer, primary_key=True)
    patient_id      = db.Column(db.Integer, db.ForeignKey("patients.id"),
                                nullable=False, index=True)
    consultation_id = db.Column(db.Integer, db.ForeignKey("consultations.id"),
                                nullable=False, index=True)
    entry_type      = db.Column(db.String(100))
    description     = db.Column(db.Text, nullable=False)
    birth_weight    = db.Column(db.String(50))
    gestational_age = db.Column(db.String(50))
    onset_date      = db.Column(db.Date, nullable=True)
    is_resolved     = db.Column(db.Boolean, default=False)
    is_deleted      = db.Column(db.Boolean, default=False)
    created_at      = db.Column(db.DateTime,
                                default=lambda: datetime.now(timezone.utc))
    patient = db.relationship("Patient", backref="birth_history")


class PatientHistoryNutrition(_HistoryBase, db.Model):
    """Nutrition History. entry_type: Vegetarian/Non-Veg/Vegan/Mixed/Specific Diet."""
    __tablename__ = "patient_history_nutrition"
    id              = db.Column(db.Integer, primary_key=True)
    patient_id      = db.Column(db.Integer, db.ForeignKey("patients.id"),
                                nullable=False, index=True)
    consultation_id = db.Column(db.Integer, db.ForeignKey("consultations.id"),
                                nullable=False, index=True)
    entry_type      = db.Column(db.String(100))
    description     = db.Column(db.Text, nullable=False)
    onset_date      = db.Column(db.Date, nullable=True)
    is_resolved     = db.Column(db.Boolean, default=False)
    is_deleted      = db.Column(db.Boolean, default=False)
    created_at      = db.Column(db.DateTime,
                                default=lambda: datetime.now(timezone.utc))
    patient = db.relationship("Patient", backref="nutrition_history")


class PatientHistoryOther(_HistoryBase, db.Model):
    """Other History — free-form catchall."""
    __tablename__ = "patient_history_other"
    id              = db.Column(db.Integer, primary_key=True)
    patient_id      = db.Column(db.Integer, db.ForeignKey("patients.id"),
                                nullable=False, index=True)
    consultation_id = db.Column(db.Integer, db.ForeignKey("consultations.id"),
                                nullable=False, index=True)
    entry_type      = db.Column(db.String(100))
    description     = db.Column(db.Text, nullable=False)
    onset_date      = db.Column(db.Date, nullable=True)
    is_resolved     = db.Column(db.Boolean, default=False)
    is_deleted      = db.Column(db.Boolean, default=False)
    created_at      = db.Column(db.DateTime,
                                default=lambda: datetime.now(timezone.utc))
    patient = db.relationship("Patient", backref="other_history")


class PatientHistoryImmunization(_HistoryBase, db.Model):
    """Immunization Records. Searchable by vaccine name."""
    __tablename__ = "patient_history_immunization"
    id              = db.Column(db.Integer, primary_key=True)
    patient_id      = db.Column(db.Integer, db.ForeignKey("patients.id"),
                                nullable=False, index=True)
    consultation_id = db.Column(db.Integer, db.ForeignKey("consultations.id"),
                                nullable=False, index=True)
    entry_type      = db.Column(db.String(100))
    vaccine_name    = db.Column(db.String(255), index=True)
    description     = db.Column(db.Text)
    dose_number     = db.Column(db.String(20))
    given_date      = db.Column(db.Date)
    next_due_date   = db.Column(db.Date)
    onset_date      = db.Column(db.Date, nullable=True)
    is_resolved     = db.Column(db.Boolean, default=False)
    is_deleted      = db.Column(db.Boolean, default=False)
    created_at      = db.Column(db.DateTime,
                                default=lambda: datetime.now(timezone.utc))
    patient = db.relationship("Patient", backref="immunization_history")


class PatientHistoryExamination(_HistoryBase, db.Model):
    """Examination findings. entry_type: General/Systemic/Local/Neurological/etc."""
    __tablename__ = "patient_history_examination"
    id              = db.Column(db.Integer, primary_key=True)
    patient_id      = db.Column(db.Integer, db.ForeignKey("patients.id"),
                                nullable=False, index=True)
    consultation_id = db.Column(db.Integer, db.ForeignKey("consultations.id"),
                                nullable=False, index=True)
    entry_type      = db.Column(db.String(100))
    system          = db.Column(db.String(100))   # CVS, RS, CNS, GIT, MSK
    description     = db.Column(db.Text, nullable=False)
    onset_date      = db.Column(db.Date, nullable=True)
    is_resolved     = db.Column(db.Boolean, default=False)
    is_deleted      = db.Column(db.Boolean, default=False)
    created_at      = db.Column(db.DateTime,
                                default=lambda: datetime.now(timezone.utc))
    patient = db.relationship("Patient", backref="examination_findings")


# ══════════════════════════════════════════════════════════════════════════════
# Prescription
# ══════════════════════════════════════════════════════════════════════════════

class Prescription(db.Model):
    __tablename__ = "prescriptions"
    id              = db.Column(db.Integer, primary_key=True)
    consultation_id = db.Column(db.Integer, db.ForeignKey("consultations.id"), nullable=False)
    patient_id      = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    doctor_id       = db.Column(db.Integer, db.ForeignKey("doctors.id"), nullable=False)
    branch_id       = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    rx_number       = db.Column(db.String(30), unique=True)
    prescribed_at   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    notes           = db.Column(db.Text)
    dispensed       = db.Column(db.Boolean, default=False)
    is_deleted      = db.Column(db.Boolean, default=False)

    items   = db.relationship("PrescriptionItem", backref="prescription", lazy="dynamic")
    patient = db.relationship("Patient", backref="prescriptions")


class PrescriptionItem(db.Model):
    """Individual drug line. Stores MOR/ACT/NIGHT separately per Rivive spec."""
    __tablename__ = "prescription_items"
    id              = db.Column(db.Integer, primary_key=True)
    prescription_id = db.Column(db.Integer, db.ForeignKey("prescriptions.id"), nullable=False)
    drug_id         = db.Column(db.Integer, db.ForeignKey("drug_master.id"), nullable=True)
    drug_name       = db.Column(db.String(255), nullable=False)
    dosage          = db.Column(db.String(100))
    route           = db.Column(db.String(50))

    # Rivive prescription format: Morning / Afternoon / Night with BF/AF
    mor_qty         = db.Column(db.Numeric(4, 1), default=0)   # Morning quantity
    mor_timing      = db.Column(db.String(5), default="AF")    # BF or AF
    act_qty         = db.Column(db.Numeric(4, 1), default=0)   # Afternoon quantity
    act_timing      = db.Column(db.String(5), default="AF")
    night_qty       = db.Column(db.Numeric(4, 1), default=0)   # Night quantity
    night_timing    = db.Column(db.String(5), default="AF")

    duration_days   = db.Column(db.Integer)
    quantity        = db.Column(db.Integer)
    instructions    = db.Column(db.String(255))
    is_highlighted  = db.Column(db.Boolean, default=False)     # star = priority
    rx_language     = db.Column(db.String(5), default="en")    # en/ta/hi per row
    sort_order      = db.Column(db.Integer, default=0)
    is_deleted      = db.Column(db.Boolean, default=False)


class Referral(db.Model):
    __tablename__ = "referrals"
    id              = db.Column(db.Integer, primary_key=True)
    consultation_id = db.Column(db.Integer, db.ForeignKey("consultations.id"), nullable=False)
    patient_id      = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    from_doctor_id  = db.Column(db.Integer, db.ForeignKey("doctors.id"))
    to_doctor_id    = db.Column(db.Integer, db.ForeignKey("doctors.id"), nullable=True)
    to_doctor_name  = db.Column(db.String(150))
    to_hospital     = db.Column(db.String(255))
    referral_type   = db.Column(db.String(20))
    reason          = db.Column(db.Text)
    urgency         = db.Column(db.String(20), default="routine")
    status          = db.Column(db.String(30), default="pending")
    referred_at     = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_deleted      = db.Column(db.Boolean, default=False)
    patient         = db.relationship("Patient", backref="referrals")
