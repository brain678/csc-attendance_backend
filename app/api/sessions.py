from fastapi import APIRouter, Depends, HTTPException, status, Query
from datetime import datetime, timedelta, timezone
from app.core.mongodb import get_database
from app.services.session_service import SessionService
from app.services.qr_service import QRTokenService
from app.services.user_service import UserService
from app.services.audit_service import AuditLogService
from app.models.requests import SessionApprove, SessionDeny, SessionResponse, OccupancyResponse
from app.api.dependencies import require_operator, require_admin, get_kiosk_or_staff

router = APIRouter(prefix="/api/sessions", tags=["Sessions"])


def ensure_timezone_aware(dt: datetime) -> str:
    """Ensure datetime is timezone-aware before converting to ISO format"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        # If naive, assume it's UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


@router.post("/approve", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def approve_entry(data: SessionApprove, operator = Depends(require_operator)):
    """Approve user entry (Operator/Admin only)"""
    db = get_database()
    session_service = SessionService(db)
    qr_service = QRTokenService(db)
    user_service = UserService(db)
    audit_service = AuditLogService(db)
    
    # Validate token
    token = await qr_service.get_qr_token(data.token)
    if not token or not token.is_active:
        raise HTTPException(status_code=400, detail="Invalid or revoked token")
    
    if token.user_id != data.user_id:
        raise HTTPException(status_code=400, detail="Token does not match user")
    
    # Verify user
    user = await user_service.get_user(data.user_id)
    if not user:
        raise HTTPException(status_code=400, detail="User not found")
    
    if user.status != "active":
        raise HTTPException(status_code=400, detail="User is not active")
    
    # Check for existing active session
    existing = await session_service.get_active_session(data.user_id)
    if existing:
        raise HTTPException(status_code=400, detail="User already has an active session")
    
    # Create session (atomic transaction)
    session = await session_service.create_session(
        data.user_id,
        data.kiosk_id,
        operator.id
    )
    
    # Mark token as used (create new approach - revoke after use)
    # In v1, we don't revoke tokens, allowing multiple uses
    
    # Log action
    await audit_service.log_action(
        "entry_approved",
        operator.id,
        {
            "user_id": data.user_id,
            "session_id": session.id,
            "kiosk_id": data.kiosk_id,
            "notes": data.notes
        }
    )
    
    return SessionResponse(
        id=session.id,
        user_id=session.user_id,
        kiosk_id=session.kiosk_id,
        entry_time=ensure_timezone_aware(session.entry_time),
        exit_time=None,
        approved_by=session.approved_by
    )


@router.post("/deny")
async def deny_entry(data: SessionDeny, operator = Depends(require_operator)):
    """Deny user entry (Operator/Admin only)"""
    db = get_database()
    qr_service = QRTokenService(db)
    audit_service = AuditLogService(db)
    
    # Validate token
    token = await qr_service.get_qr_token(data.token)
    if not token:
        raise HTTPException(status_code=400, detail="Invalid token")
    
    if token.user_id != data.user_id:
        raise HTTPException(status_code=400, detail="Token does not match user")
    
    # Log action
    await audit_service.log_action(
        "entry_denied",
        operator.id,
        {
            "user_id": data.user_id,
            "reason": data.reason
        }
    )
    
    return {"message": "Entry denied"}


@router.get("/active", response_model=list)
async def get_active_sessions(skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000),
                             auth = Depends(get_kiosk_or_staff)):
    """Get all active sessions (Operator/Admin/Kiosk allowed)"""
    db = get_database()
    session_service = SessionService(db)
    
    # Verify authorization: staff must be operator or admin
    if auth["type"] == "staff":
        from app.models.schemas import StaffRole
        if auth["role"] not in [StaffRole.operator, StaffRole.admin]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operator access required"
            )
    
    sessions = await session_service.get_active_sessions(skip, limit)
    return [
        {
            "id": s.id,
            "user_id": s.user_id,
            "kiosk_id": s.kiosk_id,
            "entry_time": ensure_timezone_aware(s.entry_time),
            "exit_time": None,
            "approved_by": s.approved_by
        } for s in sessions
    ]


@router.get("/active/with-details", response_model=list)
async def get_active_sessions_with_details(skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000),
                                          operator = Depends(require_operator)):
    """Get all active sessions with user details (Operator/Admin only)"""
    db = get_database()
    
    # Aggregation pipeline to join sessions with user details
    pipeline = [
        {"$match": {"exit_time": None}},
        {
            "$lookup": {
                "from": "users",
                "localField": "user_id",
                "foreignField": "_id",
                "as": "user_details"
            }
        },
        {"$unwind": "$user_details"},
        {
            "$project": {
                "session_id": "$_id",
                "user_id": "$user_id",
                "full_name": "$user_details.full_name",
                "matric_number": "$user_details.matric_number",
                "email": "$user_details.email",
                "phone_number": "$user_details.phone_number",
                "entry_time": 1,
                "kiosk_id": 1,
                "approved_by": 1
            }
        },
        {"$sort": {"entry_time": -1}},
        {"$skip": skip},
        {"$limit": limit}
    ]
    
    cursor = db.sessions.aggregate(pipeline)
    sessions = []
    async for session in cursor:
        sessions.append({
            "id": session["session_id"],
            "user_id": session["user_id"],
            "full_name": session.get("full_name", "N/A"),
            "matric_number": session.get("matric_number", "N/A"),
            "email": session.get("email", "N/A"),
            "phone_number": session.get("phone_number", "N/A"),
            "entry_time": ensure_timezone_aware(session["entry_time"]),
            "kiosk_id": session["kiosk_id"],
            "approved_by": session["approved_by"]
        })
    
    return sessions


@router.get("/occupancy", response_model=OccupancyResponse)
async def get_occupancy(operator = Depends(require_operator)):
    """Get current occupancy count (Operator/Admin only)"""
    db = get_database()
    session_service = SessionService(db)
    
    count = await session_service.get_occupancy_count()
    return OccupancyResponse(
        current=count,
        message=f"Current occupancy: {count} user(s)"
    )


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, operator = Depends(require_operator)):
    """Get session details (Operator/Admin only)"""
    db = get_database()
    session_service = SessionService(db)
    
    session = await session_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return SessionResponse(
        id=session.id,
        user_id=session.user_id,
        kiosk_id=session.kiosk_id,
        entry_time=ensure_timezone_aware(session.entry_time),
        exit_time=ensure_timezone_aware(session.exit_time) if session.exit_time else None,
        approved_by=session.approved_by
    )


@router.post("/{session_id}/end")
async def end_session(session_id: str, operator = Depends(require_operator)):
    """End a session (mark user as exited)"""
    db = get_database()
    session_service = SessionService(db)
    audit_service = AuditLogService(db)
    
    session = await session_service.end_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Log action
    await audit_service.log_action(
        "session_ended",
        operator.id,
        {
            "session_id": session_id,
            "user_id": session.user_id
        }
    )
    
    return {
        "message": "Session ended",
        "session_id": session_id,
        "exit_time": session.exit_time.isoformat()
    }


@router.get("/user/{user_id}", response_model=list)
async def get_user_sessions(user_id: str, skip: int = Query(0, ge=0), 
                           limit: int = Query(100, ge=1, le=1000),
                           admin = Depends(require_admin)):
    """Get all sessions for a user (Admin only)"""
    db = get_database()
    session_service = SessionService(db)
    
    sessions = await session_service.get_user_sessions(user_id, skip, limit)
    return [
        SessionResponse(
            id=s.id,
            user_id=s.user_id,
            kiosk_id=s.kiosk_id,
            entry_time=ensure_timezone_aware(s.entry_time),
            exit_time=ensure_timezone_aware(s.exit_time) if s.exit_time else None,
            approved_by=s.approved_by
        ) for s in sessions
    ]


@router.post("/admin/clear-old-sessions")
async def clear_old_sessions(minutes: int = Query(60, ge=1, description="Clear sessions older than N minutes"),
                            admin = Depends(require_admin)):
    """Clear old test sessions (Admin only) - defaults to sessions older than 60 minutes"""
    db = get_database()
    collection = db.sessions
    
    # Calculate cutoff time
    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    
    # Delete old active sessions that haven't been updated
    result = await collection.delete_many({
        "exit_time": None,
        "entry_time": {"$lt": cutoff_time}
    })
    
    return {
        "message": f"Cleared {result.deleted_count} sessions older than {minutes} minutes",
        "deleted_count": result.deleted_count,
        "cutoff_time": cutoff_time.isoformat()
    }

@router.get("/report/generate")
async def generate_session_report(
    start_date: str = Query(None, description="Start date in ISO format (YYYY-MM-DD)"),
    end_date: str = Query(None, description="End date in ISO format (YYYY-MM-DD)"),
    admin = Depends(require_admin)
):
    """Generate session report for completed sessions (Admin only)"""
    db = get_database()
    session_service = SessionService(db)
    
    # Parse dates if provided
    start_datetime = None
    end_datetime = None
    
    try:
        if start_date:
            start_datetime = datetime.fromisoformat(start_date)
        if end_date:
            # Add 1 day to include all records for the end date
            end_datetime = datetime.fromisoformat(end_date)
            end_datetime = end_datetime.replace(hour=23, minute=59, second=59)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {str(e)}")
    
    # Get completed sessions with user details
    sessions = await session_service.get_completed_sessions(
        start_date=start_datetime,
        end_date=end_datetime,
        skip=0,
        limit=10000
    )
    
    # Format response data
    report_data = []
    for session in sessions:
        duration = None
        if session.get("entry_time") and session.get("exit_time"):
            delta = session["exit_time"] - session["entry_time"]
            duration = f"{delta.seconds // 3600:02d}:{(delta.seconds // 60) % 60:02d}:{delta.seconds % 60:02d}"
        
        report_data.append({
            "session_id": str(session.get("_id", "")),
            "user_name": session.get("full_name", "N/A"),
            "matric_number": session.get("matric_number", "N/A"),
            "time_in": ensure_timezone_aware(session.get("entry_time")) if session.get("entry_time") else None,
            "time_out": ensure_timezone_aware(session.get("exit_time")) if session.get("exit_time") else None,
            "duration": duration,
            "approved_by": session.get("approved_by", "N/A"),
            "kiosk_id": session.get("kiosk_id", "N/A")
        })
    
    return {
        "status": "success",
        "count": len(report_data),
        "data": report_data
    }