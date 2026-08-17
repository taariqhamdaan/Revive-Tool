# Revive - app/utils/bulk_upload.py
# Bulk upload processor for Excel/CSV files.
# Handles patients, drugs, employees, test master, etc.
# Returns structured result: success_count, error_count, error_rows (for user feedback).

import pandas as pd
import logging
from datetime import datetime, date
from typing import Tuple, List, Dict, Any

logger = logging.getLogger(__name__)

# ── Column maps: Excel header → model field ────────────────────────────────────

PATIENT_COLUMNS = {
    "First Name*": "first_name",
    "Last Name": "last_name",
    "Date of Birth (DD/MM/YYYY)": "date_of_birth",
    "Age": "age_years",
    "Gender*": "gender",
    "Phone*": "phone",
    "Email": "email",
    "Blood Group": "blood_group",
    "Address": "address",
    "City": "city",
    "Pincode": "pincode",
    "ABHA Number": "abha_number",
}

DRUG_COLUMNS = {
    "Generic Name*": "generic_name",
    "Brand Name": "brand_name",
    "Category": "category_name",
    "Strength": "strength",
    "Form*": "form",
    "Unit": "unit_of_measure",
    "HSN Code": "hsn_code",
    "GST %": "gst_percent",
    "Reorder Level": "reorder_level",
    "MRP": "mrp",
    "Purchase Rate": "purchase_rate",
    "Sale Rate": "sale_rate",
    "Schedule": "schedule",
}

EMPLOYEE_COLUMNS = {
    "First Name*": "first_name",
    "Last Name": "last_name",
    "Department": "department_name",
    "Designation": "designation_name",
    "Phone*": "phone",
    "Email": "email",
    "Gender": "gender",
    "Date of Birth (DD/MM/YYYY)": "date_of_birth",
    "Join Date* (DD/MM/YYYY)": "join_date",
    "Employment Type": "employment_type",
    "PAN": "pan_number",
    "Bank Account": "bank_account",
    "IFSC": "bank_ifsc",
    "Bank Name": "bank_name",
}

TEST_COLUMNS = {
    "Test Code": "test_code",
    "Test Name*": "name",
    "Category": "category_name",
    "Sample Type": "sample_type",
    "Unit": "unit",
    "Normal Range": "normal_range",
    "Male Range": "male_range",
    "Female Range": "female_range",
    "Price": "price",
    "Turnaround (hrs)": "turnaround_hrs",
}


# ── Main processor ─────────────────────────────────────────────────────────────

def process_bulk_upload(
    file_path: str,
    upload_type: str,
    branch_id: int,
    user_id: int,
) -> Dict[str, Any]:
    """
    Process a bulk upload file.

    Parameters:
        file_path   — absolute path to uploaded xlsx/csv file
        upload_type — 'patients', 'drugs', 'employees', 'tests'
        branch_id   — branch context
        user_id     — who uploaded

    Returns dict:
        {
            success_count: int,
            error_count: int,
            errors: [{'row': N, 'error': 'message'}, ...],
            inserted_ids: [list of new record ids],
        }
    """
    result = {
        "success_count": 0,
        "error_count": 0,
        "errors": [],
        "inserted_ids": [],
    }

    try:
        df = _read_file(file_path)
    except Exception as e:
        result["errors"].append({"row": 0, "error": f"Cannot read file: {e}"})
        result["error_count"] = 1
        return result

    if upload_type == "patients":
        return _process_patients(df, branch_id, user_id, result)
    elif upload_type == "drugs":
        return _process_drugs(df, branch_id, user_id, result)
    elif upload_type == "employees":
        return _process_employees(df, branch_id, user_id, result)
    elif upload_type == "tests":
        return _process_tests(df, branch_id, user_id, result)
    else:
        result["errors"].append({"row": 0, "error": f"Unknown upload type: {upload_type}"})
        return result


# ── Per-type processors ────────────────────────────────────────────────────────

