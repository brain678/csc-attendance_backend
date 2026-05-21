from fastapi import APIRouter, Depends, HTTPException, status, Query
from app.core.mongodb import get_database
from app.services.staff_service import StaffService
from app.services.audit_service import AuditLogService
from app.models.requests import StaffCreate, StaffUpdate, StaffChangePassword, StaffResponse
from app.api.dependencies import require_admin, get_current_staff

router = APIRouter(prefix="/api/staff", tags=["Staff"])


@router.post("", response_model=StaffResponse, status_code=status.HTTP_201_CREATED)
async def create_staff(staff_data: StaffCreate, admin = Depends(require_admin)):
    """Create a new staff member (Admin only)"""
    db = get_database()
    staff_service = StaffService(db)
    audit_service = AuditLogService(db)
    
    # Check if email already exists
    existing = await staff_service.get_staff_by_email(staff_data.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    staff = await staff_service.create_staff(
        staff_data.name,
        staff_data.email,
        staff_data.role,
        staff_data.password
    )
    
    # Log action
    await audit_service.log_action(
        "staff_created",
        admin.id if admin else "system",
        {"staff_id": staff.id, "email": staff.email}
    )
    
    return StaffResponse(
        id=staff.id,
        name=staff.name,
        email=staff.email,
        role=staff.role,
        created_at=staff.created_at.isoformat()
    )


@router.post("/bootstrap", response_model=StaffResponse, status_code=status.HTTP_201_CREATED)
async def bootstrap_admin(staff_data: StaffCreate):
    """Bootstrap the first admin (no auth required) - Use only during initial setup"""
    db = get_database()
    staff_service = StaffService(db)
    audit_service = AuditLogService(db)
    
    # Check if any staff exists
    all_staff = await staff_service.get_all_staff()
    if all_staff:
        raise HTTPException(
            status_code=403,
            detail="Bootstrap only allowed when no staff exists. Use regular POST endpoint instead."
        )
    
    # Check if email already exists
    existing = await staff_service.get_staff_by_email(staff_data.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    staff = await staff_service.create_staff(
        staff_data.name,
        staff_data.email,
        staff_data.role,
        staff_data.password
    )
    
    # Log action
    await audit_service.log_action(
        "staff_created",
        "bootstrap",
        {"staff_id": staff.id, "email": staff.email, "role": "admin bootstrap"}
    )
    
    return StaffResponse(
        id=staff.id,
        name=staff.name,
        email=staff.email,
        role=staff.role,
        created_at=staff.created_at.isoformat()
    )


@router.get("", response_model=list)
async def get_all_staff(skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000),
                       admin = Depends(require_admin)):
    """Get all staff members (Admin only)"""
    db = get_database()
    staff_service = StaffService(db)
    
    staff_list = await staff_service.get_all_staff(skip, limit)
    return [
        StaffResponse(
            id=s.id,
            name=s.name,
            email=s.email,
            role=s.role,
            created_at=s.created_at.isoformat()
        ) for s in staff_list
    ]


@router.get("/{staff_id}", response_model=StaffResponse)
async def get_staff(staff_id: str, admin = Depends(require_admin)):
    """Get staff by ID (Admin only)"""
    db = get_database()
    staff_service = StaffService(db)
    
    staff = await staff_service.get_staff(staff_id)
    if not staff:
        raise HTTPException(status_code=404, detail="Staff not found")
    
    return StaffResponse(
        id=staff.id,
        name=staff.name,
        email=staff.email,
        role=staff.role,
        created_at=staff.created_at.isoformat()
    )


@router.put("/{staff_id}", response_model=StaffResponse)
async def update_staff(staff_id: str, staff_data: StaffUpdate, admin = Depends(require_admin)):
    """Update staff (Admin only)"""
    db = get_database()
    staff_service = StaffService(db)
    audit_service = AuditLogService(db)
    
    staff = await staff_service.update_staff(
        staff_id,
        staff_data.name,
        staff_data.role
    )
    
    if not staff:
        raise HTTPException(status_code=404, detail="Staff not found")
    
    # Log action
    await audit_service.log_action(
        "staff_updated",
        admin.id,
        {"staff_id": staff_id}
    )
    
    return StaffResponse(
        id=staff.id,
        name=staff.name,
        email=staff.email,
        role=staff.role,
        created_at=staff.created_at.isoformat()
    )


@router.delete("/{staff_id}")
async def delete_staff(staff_id: str, admin = Depends(require_admin)):
    """Delete staff member (Admin only)"""
    db = get_database()
    staff_service = StaffService(db)
    audit_service = AuditLogService(db)
    
    success = await staff_service.delete_staff(staff_id)
    if not success:
        raise HTTPException(status_code=404, detail="Staff not found")
    
    # Log action
    await audit_service.log_action(
        "staff_deleted",
        admin.id,
        {"staff_id": staff_id}
    )
    
    return {"message": "Staff member deleted successfully"}


@router.post("/change-password")
async def change_password(pwd_data: StaffChangePassword, staff = Depends(get_current_staff)):
    """Change own password"""
    db = get_database()
    staff_service = StaffService(db)
    audit_service = AuditLogService(db)
    
    # Verify current password
    current = await staff_service.authenticate_staff(staff.email, pwd_data.current_password)
    if not current:
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    
    updated = await staff_service.change_password(staff.id, pwd_data.new_password)
    if not updated:
        raise HTTPException(status_code=400, detail="Could not change password")
    
    # Log action
    await audit_service.log_action(
        "password_changed",
        staff.id,
        {"staff_id": staff.id}
    )
    
    return {"message": "Password changed successfully"}
