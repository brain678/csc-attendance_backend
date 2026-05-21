from fastapi import APIRouter, Depends, Query
from datetime import datetime, timezone
from app.core.mongodb import get_database
from app.services.audit_service import AuditLogService
from app.models.requests import AuditLogResponse
from app.api.dependencies import require_admin

router = APIRouter(prefix="/api/logs", tags=["Audit Logs"])


def ensure_log_timestamp(dt: datetime) -> str:
    """Ensure datetime is timezone-aware before converting to ISO format"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        # If naive, assume it's UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


@router.get("", response_model=list)
async def get_logs(skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000),
                  admin = Depends(require_admin)):
    """Get audit logs (Admin only)"""
    db = get_database()
    audit_service = AuditLogService(db)
    
    logs = await audit_service.get_logs(skip, limit)
    return [
        AuditLogResponse(
            id=str(log.id),
            action=log.action,
            actor_id=log.actor_id,
            timestamp=ensure_log_timestamp(log.timestamp),
            metadata=log.metadata
        ) for log in logs
    ]


@router.get("/actor/{actor_id}", response_model=list)
async def get_actor_logs(actor_id: str, skip: int = Query(0, ge=0), 
                        limit: int = Query(100, ge=1, le=1000),
                        admin = Depends(require_admin)):
    """Get logs for a specific actor (Admin only)"""
    db = get_database()
    audit_service = AuditLogService(db)
    
    logs = await audit_service.get_actor_logs(actor_id, skip, limit)
    return [
        AuditLogResponse(
            id=str(log.id),
            action=log.action,
            actor_id=log.actor_id,
            timestamp=ensure_log_timestamp(log.timestamp),
            metadata=log.metadata
        ) for log in logs
    ]


@router.get("/action/{action}", response_model=list)
async def get_action_logs(action: str, skip: int = Query(0, ge=0), 
                         limit: int = Query(100, ge=1, le=1000),
                         admin = Depends(require_admin)):
    """Get logs for a specific action (Admin only)"""
    db = get_database()
    audit_service = AuditLogService(db)
    
    logs = await audit_service.get_action_logs(action, skip, limit)
    return [
        AuditLogResponse(
            id=str(log.id),
            action=log.action,
            actor_id=log.actor_id,
            timestamp=ensure_log_timestamp(log.timestamp),
            metadata=log.metadata
        ) for log in logs
    ]


@router.get("/user/{user_id}", response_model=list)
async def get_user_activity(user_id: str, skip: int = Query(0, ge=0), 
                           limit: int = Query(100, ge=1, le=1000),
                           admin = Depends(require_admin)):
    """Get activity logs for a user (Admin only)"""
    db = get_database()
    audit_service = AuditLogService(db)
    
    logs = await audit_service.get_user_activity(user_id, skip, limit)
    return [
        AuditLogResponse(
            id=str(log.id),
            action=log.action,
            actor_id=log.actor_id,
            timestamp=ensure_log_timestamp(log.timestamp),
            metadata=log.metadata
        ) for log in logs
    ]
