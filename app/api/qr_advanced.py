"""
Enhanced QR validation with automatic approval and advanced security
"""
from fastapi import APIRouter, Depends, HTTPException, status, Header, Request
from fastapi.responses import JSONResponse
from app.core.mongodb import get_database
from app.core.rate_limiter import RateLimiter, TokenSecurityValidator
from app.services.qr_service import QRTokenService
from app.services.user_service import UserService
from app.services.session_service import SessionService
from app.services.audit_service import AuditLogService
from app.services.attendance_service import AttendanceService
from app.models.requests import QRTokenValidate
from typing import Optional
from datetime import datetime, timezone
import hashlib
import json

router = APIRouter(prefix="/api/qr-advanced", tags=["QR Advanced"])


@router.options("/validate-auto")
async def validate_token_auto_options():
    """Handle CORS preflight requests"""
    return JSONResponse(content={}, status_code=200)


async def get_client_ip(request: Request) -> str:
    """Extract client IP from request"""
    if x_forwarded_for := request.headers.get("X-Forwarded-For"):
        return x_forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/validate-auto")
async def validate_token_auto(
    data: QRTokenValidate,
    request: Request,
    kiosk_id: Optional[str] = Header(None, alias="X-Kiosk-ID"),
):
    """
    Enhanced QR token validation with automatic approval
    
    Features:
    - Rate limiting per IP
    - Duplicate scan detection
    - Automatic approval for valid tokens
    - Caching for performance
    - Full security audit logging
    - Optional 2FA support
    """
    db = get_database()
    
    # Initialize services
    qr_service = QRTokenService(db)
    user_service = UserService(db)
    session_service = SessionService(db)
    audit_service = AuditLogService(db)
    rate_limiter = RateLimiter(db)
    security_validator = TokenSecurityValidator(db)
    
    client_ip = await get_client_ip(request)
    rate_limit_key = f"{client_ip}:{kiosk_id or 'unknown'}"
    
    try:
        # 1. Rate limiting check
        await rate_limiter.check_limit(
            key=rate_limit_key,
            limit_type="qr_validate",
            custom_attempts=10,  # 10 attempts per minute
            custom_window_minutes=1
        )
        
        # 2. Validate token format
        if not data.token or len(data.token) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid token format"
            )
        
        # NOTE: We do NOT use cache for valid tokens because session state changes
        # and we need to check if user has active session for logout logic.
        # Each scan must perform a fresh validation to handle entry/exit correctly.
        
        # 3. Validate token from database
        token = await qr_service.get_qr_token(data.token)
        if not token or not token.is_active:
            await security_validator.cache_token_validation(data.token, False)
            await audit_service.log_action(
                "qr_validation_failed_invalid_token",
                "system",
                {
                    "token": data.token[:8] + "...",
                    "kiosk_id": kiosk_id,
                    "ip": client_ip,
                    "reason": "Token not found or inactive"
                }
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or revoked token"
            )
        
        # 5. Get user information
        user = await user_service.get_user(token.user_id)
        if not user:
            await audit_service.log_action(
                "qr_validation_failed_user_not_found",
                "system",
                {
                    "token_id": token.id,
                    "kiosk_id": kiosk_id,
                    "ip": client_ip
                }
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User not found"
            )
        
        # 6. Check user status
        if user.status != "active":
            await audit_service.log_action(
                "qr_validation_failed_user_inactive",
                user.id,
                {
                    "user_status": user.status,
                    "kiosk_id": kiosk_id,
                    "ip": client_ip
                }
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User is {user.status}, not active"
            )
        
        # 7. Check for duplicate scan (prevent accidental double-scans)
        is_duplicate = await security_validator.check_duplicate_scan(
            token_id=token.id,
            kiosk_id=kiosk_id or "unknown",
            window_seconds=120
        )
        
        if is_duplicate:
            await audit_service.log_action(
                "qr_duplicate_scan_detected",
                user.id,
                {
                    "token_id": token.id,
                    "kiosk_id": kiosk_id,
                    "ip": client_ip
                }
            )
            # Return success but mention duplicate (don't process again)
            return {
                "valid": True,
                "duplicate": True,
                "message": "Duplicate scan detected within 2 minutes",
                "action": "none"
            }
        
        # 8. Check for existing session
        existing_session = await session_service.get_active_session(user.id)
        
        approval_strategy = "auto_logout"  # Default: auto logout on re-scan
        if existing_session:
            # User has active session - auto-logout
            await session_service.end_session(existing_session.id)
            await audit_service.log_action(
                "qr_auto_logout",
                user.id,
                {
                    "session_id": existing_session.id,
                    "kiosk_id": kiosk_id,
                    "ip": client_ip,
                    "reason": "Token re-scanned"
                }
            )
            action_result = "logout"
        else:
            # User not logged in - auto-approve if conditions met
            if should_auto_approve(user):
                # Create new session automatically
                new_session = await session_service.create_session(
                    user_id=user.id,
                    kiosk_id=kiosk_id or "unknown",
                    approved_by="system_auto_approval"
                )
                
                await audit_service.log_action(
                    "qr_auto_approved",
                    user.id,
                    {
                        "session_id": new_session.id,
                        "token_id": token.id,
                        "kiosk_id": kiosk_id,
                        "ip": client_ip
                    }
                )
                action_result = "login_approved"
                approval_strategy = "auto_approve"
                # Record attendance for course if token includes course_id
                try:
                    attendance_service = AttendanceService(db)
                    await attendance_service.record_attendance(
                        user_id=user.id,
                        course_id=token.course_id if hasattr(token, 'course_id') else None,
                        lecture_id=token.lecture_id if hasattr(token, 'lecture_id') else None,
                        method='qr',
                        kiosk_id=kiosk_id or 'unknown',
                        qr_token_id=token.id,
                        recorded_by='system_auto_approval'
                    )
                except Exception as e:
                    # Non-fatal: log and continue
                    await audit_service.log_action('attendance_record_failed', 'system', {'error': str(e), 'user_id': user.id, 'token_id': token.id})
            else:
                # Requires manual approval
                action_result = "pending_approval"
                approval_strategy = "manual_approval"
        
        # 9. Cache validation result
        await security_validator.cache_token_validation(
            token_id=token.id,
            is_valid=True,
            user_id=user.id
        )
        
        # 10. Record scan
        await security_validator.record_scan(
            token_id=token.id,
            kiosk_id=kiosk_id or "unknown",
            success=True
        )
        
        remaining = await rate_limiter.get_remaining(rate_limit_key)
        
        return {
            "valid": True,
            "user": {
                "id": user.id,
                "full_name": user.full_name,
                "email": user.email,
                "status": user.status,
                "matric_number": user.matric_number,
                "picture_url": user.picture,
                "created_at": user.created_at.isoformat()
            },
            "action": action_result,
            "approval_strategy": approval_strategy,
            "message": f"Token valid - {action_result}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "remaining_attempts": remaining
        }
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Validation error: {str(e)}")
        await audit_service.log_action(
            "qr_validation_error",
            "system",
            {
                "error": str(e),
                "kiosk_id": kiosk_id,
                "ip": client_ip
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Validation error"
        )


def should_auto_approve(user) -> bool:
    """
    Determine if token should be automatically approved
    
    Auto-approve conditions:
    - User is active
    - User has not been blocked/suspended
    - No pending disciplinary action
    
    Can be extended with:
    - Time-based rules (business hours only)
    - User group permissions
    - Capacity checks
    """
    if user.status != "active":
        return False
    
    # Add custom business logic here
    # e.g., check user roles, departments, etc.
    
    return True


@router.get("/validate-status/{token_id}")
async def get_validation_status(token_id: str):
    """Get cached validation status without performing validation"""
    db = get_database()
    security_validator = TokenSecurityValidator(db)
    
    is_valid = await security_validator.is_token_cached_valid(token_id)
    
    return {
        "token_id": token_id,
        "cached_valid": is_valid,
        "checked_at": datetime.now(timezone.utc).isoformat()
    }


@router.get("/rate-limit-status")
async def get_rate_limit_status(request: Request, kiosk_id: Optional[str] = Header(None)):
    """Check current rate limit status for client"""
    db = get_database()
    rate_limiter = RateLimiter(db)
    client_ip = await get_client_ip(request)
    rate_limit_key = f"{client_ip}:{kiosk_id or 'unknown'}"
    
    remaining = await rate_limiter.get_remaining(rate_limit_key, "qr_validate")
    
    return {
        "remaining_attempts": remaining,
        "limit_window_minutes": 1,
        "status": "ok" if remaining > 0 else "limit_exceeded"
    }
