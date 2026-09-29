import uuid
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.system import AuditLog


async def record_audit_log(
    db: AsyncSession,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    actor_id: Optional[uuid.UUID] = None,
    before_json: Optional[Dict[str, Any]] = None,
    after_json: Optional[Dict[str, Any]] = None,
    request_id: Optional[str] = None,
) -> AuditLog:
    """
    Records an immutable audit log entry in the database.
    Sensitive keys (passwords, tokens, secrets) are scrubbed before storage.
    """
    def sanitize(payload: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not payload:
            return payload
        sensitive_keys = {"password", "password_hash", "token", "refresh_token", "secret", "secret_reference"}
        return {
            k: ("[REDACTED]" if k.lower() in sensitive_keys else v)
            for k, v in payload.items()
        }

    audit_entry = AuditLog(
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id else None,
        before_json=sanitize(before_json),
        after_json=sanitize(after_json),
        request_id=request_id,
    )
    db.add(audit_entry)
    return audit_entry
