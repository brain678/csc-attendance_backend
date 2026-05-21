from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime, timezone
from app.core.mongodb import get_database
from app.services.qr_service import QRTokenService
from app.services.user_service import UserService
from app.services.audit_service import AuditLogService
from app.models.requests import QRTokenValidate, QRTokenResponse, QRCodeGenerateResponse, QRGenerateRequest
from app.api.dependencies import require_admin
from app.utils.qr_generator import generate_qr_code
from fastapi.responses import StreamingResponse
from io import BytesIO
import base64

router = APIRouter(prefix="/api/qr", tags=["QR Tokens"])


def ensure_timestamp(dt: datetime) -> str:
    """Ensure datetime is timezone-aware before converting to ISO format"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


@router.get("/all")
async def get_all_qr_tokens(admin = Depends(require_admin)):
    """Get all QR tokens with user information (Admin only)"""
    db = get_database()
    qr_service = QRTokenService(db)
    user_service = UserService(db)
    
    tokens = await qr_service.get_all_tokens()
    
    # Enrich tokens with user information
    enriched_tokens = []
    for token in tokens:
        user = await user_service.get_user(token.user_id)
        enriched_tokens.append({
            "id": token.id,
            "user_id": token.user_id,
            "is_active": token.is_active,
            "issued_at": ensure_timestamp(token.issued_at),
            "user": {
                "full_name": user.full_name if user else "Unknown",
                "email": user.email if user else None,
                "matric_number": user.matric_number if user else None
            }
        })
    
    return {"tokens": enriched_tokens}


@router.post("/generate/{user_id}", response_model=QRCodeGenerateResponse)
async def generate_qr_token(user_id: str, admin = Depends(require_admin)):
    """Generate a new QR token for a user and return image (Admin only)"""
    db = get_database()
    user_service = UserService(db)
    qr_service = QRTokenService(db)
    audit_service = AuditLogService(db)
    
    # Verify user exists
    user = await user_service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Create QR token
    token = await qr_service.create_qr_token(user_id)
    
    # Generate QR code image
    qr_image = generate_qr_code(token.id)
    qr_base64 = base64.b64encode(qr_image).decode('utf-8')
    
    # Log action
    await audit_service.log_action(
        "qr_token_generated",
        admin.id,
        {"user_id": user_id, "token_id": token.id}
    )
    
    return QRCodeGenerateResponse(
        id=token.id,
        user_id=token.user_id,
        is_active=token.is_active,
        issued_at=ensure_timestamp(token.issued_at),
        qr_code_data=qr_base64
    )



@router.post("/generate", response_model=QRCodeGenerateResponse)
async def generate_qr_token_payload(payload: QRGenerateRequest, admin = Depends(require_admin)):
    """Generate a QR token with optional course/lecture context and TTL (Admin only)"""
    db = get_database()
    user_service = UserService(db)
    qr_service = QRTokenService(db)
    audit_service = AuditLogService(db)

    # If user_id provided, verify user exists
    if payload.user_id:
        user = await user_service.get_user(payload.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

    token = await qr_service.create_qr_token(
        user_id=payload.user_id,
        course_id=payload.course_id,
        lecture_id=payload.lecture_id,
        ttl_minutes=payload.ttl_minutes,
        issued_by=payload.issued_by,
        metadata=payload.metadata
    )

    # Generate QR code image
    qr_image = generate_qr_code(token.id)
    qr_base64 = base64.b64encode(qr_image).decode('utf-8')

    # Log action
    await audit_service.log_action(
        "qr_token_generated",
        admin.id,
        {"user_id": token.user_id, "token_id": token.id, "course_id": token.course_id, "lecture_id": token.lecture_id}
    )

    return QRCodeGenerateResponse(
        id=token.id,
        user_id=token.user_id,
        is_active=token.is_active,
        issued_at=ensure_timestamp(token.issued_at),
        qr_code_data=qr_base64
    )


@router.get("/token/{token_id}", response_model=QRTokenResponse)
async def get_qr_token(token_id: str, admin = Depends(require_admin)):
    """Get QR token details (Admin only)"""
    db = get_database()
    qr_service = QRTokenService(db)
    
    token = await qr_service.get_qr_token(token_id)
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    
    return QRTokenResponse(
        id=token.id,
        user_id=token.user_id,
        is_active=token.is_active,
        issued_at=ensure_timestamp(token.issued_at)
    )


@router.get("/user/{user_id}", response_model=list)
async def get_user_tokens(user_id: str, admin = Depends(require_admin)):
    """Get all tokens for a user (Admin only)"""
    db = get_database()
    user_service = UserService(db)
    qr_service = QRTokenService(db)
    
    # Verify user exists
    user = await user_service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    tokens = await qr_service.get_user_tokens(user_id)
    return [
        QRTokenResponse(
            id=t.id,
            user_id=t.user_id,
            is_active=t.is_active,
            issued_at=ensure_timestamp(t.issued_at)
        ) for t in tokens
    ]


@router.post("/validate", response_model=dict)
async def validate_token(data: QRTokenValidate):
    """Validate a QR token (Public endpoint for kiosk)"""
    db = get_database()
    qr_service = QRTokenService(db)
    user_service = UserService(db)
    # Validate token (this will also revoke expired tokens)
    valid = await qr_service.validate_token(data.token)
    if not valid:
        raise HTTPException(status_code=400, detail="Invalid, revoked, or expired token")

    token = await qr_service.get_qr_token(data.token)
    if not token:
        raise HTTPException(status_code=400, detail="Invalid token")

    user = await user_service.get_user(token.user_id)
    if not user:
        raise HTTPException(status_code=400, detail="User not found")

    if user.status != "active":
        raise HTTPException(status_code=400, detail="User is not active")
    
    # NOTE: Don't check for existing sessions here
    # The frontend handles toggle login/logout logic
    # If user has existing session, frontend will end it
    
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
        }
    }


@router.post("/revoke/{token_id}")
async def revoke_token(token_id: str, admin = Depends(require_admin)):
    """Revoke a QR token (Admin only)"""
    db = get_database()
    qr_service = QRTokenService(db)
    audit_service = AuditLogService(db)
    
    token = await qr_service.revoke_token(token_id)
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    
    # Log action
    await audit_service.log_action(
        "qr_token_revoked",
        admin.id,
        {"token_id": token_id, "user_id": token.user_id}
    )
    
    return {"message": f"Token {token_id} revoked"}


@router.post("/revoke-all/{user_id}")
async def revoke_all_user_tokens(user_id: str, admin = Depends(require_admin)):
    """Revoke all tokens for a user (Admin only)"""
    db = get_database()
    user_service = UserService(db)
    qr_service = QRTokenService(db)
    audit_service = AuditLogService(db)
    
    # Verify user exists
    user = await user_service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    count = await qr_service.revoke_all_user_tokens(user_id)
    
    # Log action
    await audit_service.log_action(
        "qr_tokens_revoked_all",
        admin.id,
        {"user_id": user_id, "count": count}
    )
    
    return {"message": f"Revoked {count} token(s) for user {user_id}"}


@router.get("/image/{token_id}")
async def get_qr_image(token_id: str, admin = Depends(require_admin)):
    """Get QR code image (Admin only)"""
    db = get_database()
    qr_service = QRTokenService(db)
    
    token = await qr_service.get_qr_token(token_id)
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    
    # Generate QR code image
    qr_image = generate_qr_code(token_id)
    
    return StreamingResponse(
        BytesIO(qr_image),
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename=qr_{token_id}.png"}
    )