def _process_patients(df, branch_id, user_id, result):
    from app.extensions import db
    from app.models.patients import Patient
    from app.models.foundation import Branch
    from app.utils.generators import generate_uhid

    branch = Branch.query.get(branch_id)
    df = _normalise_headers(df, PATIENT_COLUMNS)

    for idx, row in df.iterrows():
        row_num = idx + 2  # Excel row (1=header, so data starts at 2)
        try:
            errors = _validate_patient_row(row, row_num)
            if errors:
                result["errors"].extend(errors)
                result["error_count"] += len(errors)
                continue

            # Check duplicate by phone + branch
            existing = Patient.query.filter_by(
                phone=str(row.get("phone", "")).strip(),
                branch_id=branch_id,
                is_deleted=False,
            ).first()
            if existing:
                result["errors"].append({
                    "row": row_num,
                    "error": f"Patient with phone {row.get('phone')} already exists (UHID: {existing.uhid})"
                })
                result["error_count"] += 1
                continue

            patient = Patient(
                branch_id=branch_id,
                uhid=generate_uhid(branch.code),
                first_name=str(row.get("first_name", "")).strip(),
                last_name=str(row.get("last_name", "")).strip() or None,
                date_of_birth=_parse_date(row.get("date_of_birth")),
                age_years=_safe_int(row.get("age_years")),
                gender=str(row.get("gender", "")).strip() or None,
                phone=str(row.get("phone", "")).strip(),
                email=str(row.get("email", "")).strip() or None,
                blood_group=str(row.get("blood_group", "")).strip() or None,
                address=str(row.get("address", "")).strip() or None,
                city=str(row.get("city", "")).strip() or None,
                pincode=str(row.get("pincode", "")).strip() or None,
                abha_number=str(row.get("abha_number", "")).strip() or None,
                created_by=user_id,
            )
            db.session.add(patient)
            db.session.flush()  # get id without committing
            result["inserted_ids"].append(patient.id)
            result["success_count"] += 1

        except Exception as e:
            result["errors"].append({"row": row_num, "error": str(e)})
            result["error_count"] += 1
            db.session.rollback()
            continue

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        result["errors"].append({"row": 0, "error": f"DB commit failed: {e}"})

    return result


def _process_drugs(df, branch_id, user_id, result):
    from app.extensions import db
    from app.models.pharmacy import DrugMaster, DrugCategory

    df = _normalise_headers(df, DRUG_COLUMNS)

    for idx, row in df.iterrows():
        row_num = idx + 2
        try:
            name = str(row.get("generic_name", "")).strip()
            if not name:
                result["errors"].append({"row": row_num, "error": "Generic Name is required"})
                result["error_count"] += 1
                continue

            # Resolve or create category
            cat_name = str(row.get("category_name", "")).strip()
            category = None
            if cat_name:
                category = DrugCategory.query.filter_by(
                    name=cat_name, branch_id=branch_id, is_deleted=False
                ).first()
                if not category:
                    category = DrugCategory(branch_id=branch_id, name=cat_name)
                    db.session.add(category)
                    db.session.flush()

            drug = DrugMaster(
                branch_id=branch_id,
                category_id=category.id if category else None,
                generic_name=name,
                brand_name=str(row.get("brand_name", "")).strip() or None,
                strength=str(row.get("strength", "")).strip() or None,
                form=str(row.get("form", "")).strip() or None,
                unit_of_measure=str(row.get("unit_of_measure", "")).strip() or None,
                hsn_code=str(row.get("hsn_code", "")).strip() or None,
                gst_percent=_safe_decimal(row.get("gst_percent"), 12),
                reorder_level=_safe_int(row.get("reorder_level")) or 10,
                mrp=_safe_decimal(row.get("mrp")),
                purchase_rate=_safe_decimal(row.get("purchase_rate")),
                sale_rate=_safe_decimal(row.get("sale_rate")),
                schedule=str(row.get("schedule", "")).strip() or None,
            )
            db.session.add(drug)
            db.session.flush()
            result["inserted_ids"].append(drug.id)
            result["success_count"] += 1

        except Exception as e:
            result["errors"].append({"row": row_num, "error": str(e)})
            result["error_count"] += 1
            db.session.rollback()

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        result["errors"].append({"row": 0, "error": f"DB commit failed: {e}"})

    return result


def _process_employees(df, branch_id, user_id, result):
    from app.extensions import db
    from app.models.hr import Employee
    from app.models.foundation import Department, Designation
    from app.utils.generators import generate_employee_code
    from app.models.foundation import Branch

    branch = Branch.query.get(branch_id)
    df = _normalise_headers(df, EMPLOYEE_COLUMNS)

    for idx, row in df.iterrows():
        row_num = idx + 2
        try:
            first_name = str(row.get("first_name", "")).strip()
            phone = str(row.get("phone", "")).strip()
            join_date = _parse_date(row.get("join_date"))

            if not first_name:
                result["errors"].append({"row": row_num, "error": "First Name is required"})
                result["error_count"] += 1
                continue
            if not phone:
                result["errors"].append({"row": row_num, "error": "Phone is required"})
                result["error_count"] += 1
                continue
            if not join_date:
                result["errors"].append({"row": row_num, "error": "Join Date is required"})
                result["error_count"] += 1
                continue

            # Resolve department
            dept_id = None
            dept_name = str(row.get("department_name", "")).strip()
            if dept_name:
                dept = Department.query.filter_by(name=dept_name, branch_id=branch_id).first()
                if dept:
                    dept_id = dept.id

            # Resolve designation
            desig_id = None
            desig_name = str(row.get("designation_name", "")).strip()
            if desig_name:
                desig = Designation.query.filter_by(name=desig_name, branch_id=branch_id).first()
                if desig:
                    desig_id = desig.id

            emp = Employee(
                branch_id=branch_id,
                employee_code=generate_employee_code(branch.code),
                first_name=first_name,
                last_name=str(row.get("last_name", "")).strip() or None,
                department_id=dept_id,
                designation_id=desig_id,
                phone=phone,
                email=str(row.get("email", "")).strip() or None,
                gender=str(row.get("gender", "")).strip() or None,
                date_of_birth=_parse_date(row.get("date_of_birth")),
                join_date=join_date,
                employment_type=str(row.get("employment_type", "fulltime")).strip().lower() or "fulltime",
                pan_number=str(row.get("pan_number", "")).strip() or None,
                bank_account=str(row.get("bank_account", "")).strip() or None,
                bank_ifsc=str(row.get("bank_ifsc", "")).strip() or None,
                bank_name=str(row.get("bank_name", "")).strip() or None,
            )
            db.session.add(emp)
            db.session.flush()
            result["inserted_ids"].append(emp.id)
            result["success_count"] += 1

        except Exception as e:
            result["errors"].append({"row": row_num, "error": str(e)})
            result["error_count"] += 1
            db.session.rollback()

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        result["errors"].append({"row": 0, "error": f"DB commit failed: {e}"})

    return result


