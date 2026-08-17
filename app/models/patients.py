# Rivive - app/models/patients.py
# Patient master data. UHID (Unique Health ID) is auto-generated per branch.
# Sensitive fields (Aadhaar) are encrypted at application level.

from datetime import datetime, timezone
from app.extensions import db


class Patient(db.Model):
    """
    Master patient record. One record per patient (not per visit).
    UHID format: BR001-P-000001 (branch_code + P + sequential number).
    """
    __tablename__ = "patients"

    id               = db.Column(db.Integer, primary_key=True)
    branch_id        = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False)
    uhid             = db.Column(db.String(30), unique=True, nullable=False)   # auto-generated

    # Demographics
    first_name       = db.Column(db.String(100), nullable=False)
    last_name        = db.Column(db.String(100))
    first_name_ta    = db.Column(db.String(100))   # Tamil name
    last_name_ta     = db.Column(db.String(100))
    date_of_birth    = db.Column(db.Date)
    age_years        = db.Column(db.Integer)        # stored when DOB unknown
    age_months       = db.Column(db.Integer)        # for paediatric patients
    gender           = db.Column(db.String(20))     # Male, Female, Other
    blood_group      = db.Column(db.String(5))
    marital_status   = db.Column(db.String(20))
    religion         = db.Column(db.String(50))
    occupation       = db.Column(db.String(100))
    nationality      = db.Column(db.String(50), default="Indian")
    language_pref    = db.Column(db.String(10), default="en")

    # Contact
    phone            = db.Column(db.String(20), nullable=False)
    phone_alt        = db.Column(db.String(20))
    email            = db.Column(db.String(120))
    address          = db.Column(db.Text)
    city             = db.Column(db.String(100))
    state            = db.Column(db.String(100))
    pincode          = db.Column(db.String(10))

    # Identity (encrypted at application layer — stored as ciphertext)
    aadhaar_encrypted = db.Column(db.Text)          # encrypted
    aadhaar_masked    = db.Column(db.String(20))     # last 4 digits plain: XXXX-XXXX-1234
    abha_number       = db.Column(db.String(30))     # Ayushman Bharat Health Account

    # Photo
    photo_path       = db.Column(db.String(255))

    # Source
    referred_by      = db.Column(db.String(150))
    registration_type = db.Column(db.String(30), default="walkin")  # walkin, referred, online

    # Record state
    is_active        = db.Column(db.Boolean, default=True)
    is_deleted       = db.Column(db.Boolean, default=False)
    created_by       = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at       = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at       = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                                 onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    branch           = db.relationship("Branch", backref="patients")
    contacts         = db.relationship("PatientContact", backref="patient", lazy="dynamic")
    allergies        = db.relationship("PatientAllergy", backref="patient", lazy="dynamic")
    history          = db.relationship("PatientHistory", backref="patient", lazy="dynamic")
    documents        = db.relationship("PatientDocument", backref="patient", lazy="dynamic")
    insurance_list   = db.relationship("PatientInsurance", backref="patient", lazy="dynamic")

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name or ''}".strip()

    def __repr__(self):
        return f"<Patient {self.uhid}: {self.full_name}>"


class PatientContact(db.Model):
    """Emergency contacts / next of kin for a patient."""
    __tablename__ = "patient_contacts"

    id           = db.Column(db.Integer, primary_key=True)
    patient_id   = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    name         = db.Column(db.String(150), nullable=False)
    relationship = db.Column(db.String(50))   # Father, Mother, Spouse, etc.
    phone        = db.Column(db.String(20), nullable=False)
    phone_alt    = db.Column(db.String(20))
    address      = db.Column(db.Text)
    is_primary   = db.Column(db.Boolean, default=False)
    is_deleted   = db.Column(db.Boolean, default=False)


class PatientAllergy(db.Model):
    """Known allergies for a patient. Shown as warnings during prescription."""
    __tablename__ = "patient_allergies"

    id           = db.Column(db.Integer, primary_key=True)
    patient_id   = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    allergy_type = db.Column(db.String(50))    # Drug, Food, Environment, Other
    allergen     = db.Column(db.String(150), nullable=False)
    reaction     = db.Column(db.String(255))   # Rash, Anaphylaxis, etc.
    severity     = db.Column(db.String(20))    # Mild, Moderate, Severe
    noted_by     = db.Column(db.Integer, db.ForeignKey("users.id"))
    noted_at     = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_active    = db.Column(db.Boolean, default=True)
    is_deleted   = db.Column(db.Boolean, default=False)


class PatientHistory(db.Model):
    """
    Patient medical history entries.
    Each entry is a discrete fact (past surgery, chronic condition, family history).
    """
    __tablename__ = "patient_history"

    id           = db.Column(db.Integer, primary_key=True)
    patient_id   = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    history_type = db.Column(db.String(50))   # medical, surgical, family, social, obstetric
    description  = db.Column(db.Text, nullable=False)
    icd10_code   = db.Column(db.String(20))   # ICD-10 code if applicable
    since_date   = db.Column(db.Date)
    is_resolved  = db.Column(db.Boolean, default=False)
    noted_by     = db.Column(db.Integer, db.ForeignKey("users.id"))
    noted_at     = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_deleted   = db.Column(db.Boolean, default=False)


class PatientDocument(db.Model):
    """Uploaded documents — ID proof, old records, scan images, etc."""
    __tablename__ = "patient_documents"

    id            = db.Column(db.Integer, primary_key=True)
    patient_id    = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    doc_type      = db.Column(db.String(50))    # id_proof, old_record, scan, other
    doc_name      = db.Column(db.String(255), nullable=False)
    file_path     = db.Column(db.String(500), nullable=False)
    file_size_kb  = db.Column(db.Integer)
    mime_type     = db.Column(db.String(100))
    uploaded_by   = db.Column(db.Integer, db.ForeignKey("users.id"))
    uploaded_at   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_deleted    = db.Column(db.Boolean, default=False)


class PatientInsurance(db.Model):
    """Insurance / TPA policy records linked to a patient."""
    __tablename__ = "patient_insurance"

    id              = db.Column(db.Integer, primary_key=True)
    patient_id      = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    tpa_id          = db.Column(db.Integer, db.ForeignKey("tpa_master.id"), nullable=True)
    insurer_name    = db.Column(db.String(150))
    policy_number   = db.Column(db.String(100))
    member_id       = db.Column(db.String(100))
    group_number    = db.Column(db.String(100))
    valid_from      = db.Column(db.Date)
    valid_to        = db.Column(db.Date)
    coverage_amount = db.Column(db.Numeric(12, 2))
    is_primary      = db.Column(db.Boolean, default=True)
    is_active       = db.Column(db.Boolean, default=True)
    is_deleted      = db.Column(db.Boolean, default=False)
    created_at      = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
