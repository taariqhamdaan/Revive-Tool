# Rivive SCH - app/seed.py
# Creates the minimum rows the lab module needs to be usable:
# a branch, roles, an admin + a phlebotomist, and a starter test catalogue.
# Idempotent — safe to re-run against an existing database.

import os
from .extensions import db
from .models.foundation import Branch, Role, User, Doctor
from .models.lab import LabCategory, TestMaster


def _get_or_create(model, defaults=None, **lookup):
    obj = model.query.filter_by(**lookup).first()
    if obj:
        return obj, False
    params = dict(lookup)
    params.update(defaults or {})
    obj = model(**params)
    db.session.add(obj)
    db.session.flush()
    return obj, True


# (name, code, unit, normal_low, normal_high, critical_low, critical_high, price)
STARTER_TESTS = [
    ("Haematology", [
        ("Haemoglobin",        "HB",   "g/dL",    13.0, 17.0,  7.0, 20.0, 150),
        ("Total Leucocyte Count", "TLC", "/cumm", 4000, 11000, 2000, 30000, 200),
        ("Platelet Count",     "PLT",  "/cumm",  150000, 410000, 50000, 1000000, 200),
    ]),
    ("Biochemistry", [
        ("Fasting Blood Sugar", "FBS", "mg/dL",   70, 110,  40, 400, 120),
        ("Serum Creatinine",   "CREA", "mg/dL",  0.6, 1.3, 0.2, 8.0, 250),
        ("Total Cholesterol",  "CHOL", "mg/dL",    0, 200,None, 500, 300),
    ]),
    ("Serology", [
        ("Thyroid Stimulating Hormone", "TSH", "uIU/mL", 0.4, 4.0, 0.01, 100.0, 400),
    ]),
]


def run_seed():
    db.create_all()

    branch, _ = _get_or_create(
        Branch, code="MAIN",
        defaults={"name": "Rivive Main Branch", "phone": "0000000000",
                  "email": "main@rivive.local", "is_active": True},
    )

    admin_role, _ = _get_or_create(Role, name="Administrator", branch_id=branch.id)
    phleb_role, _ = _get_or_create(Role, name="Phlebotomist",  branch_id=branch.id)
    _get_or_create(Role, name="Lab Technician", branch_id=branch.id)

    username = os.environ.get("SEED_ADMIN_USERNAME", "admin")
    email    = os.environ.get("SEED_ADMIN_EMAIL", "admin@rivive.local")
    password = os.environ.get("SEED_ADMIN_PASSWORD")

    admin, created = _get_or_create(
        User, username=username,
        defaults={"email": email, "full_name": "System Administrator",
                  "branch_id": branch.id, "role_id": admin_role.id,
                  "is_active": True, "is_superadmin": True},
    )
    if created:
        if not password:
            raise SystemExit(
                "SEED_ADMIN_PASSWORD is not set. Set it before seeding, e.g.\n"
                '  Railway → Variables → SEED_ADMIN_PASSWORD=<a strong password>'
            )
        admin.set_password(password)
        print(f"Created admin user '{username}'.")
    else:
        print(f"Admin user '{username}' already exists — password left unchanged.")

    phleb, created = _get_or_create(
        User, username="phlebo1",
        defaults={"email": "phlebo1@rivive.local", "full_name": "Sample Collector",
                  "branch_id": branch.id, "role_id": phleb_role.id, "is_active": True},
    )
    if created and password:
        phleb.set_password(password)

    _get_or_create(
        Doctor, doctor_code="DR001", branch_id=branch.id,
        defaults={"title": "Dr.", "full_name": "Referring Physician",
                  "specialisation": "General Medicine", "is_active": True},
    )

    for cat_name, tests in STARTER_TESTS:
        category, _ = _get_or_create(
            LabCategory, name=cat_name, branch_id=branch.id,
            defaults={"code": cat_name[:3].upper(), "is_active": True},
        )
        for name, code, unit, nlo, nhi, clo, chi, price in tests:
            _get_or_create(
                TestMaster, test_code=code, branch_id=branch.id,
                defaults={
                    "test_name": name, "category_id": category.id,
                    "department": cat_name, "sample_type": "Blood",
                    "unit": unit,
                    "normal_range": f"{nlo}-{nhi}",
                    "normal_low": nlo, "normal_high": nhi,
                    "critical_low": clo, "critical_high": chi,
                    "price": price, "gst_percent": 0, "turnaround_hrs": 24,
                    "created_by": admin.id, "is_active": True,
                },
            )

    db.session.commit()
    print("Seed complete.")
