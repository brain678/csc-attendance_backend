from fastapi import APIRouter, Depends, HTTPException, status
from datetime import timedelta, datetime, timezone
from app.core.config import settings
from app.core.security import create_access_token
from app.core.mongodb import get_database
from app.services.staff_service import StaffService
from app.services.qr_service import QRTokenService
from app.services.user_service import UserService
from app.services.lecturer_service import LecturerService
from app.models.requests import StaffLogin, TokenResponse, QRTokenValidate
from app.api.dependencies import get_current_staff, get_current_account

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.options("/login")
async def options_login():
    """CORS preflight for login"""
    return {}


@router.post("/login", response_model=TokenResponse)
async def login(credentials: StaffLogin):
    """Admin or lecturer login endpoint"""
    db = get_database()
    staff_service = StaffService(db)
    lecturer_service = LecturerService(db)

    staff = await staff_service.authenticate_staff(credentials.email, credentials.password)
    if staff:
        access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
        access_token = create_access_token(
            data={"sub": staff.id, "role": "admin", "name": staff.name},
            expires_delta=access_token_expires,
        )
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user_id": staff.id,
            "role": "admin",
            "name": staff.name,
        }

    lecturer = await lecturer_service.authenticate_lecturer(credentials.email, credentials.password)
    if not lecturer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": lecturer.id, "role": "lecturer", "name": lecturer.full_name},
        expires_delta=access_token_expires,
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": lecturer.id,
        "role": "lecturer",
        "name": lecturer.full_name,
    }


@router.post("/verify")
async def verify_token(account = Depends(get_current_account)):
    """Verify authentication token"""
    role = account["role"]
    user = account["account"]
    name = user.name if role == "admin" else getattr(user, "full_name", None)
    response = {
        "valid": True,
        "user_id": user.id,
        "name": name,
        "role": role,
    }

    if role == "lecturer":
        response["department_id"] = getattr(user, "department_id", None)

    return response


@router.post("/logout")
async def logout(staff = Depends(get_current_staff)):
    """Logout endpoint (token is invalidated on client side)"""
    return {"message": "Logged out successfully"}


@router.post("/qr", response_model=TokenResponse)
async def login_with_qr(payload: QRTokenValidate):
    """Authenticate a user by QR token id and return a temporary JWT"""
    token_id = payload.token

    db = get_database()
    qr_service = QRTokenService(db)
    token_obj = await qr_service.get_qr_token(token_id)
    if not token_obj or not token_obj.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or inactive QR token")

    # Create access token for user
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": token_obj.user_id},
        expires_delta=access_token_expires
    )

    return {"access_token": access_token, "token_type": "bearer", "user_id": token_obj.user_id}