def _process_tests(df, branch_id, user_id, result):
    from app.extensions import db
    from app.models.lab import TestMaster, TestCategory

    df = _normalise_headers(df, TEST_COLUMNS)

    for idx, row in df.iterrows():
        row_num = idx + 2
        try:
            name = str(row.get("name", "")).strip()
            if not name:
                result["errors"].append({"row": row_num, "error": "Test Name is required"})
                result["error_count"] += 1
                continue

            cat_name = str(row.get("category_name", "")).strip()
            category = None
            if cat_name:
                category = TestCategory.query.filter_by(name=cat_name, branch_id=branch_id).first()
                if not category:
                    category = TestCategory(branch_id=branch_id, name=cat_name)
                    db.session.add(category)
                    db.session.flush()

            test = TestMaster(
                branch_id=branch_id,
                category_id=category.id if category else None,
                test_code=str(row.get("test_code", "")).strip() or None,
                name=name,
                sample_type=str(row.get("sample_type", "")).strip() or None,
                unit=str(row.get("unit", "")).strip() or None,
                normal_range=str(row.get("normal_range", "")).strip() or None,
                male_range=str(row.get("male_range", "")).strip() or None,
                female_range=str(row.get("female_range", "")).strip() or None,
                price=_safe_decimal(row.get("price")),
                turnaround_hrs=_safe_int(row.get("turnaround_hrs")) or 24,
            )
            db.session.add(test)
            db.session.flush()
            result["inserted_ids"].append(test.id)
            result["success_count"] += 1

        except Exception as e:
            result["errors"].append({"row": row_num, "error": str(e)})
            result["error_count"] += 1
            db.session.rollback()

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        result["errors"].append({"row": 0, "error": f"DB commit failed: {e}"})

    return result


# ── Template generators (for download) ────────────────────────────────────────

def generate_upload_template(upload_type: str) -> bytes:
    """Generate a blank Excel template with correct headers for a given upload type."""
    column_maps = {
        "patients": PATIENT_COLUMNS,
        "drugs": DRUG_COLUMNS,
        "employees": EMPLOYEE_COLUMNS,
        "tests": TEST_COLUMNS,
    }
    columns = column_maps.get(upload_type, {})
    if not columns:
        return b""

    import io
    df = pd.DataFrame(columns=list(columns.keys()))
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Upload")
        worksheet = writer.sheets["Upload"]
        # Auto-width columns
        for i, col in enumerate(df.columns):
            worksheet.set_column(i, i, max(len(col) + 4, 20))
    return buffer.getvalue()


# ── Internal helpers ───────────────────────────────────────────────────────────

def _read_file(path: str) -> pd.DataFrame:
    if path.endswith(".csv"):
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    return pd.read_excel(path, dtype=str, keep_default_na=False)


def _normalise_headers(df: pd.DataFrame, column_map: dict) -> pd.DataFrame:
    """Rename columns from Excel headers to model field names. Drop unmapped columns."""
    df = df.rename(columns=column_map)
    valid_fields = list(column_map.values())
    return df[[c for c in df.columns if c in valid_fields]]


def _validate_patient_row(row, row_num: int) -> list:
    errors = []
    if not str(row.get("first_name", "")).strip():
        errors.append({"row": row_num, "error": "First Name is required"})
    if not str(row.get("phone", "")).strip():
        errors.append({"row": row_num, "error": "Phone is required"})
    gender = str(row.get("gender", "")).strip().lower()
    if gender and gender not in ["male", "female", "other"]:
        errors.append({"row": row_num, "error": f"Invalid gender: {gender}. Use Male/Female/Other"})
    return errors


def _parse_date(value) -> date:
    if not value or str(value).strip() in ("", "nan", "None"):
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            continue
    return None


def _safe_int(value) -> int:
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return None


def _safe_decimal(value, default=None):
    try:
        return round(float(str(value).strip()), 2)
    except (ValueError, TypeError):
        return default
