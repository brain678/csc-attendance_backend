from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime, timezone
from app.core.mongodb import get_database
from app.services.attendance_session_service import AttendanceSessionService
from app.services.attendance_service import AttendanceService
from app.services.enrollment_service import EnrollmentService
from app.services.audit_service import AuditLogService
from app.models.requests import AttendanceMarkRequest, AttendanceRecordResponse, LiveAttendanceRecordResponse
from app.models.schemas import AttendanceSessionStatus, EnrollmentStatus
from app.api.dependencies import get_current_student, get_current_account

router = APIRouter(prefix="/api/attendance", tags=["Attendance"])


def ensure_timestamp(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def is_session_expired(session) -> bool:
    end_time = session.end_time
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) > end_time


async def close_and_mark_absences(db, session):
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


@router.post("/mark", response_model=AttendanceRecordResponse, status_code=status.HTTP_201_CREATED)
async def mark_attendance(payload: AttendanceMarkRequest, student=Depends(get_current_student)):
    db = get_database()
    session_service = AttendanceSessionService(db)
    enrollment_service = EnrollmentService(db)
    attendance_service = AttendanceService(db)
    audit_service = AuditLogService(db)

    session = await session_service.get_session_by_token(payload.qr_token)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status != AttendanceSessionStatus.open or is_session_expired(session):
        await close_and_mark_absences(db, session)
        raise HTTPException(status_code=400, detail="Session is closed")

    enrollments = await enrollment_service.get_enrollments(
        student_id=student.id,
        course_id=session.course_id,
        status=EnrollmentStatus.approved,
        skip=0,
        limit=1,
    )
    if not enrollments:
        raise HTTPException(status_code=403, detail="Enrollment not approved")

    record = await attendance_service.record_attendance(
        session_id=session.id,
        student_id=student.id,
        course_id=session.course_id,
        recorded_by=student.id,
    )

    await audit_service.log_action(
        "attendance_marked",
        student.id,
        {"session_id": session.id, "course_id": session.course_id},
    )

    return AttendanceRecordResponse(
        id=record.id,
        session_id=record.session_id,
        student_id=record.student_id,
        course_id=record.course_id,
        status=record.status,
        marked_at=ensure_timestamp(record.marked_at),
        method=record.method,
    )


@router.get("/session/{session_id}", response_model=list)
async def get_session_attendance(session_id: str, account=Depends(get_current_account)):
    role = account["role"]
    user = account["account"]
    if role not in ["admin", "lecturer"]:
        raise HTTPException(status_code=403, detail="Access denied")

    db = get_database()
    session_service = AttendanceSessionService(db)
    attendance_service = AttendanceService(db)

    session = await session_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if role == "lecturer" and session.lecturer_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this session")

    pipeline = [
        {"$match": {"session_id": session_id}},
        {
            "$lookup": {
                "from": "students",
                "localField": "student_id",
                "foreignField": "_id",
                "as": "student",
            }
        },
        {"$unwind": {"path": "$student", "preserveNullAndEmptyArrays": True}},
        {
            "$project": {
                "id": "$_id",
                "session_id": 1,
                "student_id": 1,
                "student_name": "$student.full_name",
                "student_matric": "$student.matric_number",
                "course_id": 1,
                "status": 1,
                "marked_at": 1,
                "method": 1,
            }
        },
        {"$sort": {"marked_at": 1}},
    ]

    cursor = db.attendance_records.aggregate(pipeline)
    records = []
    async for record in cursor:
        record["id"] = str(record["id"])
        records.append(record)

    return [
        LiveAttendanceRecordResponse(
            id=record["id"],
            session_id=record["session_id"],
            student_id=record["student_id"],
            student_name=record.get("student_name"),
            student_matric=record.get("student_matric"),
            course_id=record["course_id"],
            status=record["status"],
            marked_at=ensure_timestamp(record["marked_at"]),
            method=record["method"],
        )
        for record in records
    ]


@router.get("/me", response_model=list)
async def get_my_attendance(student=Depends(get_current_student)):
    db = get_database()
    attendance_service = AttendanceService(db)
    records = await attendance_service.get_student_records(student.id)
    return [
        AttendanceRecordResponse(
            id=record.id,
            session_id=record.session_id,
            student_id=record.student_id,
            course_id=record.course_id,
            status=record.status,
            marked_at=ensure_timestamp(record.marked_at),
            method=record.method,
        )
        for record in records
    ]
