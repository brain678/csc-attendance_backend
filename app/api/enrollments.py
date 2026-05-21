from fastapi import APIRouter, Depends, HTTPException, status, Query
from app.core.mongodb import get_database
from app.services.enrollment_service import EnrollmentService
from app.services.course_service import CourseService
from app.services.audit_service import AuditLogService
from app.models.requests import EnrollmentRequest, EnrollmentBulkRequest, EnrollmentBatchRequest, EnrollmentDetail
from app.models.schemas import EnrollmentStatus
from app.api.dependencies import get_current_student, get_current_lecturer, get_current_admin, get_current_account, require_admin

router = APIRouter(prefix="/api/enrollments", tags=["Enrollments"])


@router.post("/request", response_model=EnrollmentDetail, status_code=status.HTTP_201_CREATED)
async def request_enrollment(payload: EnrollmentRequest, student=Depends(get_current_student)):
    db = get_database()
    course_service = CourseService(db)
    enrollment_service = EnrollmentService(db)

    course = await course_service.get_course_by_code(payload.course_code)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    enrollment = await enrollment_service.request_enrollment(student.id, course.id)

    return EnrollmentDetail(
        id=enrollment.id,
        student_id=enrollment.student_id,
        course_id=enrollment.course_id,
        status=enrollment.status,
        requested_at=enrollment.requested_at.isoformat(),
        reviewed_at=enrollment.reviewed_at.isoformat() if enrollment.reviewed_at else None,
        reviewed_by=enrollment.reviewed_by,
    )


@router.get("/me", response_model=list)
async def list_my_enrollments(student=Depends(get_current_student)):
    db = get_database()
    enrollment_service = EnrollmentService(db)
    enrollments = await enrollment_service.get_enrollments(student_id=student.id)
    return [
        EnrollmentDetail(
            id=enrollment.id,
            student_id=enrollment.student_id,
            course_id=enrollment.course_id,
            status=enrollment.status,
            requested_at=enrollment.requested_at.isoformat(),
            reviewed_at=enrollment.reviewed_at.isoformat() if enrollment.reviewed_at else None,
            reviewed_by=enrollment.reviewed_by,
        )
        for enrollment in enrollments
    ]


@router.get("/pending", response_model=list)
async def list_pending_enrollments(skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000),
                                   lecturer=Depends(get_current_lecturer)):
    db = get_database()
    course_service = CourseService(db)
    enrollment_service = EnrollmentService(db)

    courses = await course_service.get_courses(0, 1000, lecturer_id=lecturer.id)
    course_ids = [course.id for course in courses]

    enrollments = await enrollment_service.get_enrollments_by_courses(
        course_ids,
        status=EnrollmentStatus.pending,
        skip=skip,
        limit=limit,
    )

    return [
        EnrollmentDetail(
            id=enrollment.id,
            student_id=enrollment.student_id,
            course_id=enrollment.course_id,
            status=enrollment.status,
            requested_at=enrollment.requested_at.isoformat(),
            reviewed_at=enrollment.reviewed_at.isoformat() if enrollment.reviewed_at else None,
            reviewed_by=enrollment.reviewed_by,
        )
        for enrollment in enrollments
    ]


@router.post("/request-bulk", response_model=list, status_code=status.HTTP_201_CREATED)
async def request_enrollments(payload: EnrollmentBulkRequest, student=Depends(get_current_student)):
    db = get_database()
    course_service = CourseService(db)
    enrollment_service = EnrollmentService(db)

    results = []
    for course_code in payload.course_codes:
        course = await course_service.get_course_by_code(course_code)
        if not course:
            continue
        enrollment = await enrollment_service.request_enrollment(student.id, course.id)
        results.append(
            EnrollmentDetail(
                id=enrollment.id,
                student_id=enrollment.student_id,
                course_id=enrollment.course_id,
                status=enrollment.status,
                requested_at=enrollment.requested_at.isoformat(),
                reviewed_at=enrollment.reviewed_at.isoformat() if enrollment.reviewed_at else None,
                reviewed_by=enrollment.reviewed_by,
            )
        )

    if not results:
        raise HTTPException(status_code=404, detail="No valid courses found for request")

    return results


@router.post("/batch/approve", response_model=list)
async def batch_approve_enrollments(payload: EnrollmentBatchRequest, account=Depends(get_current_account)):
    db = get_database()
    enrollment_service = EnrollmentService(db)
    course_service = CourseService(db)
    audit_service = AuditLogService(db)

    if account['role'] == 'lecturer':
        reviewer = account['account']
        reviewer_id = reviewer.id
        reviewer_role = 'lecturer'
    elif account['role'] == 'admin':
        reviewer_id = account['account'].id
        reviewer_role = 'admin'
    else:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    approved = []
    for enrollment_id in payload.enrollment_ids:
        enrollment = await enrollment_service.get_enrollment(enrollment_id)
        if not enrollment:
            continue
        if reviewer_role == 'lecturer':
            course = await course_service.get_course(enrollment.course_id)
            if not course or course.lecturer_id != reviewer_id:
                continue
        updated = await enrollment_service.update_status(enrollment_id, EnrollmentStatus.approved, reviewer_id)
        if not updated:
            continue
        await audit_service.log_action(
            "enrollment_approved",
            reviewer_id,
            {"enrollment_id": enrollment_id, "course_id": enrollment.course_id},
        )
        approved.append(
            EnrollmentDetail(
                id=updated.id,
                student_id=updated.student_id,
                course_id=updated.course_id,
                status=updated.status,
                requested_at=updated.requested_at.isoformat(),
                reviewed_at=updated.reviewed_at.isoformat() if updated.reviewed_at else None,
                reviewed_by=updated.reviewed_by,
            )
        )

    if not approved:
        raise HTTPException(status_code=400, detail="No enrollments could be approved")

    return approved


