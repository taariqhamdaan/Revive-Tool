# Revive - app/blueprints/settings/routes.py
# Settings & CMS Panel. Tabs: Branches, Users, Roles & Permissions,
# System Settings, Email Templates, Audit Logs, Theme.
# Logic summary:
#   - Branches: CRUD for branch records, theme color picker
#   - Users: create/edit/deactivate users, assign roles
#   - Roles: create roles, assign permissions per module/action
#   - Permissions: auto-seed all permissions, toggle per role
#   - System Settings: key-value config per branch
#   - Email Templates: editor for each template key
#   - Audit Log: read-only viewer with filters
#   - Theme: per-branch CSS variable overrides

from flask import (Blueprint, render_template, redirect, url_for,
                   request, flash, jsonify, current_app)
from flask_login import login_required, current_user
from datetime import datetime, timezone

from app.extensions import db
from app.models.foundation import Branch, Department, Designation, SystemSetting, EmailTemplate
from app.models.users import User, Role, Permission, RolePermission, AuditLog
from app.utils.decorators import superadmin_required, branch_admin_required
from app.utils.audit import log_action

settings_bp = Blueprint("settings", __name__)

# ── All permission modules/actions seeded on first run ───────────────────────
ALL_PERMISSIONS = {
    "patients":   ["view", "create", "edit", "delete", "export"],
    "opd":        ["view", "create", "edit", "delete", "export"],
    "ipd":        ["view", "create", "edit", "delete", "export"],
    "pharmacy":   ["view", "create", "edit", "delete", "export", "purchase"],
    "lab":        ["view", "create", "edit", "delete", "export", "verify"],
    "radiology":  ["view", "create", "edit", "delete", "export"],
    "billing":    ["view", "create", "edit", "delete", "export", "refund"],
    "insurance":  ["view", "create", "edit", "delete", "export"],
    "hr":         ["view", "create", "edit", "delete", "export"],
    "payroll":    ["view", "create", "edit", "delete", "export", "approve"],
    "reports":    ["view", "export"],
    "settings":   ["view", "edit"],
    "audit":      ["view", "export"],
}


# ── Settings Home ─────────────────────────────────────────────────────────────

@settings_bp.route("/")
@login_required
@branch_admin_required
def index():
    return render_template("settings/index.html")


# ── Branches ──────────────────────────────────────────────────────────────────

@settings_bp.route("/branches")
@login_required
@superadmin_required
def branches():
    branches = Branch.query.filter_by(is_deleted=False).order_by(Branch.code).all()
    return render_template("settings/branches.html", branches=branches)


