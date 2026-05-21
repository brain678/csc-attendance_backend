from fastapi import APIRouter, Depends, HTTPException, status, Query
from datetime import datetime, timezone
from app.core.mongodb import get_database
from app.services.attendance_session_service import AttendanceSessionService
from app.services.attendance_service import AttendanceService
from app.services.course_service import CourseService
from app.services.enrollment_service import EnrollmentService
from app.services.audit_service import AuditLogService
from app.services.report_service import ReportService
from app.models.requests import AttendanceSessionCreate, AttendanceSessionResponse, AttendanceSessionQRResponse
from app.models.schemas import EnrollmentStatus, AttendanceSessionStatus
from app.api.dependencies import get_current_account
from app.utils.qr_generator import generate_qr_code
import base64

router = APIRouter(prefix="/api/attendance-sessions", tags=["Attendance Sessions"])

MIN_DURATION_MINUTES = 1
MAX_DURATION_MINUTES = 180


def ensure_timestamp(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def is_expired(session) -> bool:
    if session.status != AttendanceSessionStatus.open:
        return False
    end_time = session.end_time
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) > end_time


async def close_session_and_mark_absences(db, session):
    session_service = AttendanceSessionService(db)
    enrollment_service = EnrollmentService(db)
    attendance_service = AttendanceService(db)

    closed = await session_service.close_session(session.id)
    if not closed:
        return session

    if not closed.absences_marked:
        enrollments = await enrollment_service.get_enrollments(
            course_id=closed.course_id,
            status=None,
            skip=0,
            limit=5000,
        )
        approved_students = [e.student_id for e in enrollments if e.status == EnrollmentStatus.approved]
        if approved_students:
            await attendance_service.mark_absences(
                closed.id,
                closed.course_id,
                approved_students,
                recorded_by="system_auto_close",
            )
        await session_service.mark_absences_completed(closed.id)

    return closed


@router.post("", response_model=AttendanceSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(payload: AttendanceSessionCreate, account=Depends(get_current_account)):
    role = account["role"]
    user = account["account"]
    if role != "lecturer":
        raise HTTPException(status_code=403, detail="Lecturer access required")

    if payload.duration_minutes < MIN_DURATION_MINUTES or payload.duration_minutes > MAX_DURATION_MINUTES:
        raise HTTPException(status_code=400, detail="Duration must be between 1 and 180 minutes")

    start_time = None
    if payload.start_time:
        try:
            start_time = datetime.fromisoformat(payload.start_time.replace('Z', '+00:00'))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_time format")
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        else:
            start_time = start_time.astimezone(timezone.utc)
        if start_time < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="Start time must be in the future")

    db = get_database()
    course_service = CourseService(db)
    session_service = AttendanceSessionService(db)
    audit_service = AuditLogService(db)

    course = await course_service.get_course(payload.course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    if course.lecturer_id != user.id:
        raise HTTPException(status_code=403, detail="Course not assigned to lecturer")

    session = await session_service.create_session(
        course_id=payload.course_id,
        lecturer_id=user.id,
        duration_minutes=payload.duration_minutes,
        start_time=start_time,
    )

    await audit_service.log_action(
        "attendance_session_created",
        user.id,
        {"session_id": session.id, "course_id": session.course_id},
    )

    return AttendanceSessionResponse(
        id=session.id,
        course_id=session.course_id,
        lecturer_id=session.lecturer_id,
        qr_token=session.qr_token,
        duration_minutes=session.duration_minutes,
        start_time=ensure_timestamp(session.start_time),
        end_time=ensure_timestamp(session.end_time),
        status=session.status,
        created_at=ensure_timestamp(session.created_at),
        closed_at=ensure_timestamp(session.closed_at),
    )


@router.get("", response_model=list)
async def list_sessions(skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000),
                        course_id: str | None = None, account=Depends(get_current_account)):
    role = account["role"]
    user = account["account"]

    db = get_database()
    session_service = AttendanceSessionService(db)

    if role == "student":
        enrollment_service = EnrollmentService(db)
        enrollments = await enrollment_service.get_enrollments(
            student_id=user.id,
            status=EnrollmentStatus.approved,
            skip=0,
            limit=1000,
        )
        course_ids = [enrollment.course_id for enrollment in enrollments]
        if not course_ids:
            return []

        if course_id and course_id not in course_ids:
            return []

        sessions = await session_service.get_sessions_by_course_ids(
            course_ids,
            skip=skip,
            limit=limit,
            status=AttendanceSessionStatus.open,
        )
    elif role == "lecturer":
        sessions = await session_service.get_sessions(skip, limit, course_id, user.id)
    elif role == "admin":
        sessions = await session_service.get_sessions(skip, limit, course_id)
    else:
        raise HTTPException(status_code=403, detail="Access denied")

    return [
        AttendanceSessionResponse(
            id=session.id,
            course_id=session.course_id,
            lecturer_id=session.lecturer_id,
            qr_token=session.qr_token,
            duration_minutes=session.duration_minutes,
            start_time=ensure_timestamp(session.start_time),
            end_time=ensure_timestamp(session.end_time),
            status=session.status,
            created_at=ensure_timestamp(session.created_at),
            closed_at=ensure_timestamp(session.closed_at),
        )
        for session in sessions
    ]


