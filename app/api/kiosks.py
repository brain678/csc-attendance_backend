from fastapi import APIRouter, Depends, HTTPException, status, Query
from app.core.mongodb import get_database
from app.services.kiosk_service import KioskService
from app.services.audit_service import AuditLogService
from app.models.requests import KioskRegister, KioskUpdate, KioskResponse
from app.api.dependencies import require_admin
from typing import Optional
from pydantic import BaseModel

router = APIRouter(prefix="/api/kiosks", tags=["Kiosks"])


class KioskSelfRegister(BaseModel):
    """Kiosk self-registration request"""
    device_name: str
    ip_address: Optional[str] = None
    hardware_id: Optional[str] = None
    location: Optional[str] = None


class KioskRegistrationResponse(BaseModel):
    """Response with kiosk ID for self-registered kiosk"""
    id: str
    device_name: str
    is_active: bool
    registered_at: str
    message: str


@router.post("/self-register", response_model=KioskRegistrationResponse, status_code=status.HTTP_201_CREATED)
async def self_register_kiosk(kiosk_data: KioskSelfRegister):
    """Self-register a kiosk device (No authentication required) ✅
    
    This endpoint allows a kiosk to register itself without admin credentials.
    The kiosk receives a unique ID to use in subsequent requests.
    
    Returns the kiosk ID to store in environment variables.
    """
    db = get_database()
    kiosk_service = KioskService(db)
    
    # Check if kiosk with same hardware_id exists
    if kiosk_data.hardware_id:
        cursor = db.kiosks.find({"hardware_id": kiosk_data.hardware_id})
        existing = await cursor.to_list(length=1)
        if existing:
            existing_kiosk = existing[0]
            existing_kiosk["id"] = existing_kiosk.pop("_id")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Kiosk with this hardware ID already registered. ID: {existing_kiosk['id']}"
            )
    
    # Register the kiosk
    kiosk = await kiosk_service.register_kiosk(
        kiosk_data.device_name,
        kiosk_data.ip_address
    )
    
    # Update with additional fields if provided
    if kiosk_data.hardware_id or kiosk_data.location:
        update_data = {}
        if kiosk_data.hardware_id:
            update_data["hardware_id"] = kiosk_data.hardware_id
        if kiosk_data.location:
            update_data["location"] = kiosk_data.location
        
        if update_data:
            await db.kiosks.update_one(
                {"_id": kiosk.id},
                {"$set": update_data}
            )
    
    return KioskRegistrationResponse(
        id=kiosk.id,
        device_name=kiosk.device_name,
        is_active=kiosk.is_active,
        registered_at=kiosk.registered_at.isoformat(),
        message=f"✅ Kiosk registered successfully! Use ID: {kiosk.id}"
    )


@router.get("/status/{kiosk_id}")
async def check_kiosk_status(kiosk_id: str):
    """Check kiosk registration and status (Public - no auth) ✅
    
    Kiosks can call this to verify they are registered.
    
    Returns:
    - 200: Kiosk is registered and active
    - 404: Kiosk not found
    - 451: Kiosk inactive (deactivated by admin)
    """
    db = get_database()
    kiosk_service = KioskService(db)
    
    kiosk = await kiosk_service.get_kiosk(kiosk_id)
    if not kiosk:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Kiosk {kiosk_id} not found. Please self-register first."
        )
    
    if not kiosk.is_active:
        raise HTTPException(
            status_code=451,  # Unavailable For Legal Reasons (repurposed as "deactivated")
            detail=f"Kiosk {kiosk_id} has been deactivated. Contact admin for reactivation."
        )
    
    return {
        "status": "active",
        "id": kiosk.id,
        "device_name": kiosk.device_name,
        "is_active": kiosk.is_active,
        "registered_at": kiosk.registered_at.isoformat() if kiosk.registered_at else None,
        "location": getattr(kiosk, 'location', None),
        "message": "✅ Kiosk is registered and ready to operate"
    }


@router.post("", response_model=KioskResponse, status_code=status.HTTP_201_CREATED)
async def register_kiosk(kiosk_data: KioskRegister, admin = Depends(require_admin)):
    """Register a new kiosk device (Admin only)"""
    db = get_database()
    kiosk_service = KioskService(db)
    audit_service = AuditLogService(db)
    
    kiosk = await kiosk_service.register_kiosk(
        kiosk_data.device_name,
        kiosk_data.ip_address
    )
    
    # Log action
    await audit_service.log_action(
        "kiosk_registered",
        admin.id,
        {"kiosk_id": kiosk.id, "device_name": kiosk.device_name}
    )
    
    return KioskResponse(
        id=kiosk.id,
        device_name=kiosk.device_name,
        is_active=kiosk.is_active,
        registered_at=kiosk.registered_at.isoformat(),
        ip_address=kiosk.ip_address
    )


