from fastapi import APIRouter, Depends, HTTPException, status, Query
from app.core.mongodb import get_database
from app.services.course_service import CourseService
from app.services.lecturer_service import LecturerService
from app.services.audit_service import AuditLogService
from app.models.requests import CourseAssignRequest, CourseCreate, CourseUpdate, CourseResponse
from app.api.dependencies import get_current_lecturer, require_admin

router = APIRouter(prefix="/api/courses", tags=["Courses"])


@router.post("", response_model=CourseResponse, status_code=status.HTTP_201_CREATED)
async def create_course(payload: CourseCreate, admin=Depends(require_admin)):
    db = get_database()
    course_service = CourseService(db)
    lecturer_service = LecturerService(db)
    audit_service = AuditLogService(db)

    existing = await course_service.get_course_by_code(payload.code)
    if existing:
        raise HTTPException(status_code=400, detail="Course code already exists")

    if payload.lecturer_id:
        lecturer = await lecturer_service.get_lecturer(payload.lecturer_id)
        if not lecturer:
            raise HTTPException(status_code=400, detail="Lecturer not found")

    course = await course_service.create_course(
        code=payload.code,
        title=payload.title,
        description=payload.description,
        department_id=payload.department_id,
        lecturer_id=payload.lecturer_id,
    )

    await audit_service.log_action(
        "course_created",
        admin.id,
        {"course_id": course.id, "code": course.code},
    )

    return CourseResponse(
        id=course.id,
        code=course.code,
        title=course.title,
        description=course.description,
        department_id=course.department_id,
        lecturer_id=course.lecturer_id,
        created_at=course.created_at.isoformat(),
    )


@router.get("", response_model=list)
async def list_courses(skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000),
                       department_id: str | None = None, lecturer_id: str | None = None):
    db = get_database()
    course_service = CourseService(db)
    courses = await course_service.get_courses(skip, limit, department_id, lecturer_id)
    return [
        CourseResponse(
            id=course.id,
            code=course.code,
            title=course.title,
            description=course.description,
            department_id=course.department_id,
            lecturer_id=course.lecturer_id,
            created_at=course.created_at.isoformat(),
        )
        for course in courses
    ]


@router.post("/assign", response_model=list[CourseResponse])
async def assign_courses_to_lecturer(
    payload: CourseAssignRequest,
    lecturer=Depends(get_current_lecturer),
):
    db = get_database()
    course_service = CourseService(db)
    audit_service = AuditLogService(db)

    assigned_courses = []
    for course_id in payload.course_ids:
        course = await course_service.get_course(course_id)
        if not course:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Course {course_id} not found")

        if course.department_id != lecturer.department_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot assign a course outside your department",
            )

        if course.lecturer_id and course.lecturer_id != lecturer.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Course {course.code} is already assigned to another lecturer",
            )

        if course.lecturer_id == lecturer.id:
            assigned_courses.append(course)
            continue

        updated = await course_service.update_course(course.id, lecturer_id=lecturer.id)
        if updated:
            assigned_courses.append(updated)

    if assigned_courses:
        await audit_service.log_action(
            "lecturer_assigned_courses",
            lecturer.id,
            {"course_ids": [course.id for course in assigned_courses]},
        )

    return [
        CourseResponse(
            id=course.id,
            code=course.code,
            title=course.title,
            description=course.description,
            department_id=course.department_id,
            lecturer_id=course.lecturer_id,
            created_at=course.created_at.isoformat(),
        )
        for course in assigned_courses
    ]


@router.get("/{course_id}", response_model=CourseResponse)
async def get_course(course_id: str):
    db = get_database()
    course_service = CourseService(db)
    course = await course_service.get_course(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    return CourseResponse(
        id=course.id,
        code=course.code,
        title=course.title,
        description=course.description,
        department_id=course.department_id,
        lecturer_id=course.lecturer_id,
        created_at=course.created_at.isoformat(),
    )


@router.put("/{course_id}", response_model=CourseResponse)
async def update_course(course_id: str, payload: CourseUpdate, admin=Depends(require_admin)):
    db = get_database()
    course_service = CourseService(db)
    lecturer_service = LecturerService(db)
    audit_service = AuditLogService(db)

    if payload.code:
        existing = await course_service.get_course_by_code(payload.code)
        if existing and existing.id != course_id:
            raise HTTPException(status_code=400, detail="Course code already exists")

    if payload.lecturer_id:
        lecturer = await lecturer_service.get_lecturer(payload.lecturer_id)
        if not lecturer:
            raise HTTPException(status_code=400, detail="Lecturer not found")

    course = await course_service.update_course(
        course_id,
        code=payload.code,
        title=payload.title,
        description=payload.description,
        department_id=payload.department_id,
        lecturer_id=payload.lecturer_id,
    )
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    await audit_service.log_action(
        "course_updated",
        admin.id,
        {"course_id": course_id},
    )

    return CourseResponse(
        id=course.id,
        code=course.code,
        title=course.title,
        description=course.description,
        department_id=course.department_id,
        lecturer_id=course.lecturer_id,
        created_at=course.created_at.isoformat(),
    )


@router.delete("/{course_id}")
async def delete_course(course_id: str, admin=Depends(require_admin)):
    db = get_database()
    course_service = CourseService(db)
    audit_service = AuditLogService(db)

    success = await course_service.delete_course(course_id)
    if not success:
        raise HTTPException(status_code=404, detail="Course not found")

    await audit_service.log_action(
        "course_deleted",
        admin.id,
        {"course_id": course_id},
    )

    return {"message": "Course deleted"}