@settings_bp.route("/branches/new", methods=["GET", "POST"])
@login_required
@superadmin_required
def branch_new():
    if request.method == "POST":
        try:
            b = Branch(
                code=request.form.get("code", "").upper().strip(),
                name=request.form.get("name", "").strip(),
                name_ta=request.form.get("name_ta", "").strip() or None,
                address=request.form.get("address", "").strip() or None,
                city=request.form.get("city", "").strip() or None,
                state=request.form.get("state", "Tamil Nadu").strip(),
                pincode=request.form.get("pincode", "").strip() or None,
                phone=request.form.get("phone", "").strip() or None,
                email=request.form.get("email", "").strip() or None,
                gstin=request.form.get("gstin", "").strip() or None,
                reg_number=request.form.get("reg_number", "").strip() or None,
                theme_primary=request.form.get("theme_primary", "#0d6efd"),
                theme_accent=request.form.get("theme_accent", "#198754"),
            )
            db.session.add(b)
            db.session.commit()
            log_action("CREATE", "settings", record_id=b.id, record_type="Branch",
                       new_value={"code": b.code, "name": b.name})
            flash(f"Branch {b.code} created.", "success")
            return redirect(url_for("settings.branches"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error: {e}", "danger")
    return render_template("settings/branch_form.html", branch=None)


@settings_bp.route("/branches/<int:branch_id>/edit", methods=["GET", "POST"])
@login_required
@superadmin_required
def branch_edit(branch_id):
    branch = Branch.query.get_or_404(branch_id)
    if request.method == "POST":
        try:
            old = {"name": branch.name, "code": branch.code}
            branch.name    = request.form.get("name", "").strip()
            branch.name_ta = request.form.get("name_ta", "").strip() or None
            branch.address = request.form.get("address", "").strip() or None
            branch.city    = request.form.get("city", "").strip() or None
            branch.state   = request.form.get("state", "Tamil Nadu").strip()
            branch.pincode = request.form.get("pincode", "").strip() or None
            branch.phone   = request.form.get("phone", "").strip() or None
            branch.email   = request.form.get("email", "").strip() or None
            branch.gstin   = request.form.get("gstin", "").strip() or None
            branch.theme_primary = request.form.get("theme_primary", "#0d6efd")
            branch.theme_accent  = request.form.get("theme_accent", "#198754")
            db.session.commit()
            log_action("UPDATE", "settings", record_id=branch.id, record_type="Branch",
                       old_value=old, new_value={"name": branch.name})
            flash("Branch updated.", "success")
            return redirect(url_for("settings.branches"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error: {e}", "danger")
    return render_template("settings/branch_form.html", branch=branch)


# ── Users ─────────────────────────────────────────────────────────────────────

@settings_bp.route("/users")
@login_required
@branch_admin_required
def users():
    query = User.query.filter_by(is_deleted=False)
    if not current_user.is_superadmin:
        query = query.filter_by(branch_id=current_user.branch_id)
    users = query.order_by(User.full_name).all()
    return render_template("settings/users.html", users=users)


@settings_bp.route("/users/new", methods=["GET", "POST"])
@login_required
@branch_admin_required
def user_new():
    roles = _get_available_roles()
    branches = Branch.query.filter_by(is_active=True, is_deleted=False).all() if current_user.is_superadmin else []

    if request.method == "POST":
        try:
            branch_id = int(request.form.get("branch_id", current_user.branch_id))
            role_id   = int(request.form.get("role_id"))
            username  = request.form.get("username", "").strip().lower()
            email     = request.form.get("email", "").strip().lower()
            password  = request.form.get("password", "")

            if User.query.filter_by(username=username).first():
                flash("Username already taken.", "danger")
                return render_template("settings/user_form.html", user=None, roles=roles, branches=branches)

            if User.query.filter_by(email=email).first():
                flash("Email already registered.", "danger")
                return render_template("settings/user_form.html", user=None, roles=roles, branches=branches)

            u = User(
                branch_id=branch_id,
                role_id=role_id,
                username=username,
                email=email,
                full_name=request.form.get("full_name", "").strip(),
                phone=request.form.get("phone", "").strip() or None,
                must_change_pwd=True,
            )
            u.set_password(password)
            db.session.add(u)
            db.session.commit()
            log_action("CREATE", "settings", record_id=u.id, record_type="User",
                       new_value={"username": u.username, "email": u.email})
            flash(f"User {u.username} created. They must change password on first login.", "success")
            return redirect(url_for("settings.users"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error: {e}", "danger")

    return render_template("settings/user_form.html", user=None, roles=roles, branches=branches)


@settings_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@branch_admin_required
def user_edit(user_id):
    user = User.query.get_or_404(user_id)
    roles = _get_available_roles()
    branches = Branch.query.filter_by(is_active=True, is_deleted=False).all() if current_user.is_superadmin else []

    if request.method == "POST":
        try:
            user.full_name = request.form.get("full_name", "").strip()
            user.phone     = request.form.get("phone", "").strip() or None
            user.role_id   = int(request.form.get("role_id"))
            user.is_active = request.form.get("is_active") == "on"
            if current_user.is_superadmin:
                user.branch_id = int(request.form.get("branch_id", user.branch_id))
            db.session.commit()
            log_action("UPDATE", "settings", record_id=user.id, record_type="User")
            flash("User updated.", "success")
            return redirect(url_for("settings.users"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error: {e}", "danger")

    return render_template("settings/user_form.html", user=user, roles=roles, branches=branches)


@settings_bp.route("/users/<int:user_id>/reset-password", methods=["POST"])
@login_required
@branch_admin_required
def user_reset_password(user_id):
    user = User.query.get_or_404(user_id)
    new_pwd = request.form.get("new_password", "")
    if len(new_pwd) < 8:
        flash("Password must be at least 8 characters.", "danger")
        return redirect(url_for("settings.user_edit", user_id=user_id))
    user.set_password(new_pwd)
    user.must_change_pwd = True
    db.session.commit()
    log_action("PASSWORD_RESET_BY_ADMIN", "settings", record_id=user.id, record_type="User")
    flash("Password reset. User must change on next login.", "success")
    return redirect(url_for("settings.users"))


# ── Roles & Permissions ────────────────────────────────────────────────────────

@settings_bp.route("/roles")
@login_required
@branch_admin_required
def roles():
    query = Role.query.filter_by(is_deleted=False)
    if not current_user.is_superadmin:
        query = query.filter(
            db.or_(Role.branch_id == current_user.branch_id, Role.branch_id == None)
        )
    roles = query.order_by(Role.name).all()
    return render_template("settings/roles.html", roles=roles)


@settings_bp.route("/roles/new", methods=["GET", "POST"])
@login_required
@branch_admin_required
def role_new():
    if request.method == "POST":
        try:
            branch_id = current_user.branch_id if not current_user.is_superadmin else (
                int(request.form.get("branch_id")) if request.form.get("branch_id") else None
            )
            r = Role(
                branch_id=branch_id,
                name=request.form.get("name", "").strip(),
                name_ta=request.form.get("name_ta", "").strip() or None,
                description=request.form.get("description", "").strip() or None,
            )
            db.session.add(r)
            db.session.commit()
            log_action("CREATE", "settings", record_id=r.id, record_type="Role", new_value={"name": r.name})
            flash(f"Role '{r.name}' created. Now assign permissions.", "success")
            return redirect(url_for("settings.role_permissions", role_id=r.id))
        except Exception as e:
            db.session.rollback()
            flash(f"Error: {e}", "danger")
    branches = Branch.query.filter_by(is_active=True, is_deleted=False).all() if current_user.is_superadmin else []
    return render_template("settings/role_form.html", role=None, branches=branches)


@settings_bp.route("/roles/<int:role_id>/permissions", methods=["GET", "POST"])
@login_required
@branch_admin_required
def role_permissions(role_id):
    role = Role.query.get_or_404(role_id)
    _seed_permissions()   # ensure all permissions exist

    all_perms = Permission.query.order_by(Permission.module, Permission.action).all()
    granted_ids = {rp.permission_id for rp in role.permissions.all()}

    if request.method == "POST":
        selected_ids = set(int(x) for x in request.form.getlist("permissions"))

        # Remove unselected
        RolePermission.query.filter_by(role_id=role.id).filter(
            ~RolePermission.permission_id.in_(selected_ids)
        ).delete(synchronize_session=False)

        # Add new
        for pid in selected_ids - granted_ids:
            rp = RolePermission(role_id=role.id, permission_id=pid, granted_by=current_user.id)
            db.session.add(rp)

        db.session.commit()
        log_action("UPDATE", "settings", record_id=role.id, record_type="Role",
                   notes=f"Permissions updated: {len(selected_ids)} granted")
        flash("Permissions saved.", "success")
        return redirect(url_for("settings.roles"))

    return render_template("settings/role_permissions.html",
                           role=role,
                           all_perms=all_perms,
                           granted_ids=granted_ids,
                           modules=ALL_PERMISSIONS)


# ── System Settings ────────────────────────────────────────────────────────────

@settings_bp.route("/system", methods=["GET", "POST"])
@login_required
@branch_admin_required
def system_settings():
    branch_id = current_user.branch_id if not current_user.is_superadmin else None

    if request.method == "POST":
        for key, value in request.form.items():
            if key.startswith("setting_"):
                setting_key = key[8:]  # strip "setting_" prefix
                setting = SystemSetting.query.filter_by(key=setting_key, branch_id=branch_id).first()
                if setting:
                    setting.value = value
                    setting.updated_at = datetime.now(timezone.utc)
                else:
                    s = SystemSetting(key=setting_key, value=value, branch_id=branch_id)
                    db.session.add(s)
        db.session.commit()
        flash("Settings saved.", "success")
        return redirect(url_for("settings.system_settings"))

    settings = SystemSetting.query.filter(
        db.or_(SystemSetting.branch_id == branch_id, SystemSetting.branch_id == None)
    ).order_by(SystemSetting.setting_group, SystemSetting.key).all()

    settings_by_group = {}
    for s in settings:
        g = s.setting_group or "General"
        settings_by_group.setdefault(g, []).append(s)

    return render_template("settings/system_settings.html", settings_by_group=settings_by_group)


# ── Email Templates ────────────────────────────────────────────────────────────

@settings_bp.route("/email-templates")
@login_required
@branch_admin_required
def email_templates():
    branch_id = current_user.branch_id if not current_user.is_superadmin else None
    templates = EmailTemplate.query.filter(
        db.or_(EmailTemplate.branch_id == branch_id, EmailTemplate.branch_id == None),
        EmailTemplate.is_deleted == False,
    ).order_by(EmailTemplate.template_key).all()
    return render_template("settings/email_templates.html", templates=templates)


@settings_bp.route("/email-templates/<int:template_id>/edit", methods=["GET", "POST"])
@login_required
@branch_admin_required
def email_template_edit(template_id):
    template = EmailTemplate.query.get_or_404(template_id)
    if request.method == "POST":
        template.subject   = request.form.get("subject", "").strip()
        template.body_html = request.form.get("body_html", "")
        template.body_text = request.form.get("body_text", "")
        template.is_active = request.form.get("is_active") == "on"
        template.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        flash("Email template saved.", "success")
        return redirect(url_for("settings.email_templates"))
    return render_template("settings/email_template_form.html", template=template)


# ── Audit Log Viewer ──────────────────────────────────────────────────────────

def require_permission_view(module):
    """Local shorthand for view permission on a module."""
    from app.utils.decorators import require_permission
    return require_permission(module, "view")


@settings_bp.route("/audit-log")
@login_required
@require_permission_view("audit")
def audit_log():
    page     = request.args.get("page", 1, type=int)
    module   = request.args.get("module", "")
    action   = request.args.get("action", "")
    user_id  = request.args.get("user_id", type=int)
    date_from = request.args.get("date_from", "")
    date_to  = request.args.get("date_to", "")

    query = AuditLog.query
    if not current_user.is_superadmin:
        query = query.filter_by(branch_id=current_user.branch_id)
    if module:
        query = query.filter_by(module=module)
    if action:
        query = query.filter_by(action=action)
    if user_id:
        query = query.filter_by(user_id=user_id)
    if date_from:
        from datetime import datetime as dt
        try:
            query = query.filter(AuditLog.timestamp >= dt.strptime(date_from, "%Y-%m-%d"))
        except ValueError:
            pass
    if date_to:
        try:
            query = query.filter(AuditLog.timestamp <= dt.strptime(date_to + " 23:59:59", "%Y-%m-%d %H:%M:%S"))
        except ValueError:
            pass

    logs = query.order_by(AuditLog.timestamp.desc()).paginate(page=page, per_page=50)
    users = User.query.filter_by(is_deleted=False).all()
    modules = [row[0] for row in db.session.query(AuditLog.module).distinct().all()]

    return render_template("settings/audit_log.html",
                           logs=logs, users=users, modules=modules,
                           filters={"module": module, "action": action,
                                    "user_id": user_id, "date_from": date_from, "date_to": date_to})


# ── Departments & Designations ─────────────────────────────────────────────────

@settings_bp.route("/departments")
@login_required
@branch_admin_required
def departments():
    branch_id = current_user.branch_id if not current_user.is_superadmin else None
    query = Department.query.filter_by(is_deleted=False)
    if branch_id:
        query = query.filter_by(branch_id=branch_id)
    depts = query.order_by(Department.name).all()
    return render_template("settings/departments.html", departments=depts)


@settings_bp.route("/departments/save", methods=["POST"])
@login_required
@branch_admin_required
def department_save():
    dept_id = request.form.get("dept_id")
    branch_id = current_user.branch_id

    if dept_id:
        d = Department.query.get_or_404(int(dept_id))
    else:
        d = Department(branch_id=branch_id)
        db.session.add(d)

    d.code    = request.form.get("code", "").upper().strip()
    d.name    = request.form.get("name", "").strip()
    d.name_ta = request.form.get("name_ta", "").strip() or None
    d.dept_type = request.form.get("dept_type", "clinical")
    db.session.commit()
    flash("Department saved.", "success")
    return redirect(url_for("settings.departments"))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_available_roles():
    if current_user.is_superadmin:
        return Role.query.filter_by(is_deleted=False, is_active=True).order_by(Role.name).all()
    return Role.query.filter(
        db.or_(Role.branch_id == current_user.branch_id, Role.branch_id == None),
        Role.is_deleted == False,
        Role.is_active == True,
    ).order_by(Role.name).all()


def _seed_permissions():
    """Ensure all module.action permission rows exist in DB. Idempotent."""
    for module, actions in ALL_PERMISSIONS.items():
        for action in actions:
            exists = Permission.query.filter_by(module=module, action=action).first()
            if not exists:
                p = Permission(
                    module=module,
                    action=action,
                    label=f"{module.title()} — {action.title()}",
                )
                db.session.add(p)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()


    return require_permission(module, "view")