@router.get("", response_model=list)
async def get_all_kiosks(skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000),
                        admin = Depends(require_admin)):
    """Get all kiosks (Admin only)"""
    db = get_database()
    kiosk_service = KioskService(db)
    
    kiosks = await kiosk_service.get_all_kiosks(skip, limit)
    return [
        KioskResponse(
            id=k.id,
            device_name=k.device_name,
            is_active=k.is_active,
            registered_at=k.registered_at.isoformat(),
            ip_address=k.ip_address
        ) for k in kiosks
    ]


@router.get("/active")
async def get_active_kiosks(admin = Depends(require_admin)):
    """Get all active kiosks (Admin only)"""
    db = get_database()
    kiosk_service = KioskService(db)
    
    kiosks = await kiosk_service.get_active_kiosks()
    return [
        KioskResponse(
            id=k.id,
            device_name=k.device_name,
            is_active=k.is_active,
            registered_at=k.registered_at.isoformat(),
            ip_address=k.ip_address
        ) for k in kiosks
    ]


@router.get("/{kiosk_id}", response_model=KioskResponse)
async def get_kiosk(kiosk_id: str, admin = Depends(require_admin)):
    """Get kiosk by ID (Admin only)"""
    db = get_database()
    kiosk_service = KioskService(db)
    
    kiosk = await kiosk_service.get_kiosk(kiosk_id)
    if not kiosk:
        raise HTTPException(status_code=404, detail="Kiosk not found")
    
    return KioskResponse(
        id=kiosk.id,
        device_name=kiosk.device_name,
        is_active=kiosk.is_active,
        registered_at=kiosk.registered_at.isoformat(),
        ip_address=kiosk.ip_address
    )


@router.put("/{kiosk_id}", response_model=KioskResponse)
async def update_kiosk(kiosk_id: str, kiosk_data: KioskUpdate, admin = Depends(require_admin)):
    """Update kiosk (Admin only)"""
    db = get_database()
    kiosk_service = KioskService(db)
    audit_service = AuditLogService(db)
    
    kiosk = await kiosk_service.update_kiosk(
        kiosk_id,
        kiosk_data.device_name,
        kiosk_data.ip_address,
        kiosk_data.is_active
    )
    
    if not kiosk:
        raise HTTPException(status_code=404, detail="Kiosk not found")
    
    # Log action
    await audit_service.log_action(
        "kiosk_updated",
        admin.id,
        {"kiosk_id": kiosk_id}
    )
    
    return KioskResponse(
        id=kiosk.id,
        device_name=kiosk.device_name,
        is_active=kiosk.is_active,
        registered_at=kiosk.registered_at.isoformat(),
        ip_address=kiosk.ip_address
    )


@router.delete("/{kiosk_id}")
async def delete_kiosk(kiosk_id: str, admin = Depends(require_admin)):
    """Delete kiosk (Admin only)"""
    db = get_database()
    kiosk_service = KioskService(db)
    audit_service = AuditLogService(db)
    
    success = await kiosk_service.delete_kiosk(kiosk_id)
    if not success:
        raise HTTPException(status_code=404, detail="Kiosk not found")
    
    # Log action
    await audit_service.log_action(
        "kiosk_deleted",
        admin.id,
        {"kiosk_id": kiosk_id}
    )
    
    return {"message": "Kiosk deleted successfully"}


@router.post("/{kiosk_id}/deactivate")
async def deactivate_kiosk(kiosk_id: str, admin = Depends(require_admin)):
    """Deactivate a kiosk (Admin only)"""
    db = get_database()
    kiosk_service = KioskService(db)
    audit_service = AuditLogService(db)
    
    kiosk = await kiosk_service.deactivate_kiosk(kiosk_id)
    if not kiosk:
        raise HTTPException(status_code=404, detail="Kiosk not found")
    
    # Log action
    await audit_service.log_action(
        "kiosk_deactivated",
        admin.id,
        {"kiosk_id": kiosk_id}
    )
    
    return {"message": f"Kiosk {kiosk_id} deactivated"}


@router.post("/{kiosk_id}/activate")
async def activate_kiosk(kiosk_id: str, admin = Depends(require_admin)):
    """Activate a kiosk (Admin only)"""
    db = get_database()
    kiosk_service = KioskService(db)
    audit_service = AuditLogService(db)
    
    kiosk = await kiosk_service.activate_kiosk(kiosk_id)
    if not kiosk:
        raise HTTPException(status_code=404, detail="Kiosk not found")
    
    # Log action
    await audit_service.log_action(
        "kiosk_activated",
        admin.id,
        {"kiosk_id": kiosk_id}
    )
    
    return {"message": f"Kiosk {kiosk_id} activated"}

