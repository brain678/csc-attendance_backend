from fastapi import APIRouter, Depends, HTTPException, status, Query
from app.core.mongodb import get_database
from app.services.lecturer_service import LecturerService
from app.services.audit_service import AuditLogService
from app.models.requests import LecturerCreate, LecturerUpdate, LecturerResponse
from app.api.dependencies import require_admin

router = APIRouter(prefix="/api/lecturers", tags=["Lecturers"])


@router.post("", response_model=LecturerResponse, status_code=status.HTTP_201_CREATED)
async def create_lecturer(payload: LecturerCreate, admin=Depends(require_admin)):
    db = get_database()
    lecturer_service = LecturerService(db)
    audit_service = AuditLogService(db)

    existing = await lecturer_service.get_lecturer_by_email(payload.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    lecturer = await lecturer_service.create_lecturer(
        payload.full_name,
        payload.email,
        payload.department_id,
        payload.password,
    )

    await audit_service.log_action(
        "lecturer_created",
        admin.id,
        {"lecturer_id": lecturer.id, "email": lecturer.email},
    )

    return LecturerResponse(
        id=lecturer.id,
        full_name=lecturer.full_name,
        email=lecturer.email,
        department_id=lecturer.department_id,
        status=lecturer.status,
        created_at=lecturer.created_at.isoformat(),
    )


@router.get("", response_model=list)
async def list_lecturers(skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000),
                         admin=Depends(require_admin)):
    db = get_database()
    lecturer_service = LecturerService(db)
    lecturers = await lecturer_service.get_all_lecturers(skip, limit)
    return [
        LecturerResponse(
            id=lecturer.id,
            full_name=lecturer.full_name,
            email=lecturer.email,
            department_id=lecturer.department_id,
            status=lecturer.status,
            created_at=lecturer.created_at.isoformat(),
        )
        for lecturer in lecturers
    ]


@router.get("/{lecturer_id}", response_model=LecturerResponse)
async def get_lecturer(lecturer_id: str, admin=Depends(require_admin)):
    db = get_database()
    lecturer_service = LecturerService(db)
    lecturer = await lecturer_service.get_lecturer(lecturer_id)
    if not lecturer:
        raise HTTPException(status_code=404, detail="Lecturer not found")

    return LecturerResponse(
        id=lecturer.id,
        full_name=lecturer.full_name,
        email=lecturer.email,
        department_id=lecturer.department_id,
        status=lecturer.status,
        created_at=lecturer.created_at.isoformat(),
    )


@router.put("/{lecturer_id}", response_model=LecturerResponse)
async def update_lecturer(lecturer_id: str, payload: LecturerUpdate, admin=Depends(require_admin)):
    db = get_database()
    lecturer_service = LecturerService(db)
    audit_service = AuditLogService(db)

    lecturer = await lecturer_service.update_lecturer(
        lecturer_id,
        full_name=payload.full_name,
        department_id=payload.department_id,
        status=payload.status,
    )
    if not lecturer:
        raise HTTPException(status_code=404, detail="Lecturer not found")

    await audit_service.log_action(
        "lecturer_updated",
        admin.id,
        {"lecturer_id": lecturer_id},
    )

    return LecturerResponse(
        id=lecturer.id,
        full_name=lecturer.full_name,
        email=lecturer.email,
        department_id=lecturer.department_id,
        status=lecturer.status,
        created_at=lecturer.created_at.isoformat(),
    )


@router.delete("/{lecturer_id}")
async def delete_lecturer(lecturer_id: str, admin=Depends(require_admin)):
    db = get_database()
    lecturer_service = LecturerService(db)
    audit_service = AuditLogService(db)

    success = await lecturer_service.delete_lecturer(lecturer_id)
    if not success:
        raise HTTPException(status_code=404, detail="Lecturer not found")

    await audit_service.log_action(
        "lecturer_deleted",
        admin.id,
        {"lecturer_id": lecturer_id},
    )

    return {"message": "Lecturer deleted"}
