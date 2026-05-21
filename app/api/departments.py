from fastapi import APIRouter, Depends, HTTPException, status, Query
from app.core.mongodb import get_database
from app.services.department_service import DepartmentService
from app.services.audit_service import AuditLogService
from app.models.requests import DepartmentCreate, DepartmentUpdate, DepartmentResponse
from app.api.dependencies import require_admin

router = APIRouter(prefix="/api/departments", tags=["Departments"])


@router.post("", response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED)
async def create_department(payload: DepartmentCreate, admin=Depends(require_admin)):
    db = get_database()
    department_service = DepartmentService(db)
    audit_service = AuditLogService(db)

    existing = await department_service.get_department_by_code(payload.code)
    if existing:
        raise HTTPException(status_code=400, detail="Department code already exists")

    department = await department_service.create_department(payload.name, payload.code)

    await audit_service.log_action(
        "department_created",
        admin.id,
        {"department_id": department.id, "code": department.code},
    )

    return DepartmentResponse(
        id=department.id,
        name=department.name,
        code=department.code,
        created_at=department.created_at.isoformat(),
    )


@router.get("", response_model=list)
async def list_departments(skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000)):
    db = get_database()
    department_service = DepartmentService(db)
    departments = await department_service.get_all_departments(skip, limit)
    return [
        DepartmentResponse(
            id=department.id,
            name=department.name,
            code=department.code,
            created_at=department.created_at.isoformat(),
        )
        for department in departments
    ]


@router.put("/{department_id}", response_model=DepartmentResponse)
async def update_department(department_id: str, payload: DepartmentUpdate, admin=Depends(require_admin)):
    db = get_database()
    department_service = DepartmentService(db)
    audit_service = AuditLogService(db)

    if payload.code:
        existing = await department_service.get_department_by_code(payload.code)
        if existing and existing.id != department_id:
            raise HTTPException(status_code=400, detail="Department code already exists")

    department = await department_service.update_department(
        department_id,
        name=payload.name,
        code=payload.code,
    )
    if not department:
        raise HTTPException(status_code=404, detail="Department not found")

    await audit_service.log_action(
        "department_updated",
        admin.id,
        {"department_id": department_id},
    )

    return DepartmentResponse(
        id=department.id,
        name=department.name,
        code=department.code,
        created_at=department.created_at.isoformat(),
    )


@router.delete("/{department_id}")
async def delete_department(department_id: str, admin=Depends(require_admin)):
    db = get_database()
    department_service = DepartmentService(db)
    audit_service = AuditLogService(db)

    success = await department_service.delete_department(department_id)
    if not success:
        raise HTTPException(status_code=404, detail="Department not found")

    await audit_service.log_action(
        "department_deleted",
        admin.id,
        {"department_id": department_id},
    )

    return {"message": "Department deleted"}
