from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.core.mongodb import get_database
from app.api.dependencies import get_current_account, require_admin

router = APIRouter(prefix="/api", tags=["Dashboard"])


class DashboardStats(BaseModel):
    total_students: int
    total_lecturers: int
    total_courses: int
    total_departments: int
    active_sessions: int


class DashboardSessionSummary(BaseModel):
    id: str
    course_id: str
    course_code: str | None
    course_title: str | None
    status: str
    start_time: str | None
    end_time: str | None


class LecturerDashboardStats(BaseModel):
    total_courses: int
    total_sessions: int
    active_sessions: int
    closed_sessions: int
    saved_reports: int
    pending_enrollments: int
    approved_students: int
    recent_sessions: list[DashboardSessionSummary]


@router.get("/dashboard", response_model=DashboardStats)
async def get_dashboard_stats(admin=Depends(require_admin)):
    """Get dashboard statistics (Admin only)"""
    db = get_database()
    
    total_students = await db.students.count_documents({})
    total_lecturers = await db.lecturers.count_documents({})
    total_courses = await db.courses.count_documents({})
    total_departments = await db.departments.count_documents({})
    active_sessions = await db.attendance_sessions.count_documents({"status": "open"})

    return DashboardStats(
        total_students=total_students,
        total_lecturers=total_lecturers,
        total_courses=total_courses,
        total_departments=total_departments,
        active_sessions=active_sessions,
    )


@router.get("/dashboard/lecturer", response_model=LecturerDashboardStats)
async def get_lecturer_dashboard(account=Depends(get_current_account)):
    if account["role"] != "lecturer":
        raise HTTPException(status_code=403, detail="Lecturer access required")

    user = account["account"]
    db = get_database()

    total_courses = await db.courses.count_documents({"lecturer_id": user.id})
    total_sessions = await db.attendance_sessions.count_documents({"lecturer_id": user.id})
    active_sessions = await db.attendance_sessions.count_documents({"lecturer_id": user.id, "status": "open"})
    closed_sessions = await db.attendance_sessions.count_documents({"lecturer_id": user.id, "status": "closed"})
    saved_reports = await db.attendance_reports.count_documents({"lecturer_id": user.id})

    courses = await db.courses.find({"lecturer_id": user.id}).to_list(length=1000)
    course_ids = [course["_id"] for course in courses]

    if course_ids:
        pending_enrollments = await db.enrollments.count_documents({"course_id": {"$in": course_ids}, "status": "pending"})
        approved_students = len(await db.enrollments.distinct("student_id", {"course_id": {"$in": course_ids}, "status": "approved"}))
    else:
        pending_enrollments = 0
        approved_students = 0

    raw_sessions = await db.attendance_sessions.find({"lecturer_id": user.id}).sort("start_time", -1).to_list(length=5)
    course_map = {course["_id"]: course for course in courses}

    recent_sessions = [
        DashboardSessionSummary(
            id=session["_id"],
            course_id=session["course_id"],
            course_code=course_map.get(session["course_id"], {}).get("code"),
            course_title=course_map.get(session["course_id"], {}).get("title"),
            status=session["status"],
            start_time=session["start_time"].isoformat() if session.get("start_time") else None,
            end_time=session["end_time"].isoformat() if session.get("end_time") else None,
        )
        for session in raw_sessions
    ]

    return LecturerDashboardStats(
        total_courses=total_courses,
        total_sessions=total_sessions,
        active_sessions=active_sessions,
        closed_sessions=closed_sessions,
        saved_reports=saved_reports,
        pending_enrollments=pending_enrollments,
        approved_students=approved_students,
        recent_sessions=recent_sessions,
    )