@router.post("/batch/deny", response_model=list)
async def batch_deny_enrollments(payload: EnrollmentBatchRequest, account=Depends(get_current_account)):
    db = get_database()
    enrollment_service = EnrollmentService(db)
    course_service = CourseService(db)
    audit_service = AuditLogService(db)

    if account['role'] == 'lecturer':
        reviewer = account['account']
        reviewer_id = reviewer.id
        reviewer_role = 'lecturer'
    elif account['role'] == 'admin':
        reviewer_id = account['account'].id
        reviewer_role = 'admin'
    else:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    denied = []
    for enrollment_id in payload.enrollment_ids:
        enrollment = await enrollment_service.get_enrollment(enrollment_id)
        if not enrollment:
            continue
        if reviewer_role == 'lecturer':
            course = await course_service.get_course(enrollment.course_id)
            if not course or course.lecturer_id != reviewer_id:
                continue
        updated = await enrollment_service.update_status(enrollment_id, EnrollmentStatus.denied, reviewer_id)
        if not updated:
            continue
        await audit_service.log_action(
            "enrollment_denied",
            reviewer_id,
            {"enrollment_id": enrollment_id, "course_id": enrollment.course_id},
        )
        denied.append(
            EnrollmentDetail(
                id=updated.id,
                student_id=updated.student_id,
                course_id=updated.course_id,
                status=updated.status,
                requested_at=updated.requested_at.isoformat(),
                reviewed_at=updated.reviewed_at.isoformat() if updated.reviewed_at else None,
                reviewed_by=updated.reviewed_by,
            )
        )

    if not denied:
        raise HTTPException(status_code=400, detail="No enrollments could be denied")

    return denied


@router.post("/{enrollment_id}/approve", response_model=EnrollmentDetail)
async def approve_enrollment(enrollment_id: str, account=Depends(get_current_account)):
    db = get_database()
    enrollment_service = EnrollmentService(db)
    course_service = CourseService(db)
    audit_service = AuditLogService(db)

    enrollment = await enrollment_service.get_enrollment(enrollment_id)
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    if account['role'] == 'lecturer':
        lecturer = account['account']
        course = await course_service.get_course(enrollment.course_id)
        if not course or course.lecturer_id != lecturer.id:
            raise HTTPException(status_code=403, detail="Not authorized for this course")
        reviewer_id = lecturer.id
    elif account['role'] == 'admin':
        reviewer_id = account['account'].id
    else:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    updated = await enrollment_service.update_status(enrollment_id, EnrollmentStatus.approved, reviewer_id)
    if not updated:
        raise HTTPException(status_code=400, detail="Could not update enrollment")

    await audit_service.log_action(
        "enrollment_approved",
        reviewer_id,
        {"enrollment_id": enrollment_id, "course_id": enrollment.course_id},
    )

    return EnrollmentDetail(
        id=updated.id,
        student_id=updated.student_id,
        course_id=updated.course_id,
        status=updated.status,
        requested_at=updated.requested_at.isoformat(),
        reviewed_at=updated.reviewed_at.isoformat() if updated.reviewed_at else None,
        reviewed_by=updated.reviewed_by,
    )


@router.post("/{enrollment_id}/deny", response_model=EnrollmentDetail)
async def deny_enrollment(enrollment_id: str, account=Depends(get_current_account)):
    db = get_database()
    enrollment_service = EnrollmentService(db)
    course_service = CourseService(db)
    audit_service = AuditLogService(db)

    enrollment = await enrollment_service.get_enrollment(enrollment_id)
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    if account['role'] == 'lecturer':
        lecturer = account['account']
        course = await course_service.get_course(enrollment.course_id)
        if not course or course.lecturer_id != lecturer.id:
            raise HTTPException(status_code=403, detail="Not authorized for this course")
        reviewer_id = lecturer.id
    elif account['role'] == 'admin':
        reviewer_id = account['account'].id
    else:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    updated = await enrollment_service.update_status(enrollment_id, EnrollmentStatus.denied, reviewer_id)
    if not updated:
        raise HTTPException(status_code=400, detail="Could not update enrollment")

    await audit_service.log_action(
        "enrollment_denied",
        reviewer_id,
        {"enrollment_id": enrollment_id, "course_id": enrollment.course_id},
    )

    return EnrollmentDetail(
        id=updated.id,
        student_id=updated.student_id,
        course_id=updated.course_id,
        status=updated.status,
        requested_at=updated.requested_at.isoformat(),
        reviewed_at=updated.reviewed_at.isoformat() if updated.reviewed_at else None,
        reviewed_by=updated.reviewed_by,
    )


@router.get("", response_model=list)
async def list_enrollments(skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000),
                           admin=Depends(require_admin)):
    db = get_database()
    enrollment_service = EnrollmentService(db)
    enrollments = await enrollment_service.get_enrollments(skip=skip, limit=limit)
    return [
        EnrollmentDetail(
            id=enrollment.id,
            student_id=enrollment.student_id,
            course_id=enrollment.course_id,
            status=enrollment.status,
            requested_at=enrollment.requested_at.isoformat(),
            reviewed_at=enrollment.reviewed_at.isoformat() if enrollment.reviewed_at else None,
            reviewed_by=enrollment.reviewed_by,
        )
        for enrollment in enrollments
    ]