@router.get("/{session_id}", response_model=AttendanceSessionResponse)
async def get_session(session_id: str, account=Depends(get_current_account)):
    role = account["role"]
    user = account["account"]
    if role not in ["admin", "lecturer", "student"]:
        raise HTTPException(status_code=403, detail="Access denied")

    db = get_database()
    session_service = AttendanceSessionService(db)
    session = await session_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if role == "lecturer" and session.lecturer_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this session")

    if role == "student":
        enrollment_service = EnrollmentService(db)
        enrollments = await enrollment_service.get_enrollments(
            student_id=user.id,
            course_id=session.course_id,
            status=EnrollmentStatus.approved,
            skip=0,
            limit=1,
        )
        if not enrollments or session.status != AttendanceSessionStatus.open:
            raise HTTPException(status_code=403, detail="Not authorized for this session")

    if is_expired(session):
        session = await close_session_and_mark_absences(db, session)

    return AttendanceSessionResponse(
        id=session.id,
        course_id=session.course_id,
        lecturer_id=session.lecturer_id,
        qr_token=session.qr_token,
        duration_minutes=session.duration_minutes,
        start_time=ensure_timestamp(session.start_time),
        end_time=ensure_timestamp(session.end_time),
        status=session.status,
        created_at=ensure_timestamp(session.created_at),
        closed_at=ensure_timestamp(session.closed_at),
    )


@router.get("/{session_id}/qr", response_model=AttendanceSessionQRResponse)
async def get_session_qr(session_id: str, account=Depends(get_current_account)):
    role = account["role"]
    user = account["account"]
    if role not in ["admin", "lecturer"]:
        raise HTTPException(status_code=403, detail="Access denied")

    db = get_database()
    session_service = AttendanceSessionService(db)
    session = await session_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if role == "lecturer" and session.lecturer_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this session")

    qr_image = generate_qr_code(session.qr_token)
    qr_base64 = base64.b64encode(qr_image).decode("utf-8")

    return AttendanceSessionQRResponse(qr_token=session.qr_token, qr_code_data=qr_base64)


@router.post("/{session_id}/close", response_model=AttendanceSessionResponse)
async def close_session(session_id: str, account=Depends(get_current_account)):
    role = account["role"]
    user = account["account"]
    if role not in ["admin", "lecturer"]:
        raise HTTPException(status_code=403, detail="Access denied")

    db = get_database()
    session_service = AttendanceSessionService(db)
    audit_service = AuditLogService(db)

    session = await session_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if role == "lecturer" and session.lecturer_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this session")

    closed = await close_session_and_mark_absences(db, session)

    try:
        course_service = CourseService(db)
        report_service = ReportService(db)
        course = await course_service.get_course(closed.course_id)
        closed_data = closed.dict()
        if course:
            closed_data["course_code"] = course.code
            closed_data["course_title"] = course.title

        report_records = await report_service.build_session_report_records(closed.id)
        await report_service.create_session_report(closed_data, report_records)
    except Exception:
        # If report save fails, still close the session
        pass

    await audit_service.log_action(
        "attendance_session_closed",
        user.id,
        {"session_id": session_id},
    )

    return AttendanceSessionResponse(
        id=closed.id,
        course_id=closed.course_id,
        lecturer_id=closed.lecturer_id,
        qr_token=closed.qr_token,
        duration_minutes=closed.duration_minutes,
        start_time=ensure_timestamp(closed.start_time),
        end_time=ensure_timestamp(closed.end_time),
        status=closed.status,
        created_at=ensure_timestamp(closed.created_at),
        closed_at=ensure_timestamp(closed.closed_at),
    )
