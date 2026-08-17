# MediCore - app/utils/email.py
# Email service. Sends via Flask-Mail using templates stored in DB.
# Variables in templates use {{variable_name}} syntax.
# All sends are logged. Failures do not break the main request.

import re
import logging
from flask import current_app, render_template_string
from flask_mail import Message
from app.extensions import mail, db

logger = logging.getLogger(__name__)


def send_email(
    to: list,
    subject: str,
    body_html: str,
    body_text: str = None,
    cc: list = None,
    bcc: list = None,
    attachments: list = None,
) -> bool:
    """
    Send a raw email.

    Parameters:
        to          — list of recipient email strings
        subject     — email subject
        body_html   — HTML body
        body_text   — plain text fallback
        cc, bcc     — optional lists
        attachments — list of (filename, mimetype, data_bytes)

    Returns True on success, False on failure.
    """
    try:
        msg = Message(
            subject=subject,
            recipients=to,
            html=body_html,
            body=body_text or _html_to_text(body_html),
            cc=cc or [],
            bcc=bcc or [],
            sender=current_app.config.get("MAIL_DEFAULT_SENDER"),
        )
        if attachments:
            for filename, mimetype, data in attachments:
                msg.attach(filename, mimetype, data)

        mail.send(msg)
        logger.info(f"Email sent to {to} | Subject: {subject}")
        return True

    except Exception as e:
        logger.error(f"Email send failed to {to}: {e}")
        return False


def send_template_email(
    template_key: str,
    to: list,
    variables: dict = None,
    branch_id: int = None,
    cc: list = None,
    attachments: list = None,
) -> bool:
    """
    Send an email using a template stored in the EmailTemplate table.
    Variables are substituted using {{key}} syntax.

    Parameters:
        template_key — unique key from email_templates table
        to           — recipient list
        variables    — dict of substitution values e.g. {'patient_name': 'John'}
        branch_id    — look for branch-specific template first, fall back to global
    """
    from app.models.foundation import EmailTemplate

    # Fetch template: branch-specific first, then global
    template = None
    if branch_id:
        template = EmailTemplate.query.filter_by(
            template_key=template_key,
            branch_id=branch_id,
            is_active=True,
            is_deleted=False,
        ).first()

    if not template:
        template = EmailTemplate.query.filter_by(
            template_key=template_key,
            branch_id=None,
            is_active=True,
            is_deleted=False,
        ).first()

    if not template:
        logger.warning(f"Email template not found: {template_key}")
        return False

    variables = variables or {}

    # Substitute {{variable}} placeholders
    subject  = _substitute(template.subject, variables)
    body_html = _substitute(template.body_html, variables)
    body_text = _substitute(template.body_text or "", variables)

    return send_email(
        to=to,
        subject=subject,
        body_html=body_html,
        body_text=body_text,
        cc=cc,
        attachments=attachments,
    )


def send_password_reset_email(user, reset_url: str) -> bool:
    return send_template_email(
        template_key="password_reset",
        to=[user.email],
        variables={
            "user_name": user.full_name,
            "reset_url": reset_url,
            "app_name": current_app.config.get("APP_NAME", "MediCore"),
        },
    )


def send_appointment_confirmation(patient, appointment, doctor, branch) -> bool:
    return send_template_email(
        template_key="appointment_confirm",
        to=[patient.email] if patient.email else [],
        variables={
            "patient_name": patient.full_name,
            "doctor_name": doctor.full_name,
            "appointment_date": appointment.appointment_date.strftime("%d %b %Y"),
            "slot_time": appointment.slot_time.strftime("%I:%M %p") if appointment.slot_time else "N/A",
            "branch_name": branch.name,
            "token_number": appointment.token_number or "N/A",
        },
        branch_id=branch.id,
    )


def send_lab_report_ready(patient, order, branch) -> bool:
    if not patient.email:
        return False
    return send_template_email(
        template_key="lab_report_ready",
        to=[patient.email],
        variables={
            "patient_name": patient.full_name,
            "order_number": order.order_number,
            "branch_name": branch.name,
        },
        branch_id=branch.id,
    )


def send_payslip_email(employee, slip, pdf_bytes: bytes, month_label: str) -> bool:
    if not employee.email:
        return False
    return send_template_email(
        template_key="payslip",
        to=[employee.email],
        variables={
            "employee_name": employee.full_name,
            "month": month_label,
            "net_salary": f"₹{slip.net_salary:,.2f}",
        },
        attachments=[(f"PaySlip_{month_label}.pdf", "application/pdf", pdf_bytes)],
    )


def send_stock_alert_email(drug, current_stock: int, reorder_level: int, branch) -> bool:
    """Send low stock alert to branch admin email."""
    if not branch.email:
        return False
    return send_template_email(
        template_key="stock_alert",
        to=[branch.email],
        variables={
            "drug_name": drug.generic_name,
            "brand_name": drug.brand_name or "",
            "current_stock": current_stock,
            "reorder_level": reorder_level,
            "branch_name": branch.name,
        },
        branch_id=branch.id,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _substitute(text: str, variables: dict) -> str:
    """Replace {{key}} placeholders with values from variables dict."""
    if not text:
        return ""
    for key, value in variables.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text


def _html_to_text(html: str) -> str:
    """Very basic HTML to plain text strip for email fallback."""
    text = re.sub(r"<br\s*/?>", "\n", html or "")
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()
