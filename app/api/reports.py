from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime
from app.core.mongodb import get_database
from app.services.attendance_service import AttendanceService
from app.services.report_service import ReportService
from app.api.dependencies import get_current_account

router = APIRouter(prefix="/api/reports", tags=["Reports"])


@router.get("/attendance", response_model=list)
async def attendance_report(
    course_id: str | None = None,
    student_id: str | None = None,
    lecturer_id: str | None = None,
    start_date: str | None = Query(None, description="YYYY-MM-DD"),
    end_date: str | None = Query(None, description="YYYY-MM-DD"),
    account=Depends(get_current_account),
):
    role = account["role"]
    user = account["account"]
    if role not in ["admin", "lecturer"]:
        raise HTTPException(status_code=403, detail="Access denied")

    db = get_database()
    attendance_service = AttendanceService(db)

    start_datetime = None
    end_datetime = None
    try:
        if start_date:
            start_datetime = datetime.fromisoformat(start_date)
        if end_date:
            end_datetime = datetime.fromisoformat(end_date)
            end_datetime = end_datetime.replace(hour=23, minute=59, second=59)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {exc}")

    report = await attendance_service.get_report(
        course_id=course_id,
        student_id=student_id,
        lecturer_id=user.id if role == "lecturer" else lecturer_id,
        start_date=start_datetime,
        end_date=end_datetime,
    )

    return report


@router.get("/saved")
async def saved_session_reports(
    course_id: str | None = None,
    lecturer_id: str | None = None,
    session_id: str | None = None,
    account=Depends(get_current_account),
):
    role = account["role"]
    user = account["account"]

    if role not in ["admin", "lecturer"]:
        raise HTTPException(status_code=403, detail="Access denied")

    db = get_database()
    report_service = ReportService(db)

    if role == "lecturer":
        lecturer_id = user.id

    reports = await report_service.get_reports(lecturer_id=lecturer_id, skip=0, limit=100)
    return reports


@router.get("/saved/{report_id}")
async def get_saved_report(report_id: str, account=Depends(get_current_account)):
    role = account["role"]
    user = account["account"]

    if role not in ["admin", "lecturer"]:
        raise HTTPException(status_code=403, detail="Access denied")

    db = get_database()
    report_service = ReportService(db)
    report = await report_service.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    if role == "lecturer" and report.get("lecturer_id") != user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this report")

    return report
