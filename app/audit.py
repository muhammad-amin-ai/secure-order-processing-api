"""
Audit logging helper.

Every sensitive/state-changing action (order creation, inventory
adjustment, product changes, order status changes) should call
record_audit() within the same DB transaction so the audit trail
stays consistent with the data it describes.
"""
import json
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app import models


def _json_default(value):
    """Fallback encoder for types json.dumps can't handle natively
    (Decimal amounts, enums, etc.) so audit logging never fails a request."""
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "value"):  # enums
        return value.value
    return str(value)


def record_audit(
    db: Session,
    *,
    user_id: Optional[str],
    action: str,
    entity_type: str,
    entity_id: Optional[str] = None,
    details: Optional[dict] = None,
) -> models.AuditLog:
    entry = models.AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=json.dumps(details, default=_json_default) if details is not None else None,
    )
    db.add(entry)
    return entry
