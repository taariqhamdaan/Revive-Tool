# MediCore - app/models/base.py
# Abstract base model. Every table inherits from this.
# Provides: id, branch_id, created_at, updated_at, created_by, is_deleted (soft delete)

from datetime import datetime, timezone
from app.extensions import db


class BaseModel(db.Model):
    """
    Abstract base — all MediCore tables inherit this.
    Soft delete: records are never hard-deleted (medical compliance).
    """
    __abstract__ = True

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # Audit timestamps (UTC always)
    created_at  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                            onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Who created / last modified this record
    created_by  = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    modified_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    # Soft delete — NEVER hard delete medical records
    is_deleted     = db.Column(db.Boolean, default=False, nullable=False)
    deleted_at     = db.Column(db.DateTime, nullable=True)
    deleted_by     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    def soft_delete(self, user_id: int):
        """Mark record as deleted. Does not remove from database."""
        self.is_deleted = True
        self.deleted_at = datetime.now(timezone.utc)
        self.deleted_by = user_id

    def to_dict(self):
        """Convert model to dictionary for API/JSON responses."""
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
