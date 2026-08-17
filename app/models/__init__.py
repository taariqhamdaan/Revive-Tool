# Revive - app/models/__init__.py
# Import all models so Flask-Migrate/SQLAlchemy can discover all tables.
# Order matters — base models before dependent ones.

from app.models.foundation import Branch, Department, Designation, SystemSetting, EmailTemplate
from app.models.users import User, Role, Permission, RolePermission, UserSession, PasswordHistory, AuditLog
from app.models.hr import Employee, Shift, Attendance, LeaveType, LeaveRequest
from app.models.patients import Patient, PatientContact, PatientAllergy, PatientHistory, PatientDocument, PatientInsurance
from app.models.opd import Doctor, DoctorSchedule, Appointment, Consultation, Prescription, PrescriptionItem, Referral
from app.models.ipd import Ward, Bed, Admission, DailyNote, DischargeSummary
from app.models.pharmacy import DrugCategory, DrugMaster, Supplier, PurchaseOrder, POItem, GRN, GRNItem, StockLedger, Dispensing, DispensingItem
from app.models.lab import TestCategory, TestMaster, TestPanel, TestPanelItem, LabOrder, LabOrderItem, LabResult
from app.models.radiology import InvestigationMaster, RadiologyOrder, RadiologyReport
from app.models.billing import TPAMaster, BillMaster, BillItem, Payment, Receipt, CreditNote, InsuranceClaim
from app.models.payroll import SalaryComponent, SalaryStructure, SalaryStructureItem, PayrollRun, PaySlip, PaySlipItem
