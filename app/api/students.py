from fastapi import APIRouter, Depends, HTTPException, status, Query
from datetime import timedelta
from app.core.config import settings
from app.core.mongodb import get_database
from app.core.security import create_access_token
from app.services.student_service import StudentService
from app.services.course_service import CourseService
from app.services.enrollment_service import EnrollmentService
from app.services.department_service import DepartmentService
from app.services.audit_service import AuditLogService
from app.models.requests import StudentRegister, StudentLogin, StudentUpdate, StudentResponse, StudentDetailResponse, TokenResponse
from app.models.schemas import StudentStatus, EnrollmentStatus
from app.api.dependencies import require_admin, get_current_student

router = APIRouter(prefix="/api/students", tags=["Students"])


@router.post("/register", response_model=StudentResponse, status_code=status.HTTP_201_CREATED)
async def register_student(payload: StudentRegister):
    db = get_database()
    student_service = StudentService(db)

    existing_email = await student_service.get_student_by_email(payload.email)
    if existing_email:
        raise HTTPException(status_code=400, detail="Email already registered")

    existing_matric = await student_service.get_student_by_matric(payload.matric_number)
    if existing_matric:
        raise HTTPException(status_code=400, detail="Matric number already registered")

    student = await student_service.create_student(
        payload.full_name,
        payload.email,
        payload.matric_number,
        payload.department_id,
        payload.password,
        status=StudentStatus.pending,
    )

    if payload.course_codes:
        course_service = CourseService(db)
        enrollment_service = EnrollmentService(db)
        for course_code in payload.course_codes:
            course = await course_service.get_course_by_code(course_code)
            if course:
                await enrollment_service.request_enrollment(student.id, course.id)

    return StudentResponse(
        id=student.id,
        full_name=student.full_name,
        email=student.email,
        matric_number=student.matric_number,
        department_id=student.department_id,
        status=student.status,
        created_at=student.created_at.isoformat(),
    )


@router.post("/login", response_model=TokenResponse)
async def login_student(payload: StudentLogin):
    db = get_database()
    student_service = StudentService(db)

    student = await student_service.authenticate_student(
        payload.email,
        payload.matric_number,
        payload.password,
    )

    if not student:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if student.status == StudentStatus.pending:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Student registration is pending admin approval")
    if student.status == StudentStatus.suspended:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Student account suspended")

    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": student.id, "role": "student", "name": student.full_name},
        expires_delta=access_token_expires,
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": student.id,
        "role": "student",
        "name": student.full_name,
    }


@router.get("/me", response_model=StudentResponse)
async def get_current_student_profile(student=Depends(get_current_student)):
    db = get_database()
    enrollment_service = EnrollmentService(db)
    course_service = CourseService(db)

    approved_enrollments = await enrollment_service.get_enrollments(
        student_id=student.id,
        status=EnrollmentStatus.approved,
    )
    course_codes = []
    for enrollment in approved_enrollments:
        course = await course_service.get_course(enrollment.course_id)
        if course and course.code:
            course_codes.append(course.code)

    return StudentResponse(
        id=student.id,
        full_name=student.full_name,
        email=student.email,
        matric_number=student.matric_number,
        department_id=student.department_id,
        status=student.status,
        created_at=student.created_at.isoformat(),
        course_codes=course_codes,
    )


@router.get("", response_model=list)
async def list_students(skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000),
                        admin=Depends(require_admin)):
    db = get_database()
    student_service = StudentService(db)
    students = await student_service.get_all_students(skip, limit)
    return [
        StudentResponse(
            id=student.id,
            full_name=student.full_name,
            email=student.email,
            matric_number=student.matric_number,
            department_id=student.department_id,
            status=student.status,
            created_at=student.created_at.isoformat(),
        )
        for student in students
    ]


@router.get("/{student_id}", response_model=StudentResponse)
async def get_student(student_id: str, admin=Depends(require_admin)):
    db = get_database()
    student_service = StudentService(db)
    student = await student_service.get_student(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    return StudentResponse(
        id=student.id,
        full_name=student.full_name,
        email=student.email,
        matric_number=student.matric_number,
        department_id=student.department_id,
        status=student.status,
        created_at=student.created_at.isoformat(),
    )


@router.get("/{student_id}/details", response_model=StudentDetailResponse)
async def get_student_details(student_id: str, admin=Depends(require_admin)):
    db = get_database()
    student_service = StudentService(db)
    department_service = DepartmentService(db)
    enrollment_service = EnrollmentService(db)
    course_service = CourseService(db)

    student = await student_service.get_student(student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    department_name = None
    if student.department_id:
        department = await department_service.get_department(student.department_id)
        if department:
            department_name = department.name

    enrollments = await enrollment_service.get_enrollments(student_id=student.id)
    enrollment_details = []
    course_codes = []
    for enrollment in enrollments:
        course = await course_service.get_course(enrollment.course_id)
        course_code = course.code if course else enrollment.course_id
        course_title = course.title if course else ''
        if course_code:
            course_codes.append(course_code)
        enrollment_details.append(
            {
                'id': enrollment.id,
                'student_id': enrollment.student_id,
                'course_id': enrollment.course_id,
                'course_code': course_code,
                'course_title': course_title,
                'status': enrollment.status,
                'requested_at': enrollment.requested_at.isoformat(),
                'reviewed_at': enrollment.reviewed_at.isoformat() if enrollment.reviewed_at else None,
                'reviewed_by': enrollment.reviewed_by,
            }
        )

    return StudentDetailResponse(
        id=student.id,
        full_name=student.full_name,
        email=student.email,
        matric_number=student.matric_number,
        department_id=student.department_id,
        department_name=department_name,
        status=student.status,
        created_at=student.created_at.isoformat(),
        course_codes=course_codes,
        enrollments=enrollment_details,
    )


@router.put("/{student_id}", response_model=StudentResponse)
async def update_student(student_id: str, payload: StudentUpdate, admin=Depends(require_admin)):
    db = get_database()
    student_service = StudentService(db)
    audit_service = AuditLogService(db)

    if payload.email:
        existing = await student_service.get_student_by_email(payload.email)
        if existing and existing.id != student_id:
            raise HTTPException(status_code=400, detail="Email already registered")

    if payload.matric_number:
        existing = await student_service.get_student_by_matric(payload.matric_number)
        if existing and existing.id != student_id:
            raise HTTPException(status_code=400, detail="Matric number already registered")

    student = await student_service.update_student(
        student_id,
        full_name=payload.full_name,
        email=payload.email,
        matric_number=payload.matric_number,
        department_id=payload.department_id,
        status=payload.status,
    )
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    await audit_service.log_action(
        "student_updated",
        admin.id,
        {"student_id": student_id},
    )

    return StudentResponse(
        id=student.id,
        full_name=student.full_name,
        email=student.email,
        matric_number=student.matric_number,
        department_id=student.department_id,
        status=student.status,
        created_at=student.created_at.isoformat(),
    )


@router.delete("/{student_id}")
async def delete_student(student_id: str, admin=Depends(require_admin)):
    db = get_database()
    student_service = StudentService(db)
    audit_service = AuditLogService(db)

    success = await student_service.delete_student(student_id)
    if not success:
        raise HTTPException(status_code=404, detail="Student not found")

    await audit_service.log_action(
        "student_deleted",
        admin.id,
        {"student_id": student_id},
    )

    return {"message": "Student deleted"}
