from fastapi import APIRouter, Depends, HTTPException, status, Query
from datetime import datetime, timezone
from app.core.mongodb import get_database
from app.services.user_service import UserService
from app.services.qr_service import QRTokenService
from app.services.audit_service import AuditLogService
from app.services.email_service import EmailService
from app.models.requests import UserCreate, UserUpdate, UserResponse
from app.api.dependencies import require_admin, require_operator
from app.utils.qr_generator import generate_qr_code
from io import BytesIO
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/users", tags=["Users"])


def ensure_user_timestamp(dt: datetime) -> str:
    """Ensure datetime is timezone-aware before converting to ISO format"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(user_data: UserCreate, admin = Depends(require_admin)):
    """Create a new user (Admin only) and send welcome email with QR code"""
    db = get_database()
    user_service = UserService(db)
    audit_service = AuditLogService(db)
    email_service = EmailService(db)
    
    user = await user_service.create_user(
        user_data.full_name, 
        user_data.email,
        user_data.phone_number,
        user_data.matric_number,
        user_data.picture
    )
    
    # Send welcome email with QR code
    try:
        if user.email:
            await email_service.send_welcome_email_with_qr(
                user_id=user.id,
                user_email=user.email,
                user_name=user.full_name,
                matric_number=user.matric_number
            )
            print(f"Welcome email sent to {user.email}")
        else:
            print(f"No email address provided for user {user.id}, skipping email")
    except Exception as e:
        print(f"Error sending welcome email: {str(e)}")
        # Don't fail user creation if email fails, just log the error
    
    # Log action
    await audit_service.log_action(
        "user_created",
        admin.id,
        {"user_id": user.id, "full_name": user.full_name}
    )
    
    return UserResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        phone_number=user.phone_number,
        matric_number=user.matric_number,
        picture=user.picture,
        status=user.status,
        created_at=user.created_at.isoformat()
    )


@router.get("", response_model=list)
async def get_users(skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000), 
                   admin = Depends(require_admin)):
    """Get all users (Admin only)"""
    db = get_database()
    user_service = UserService(db)
    
    users = await user_service.get_all_users(skip, limit)
    return [
        UserResponse(
            id=u.id,
            full_name=u.full_name,
            email=u.email,
            phone_number=u.phone_number,
            matric_number=u.matric_number,
            picture=u.picture,
            status=u.status,
            created_at=ensure_user_timestamp(u.created_at)
        ) for u in users
    ]


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, operator = Depends(require_operator)):
    """Get user by ID (Operator/Admin)"""
    db = get_database()
    user_service = UserService(db)
    
    user = await user_service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return UserResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        phone_number=user.phone_number,
        matric_number=user.matric_number,
        picture=user.picture,
        status=user.status,
        created_at=ensure_user_timestamp(user.created_at)
    )


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(user_id: str, user_data: UserUpdate, admin = Depends(require_admin)):
    """Update user (Admin only)"""
    db = get_database()
    user_service = UserService(db)
    audit_service = AuditLogService(db)
    
    user = await user_service.update_user(
        user_id,
        user_data.full_name,
        user_data.email,
        user_data.phone_number,
        user_data.matric_number,
        user_data.picture,
        user_data.status
    )
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Log action
    await audit_service.log_action(
        "user_updated",
        admin.id,
        {"user_id": user_id}
    )
    
    return UserResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        phone_number=user.phone_number,
        matric_number=user.matric_number,
        picture=user.picture,
        status=user.status,
        created_at=ensure_user_timestamp(user.created_at)
    )


@router.delete("/{user_id}")
async def delete_user(user_id: str, admin = Depends(require_admin)):
    """Delete user (Admin only)"""
    db = get_database()
    user_service = UserService(db)
    audit_service = AuditLogService(db)
    
    success = await user_service.delete_user(user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Log action
    await audit_service.log_action(
        "user_deleted",
        admin.id,
        {"user_id": user_id}
    )
    
    return {"message": "User deleted successfully"}


@router.post("/{user_id}/suspend")
async def suspend_user(user_id: str, admin = Depends(require_admin)):
    """Suspend a user (Admin only)"""
    db = get_database()
    user_service = UserService(db)
    audit_service = AuditLogService(db)
    
    user = await user_service.suspend_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Log action
    await audit_service.log_action(
        "user_suspended",
        admin.id,
        {"user_id": user_id}
    )
    
    return {"message": f"User {user_id} suspended"}


@router.post("/{user_id}/activate")
async def activate_user(user_id: str, admin = Depends(require_admin)):
    """Activate a user (Admin only)"""
    db = get_database()
    user_service = UserService(db)
    audit_service = AuditLogService(db)
    
    user = await user_service.activate_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Log action
    await audit_service.log_action(
        "user_activated",
        admin.id,
        {"user_id": user_id}
    )
    
    return {"message": f"User {user_id} activated"}