@router.post("/{kiosk_id}/health-check")
async def health_check_kiosk(kiosk_id: str, admin = Depends(require_admin)):
    """Check kiosk health status and connectivity (Admin only)"""
    db = get_database()
    kiosk_service = KioskService(db)
    audit_service = AuditLogService(db)
    
    health_info = await kiosk_service.check_kiosk_health(kiosk_id)
    
    if health_info.get("status") == "success":
        # Log action
        await audit_service.log_action(
            "kiosk_health_check",
            admin.id,
            {
                "kiosk_id": kiosk_id,
                "is_online": health_info.get("is_online"),
                "health_status": health_info.get("health_status")
            }
        )
    
    return health_info


@router.post("/{kiosk_id}/assign/{staff_id}")
async def assign_kiosk_to_staff(kiosk_id: str, staff_id: str, admin = Depends(require_admin)):
    """Assign a kiosk to a staff operator (Admin only) ✅"""
    db = get_database()
    kiosk_service = KioskService(db)
    staff_service = __import__('app.services.staff_service', fromlist=['StaffService']).StaffService(db)
    audit_service = AuditLogService(db)
    
    # Verify kiosk exists
    kiosk = await kiosk_service.get_kiosk(kiosk_id)
    if not kiosk:
        raise HTTPException(status_code=404, detail="Kiosk not found")
    
    # Verify staff exists
    staff = await staff_service.get_staff(staff_id)
    if not staff:
        raise HTTPException(status_code=404, detail="Staff member not found")
    
    # Assign kiosk
    updated_kiosk = await kiosk_service.assign_to_staff(kiosk_id, staff_id)
    
    # Log action
    await audit_service.log_action(
        "kiosk_assigned_to_staff",
        admin.id,
        {"kiosk_id": kiosk_id, "staff_id": staff_id, "staff_name": staff.name}
    )
    
    return {
        "status": "success",
        "message": f"✓ Kiosk '{kiosk.device_name}' assigned to {staff.name}",
        "kiosk_id": kiosk_id,
        "assigned_to": staff_id,
        "operator_name": staff.name
    }


@router.post("/{kiosk_id}/unassign")
async def unassign_kiosk(kiosk_id: str, admin = Depends(require_admin)):
    """Unassign a kiosk from staff operator (Admin only) ✅"""
    db = get_database()
    kiosk_service = KioskService(db)
    audit_service = AuditLogService(db)
    
    # Verify kiosk exists
    kiosk = await kiosk_service.get_kiosk(kiosk_id)
    if not kiosk:
        raise HTTPException(status_code=404, detail="Kiosk not found")
    
    # Get operator name before unassigning
    operator_name = None
    if kiosk.assigned_to:
        staff_service = __import__('app.services.staff_service', fromlist=['StaffService']).StaffService(db)
        staff = await staff_service.get_staff(kiosk.assigned_to)
        operator_name = staff.name if staff else "Unknown"
    
    # Unassign
    await kiosk_service.assign_to_staff(kiosk_id, None)
    
    # Log action
    await audit_service.log_action(
        "kiosk_unassigned",
        admin.id,
        {"kiosk_id": kiosk_id, "previous_operator": operator_name}
    )
    
    return {
        "status": "success",
        "message": f"✓ Kiosk '{kiosk.device_name}' has been unassigned",
        "kiosk_id": kiosk_id
    }


@router.get("/staff/{staff_id}/kiosks")
async def get_staff_kiosks(staff_id: str, admin = Depends(require_admin)):
    """Get all kiosks assigned to a staff member (Admin only) ✅"""
    db = get_database()
    kiosk_service = KioskService(db)
    staff_service = __import__('app.services.staff_service', fromlist=['StaffService']).StaffService(db)
    
    # Verify staff exists
    staff = await staff_service.get_staff(staff_id)
    if not staff:
        raise HTTPException(status_code=404, detail="Staff member not found")
    
    # Get kiosks
    kiosks = await kiosk_service.get_kiosks_by_staff(staff_id)
    
    return {
        "staff_id": staff_id,
        "staff_name": staff.name,
        "total_kiosks": len(kiosks),
        "kiosks": [
            {
                "id": k.id,
                "device_name": k.device_name,
                "is_active": k.is_active,
                "location": getattr(k, 'location', None),
                "health_status": getattr(k, 'health_status', None),
                "ip_address": k.ip_address
            } for k in kiosks
        ]
    }
