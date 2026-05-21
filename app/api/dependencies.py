from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer
from starlette.authentication import AuthCredentials
from app.core.security import verify_token
from app.core.mongodb import get_database
from app.services.staff_service import StaffService
from app.services.lecturer_service import LecturerService
from app.services.student_service import StudentService
from app.services.kiosk_service import KioskService
from app.models.schemas import StaffRole
from typing import Optional
from app.services.user_service import UserService

security = HTTPBearer()


async def get_current_staff(credentials = Depends(security)):
    """Get current authenticated staff member (admin only)"""
    token = credentials.credentials
    token_data = verify_token(token)

    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if token_data.role and token_data.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    db = get_database()
    staff_service = StaffService(db)
    staff = await staff_service.get_staff(token_data.sub)

    if staff is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Staff member not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return staff


async def get_current_admin(credentials = Depends(security)):
    """Get current authenticated admin"""
    return await get_current_staff(credentials)


async def get_current_lecturer(credentials = Depends(security)):
    """Get current authenticated lecturer"""
    token = credentials.credentials
    token_data = verify_token(token)

    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if token_data.role != "lecturer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Lecturer access required",
        )

    db = get_database()
    lecturer_service = LecturerService(db)
    lecturer = await lecturer_service.get_lecturer(token_data.sub)

    if lecturer is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Lecturer not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return lecturer


async def get_kiosk_or_staff(credentials: Optional[str] = Depends(security), 
                            x_kiosk_id: Optional[str] = Header(None)) -> dict:
    """Authenticate either as a kiosk (via X-Kiosk-ID header) or staff member (via Bearer token)"""
    db = get_database()
    
    # Try kiosk authentication first (higher priority for kiosks)
    if x_kiosk_id:
        kiosk_service = KioskService(db)
        kiosk = await kiosk_service.get_kiosk(x_kiosk_id)
        if kiosk and kiosk.is_active:
            return {
                "type": "kiosk",
                "id": kiosk.id,
                "device_name": kiosk.device_name,
                "role": "kiosk"
            }
    
    # Fall back to staff authentication
    if credentials:
        token_data = verify_token(credentials.credentials)
        if token_data is not None:
            staff_service = StaffService(db)
            staff = await staff_service.get_staff(token_data.sub)
            if staff is not None:
                return {
                    "type": "staff",
                    "id": staff.id,
                    "name": staff.name,
                    "role": staff.role,
                    "email": staff.email
                }
    
    # Authentication failed
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials. Provide either Bearer token or X-Kiosk-ID header",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_admin(staff = Depends(get_current_admin)):
    """Require admin role"""
    if staff.role != StaffRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return staff


async def require_operator(staff = Depends(get_current_staff)):
    """Require operator or admin role"""
    if staff.role not in [StaffRole.operator, StaffRole.admin]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator access required"
        )
    return staff


async def get_current_user(credentials = Depends(security)):
    """Get current authenticated user (for students/lecturers)"""
    token = credentials.credentials
    token_data = verify_token(token)

    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    db = get_database()
    user_service = UserService(db)
    user = await user_service.get_user(token_data.sub)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_student(credentials = Depends(security)):
    """Get current authenticated student"""
    token = credentials.credentials
    token_data = verify_token(token)

    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if token_data.role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Student access required",
        )

    db = get_database()
    student_service = StudentService(db)
    student = await student_service.get_student(token_data.sub)

    if student is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Student not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return student


async def get_current_account(credentials = Depends(security)) -> dict:
    """Get current authenticated account (admin, lecturer, or student)"""
    token = credentials.credentials
    token_data = verify_token(token)

    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    db = get_database()

    if token_data.role == "lecturer":
        lecturer_service = LecturerService(db)
        lecturer = await lecturer_service.get_lecturer(token_data.sub)
        if not lecturer:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Lecturer not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return {"role": "lecturer", "account": lecturer}

    if token_data.role == "student":
        student_service = StudentService(db)
        student = await student_service.get_student(token_data.sub)
        if not student:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Student not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return {"role": "student", "account": student}

    staff_service = StaffService(db)
    staff = await staff_service.get_staff(token_data.sub)
    if not staff:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Staff member not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {"role": "admin", "account": staff}
