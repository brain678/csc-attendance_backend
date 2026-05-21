from typing import Optional, List, TYPE_CHECKING
from datetime import datetime, timezone
from app.utils.qr_generator import generate_uuid

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase


class ReportService:
    """Service for saved attendance session reports"""

    def __init__(self, db: 'AsyncIOMotorDatabase'):
        self.db = db
        self.collection = db.attendance_reports

    async def create_session_report(self, session: dict, records: list[dict]) -> dict:
        report_id = generate_uuid()
        now = datetime.now(timezone.utc)

        present_count = sum(1 for record in records if record.get("status") == "present")
        approved_count = await self.db.enrollments.count_documents({
            "course_id": session["course_id"],
            "status": "approved",
        })

        report_doc = {
            "_id": report_id,
            "session_id": session["id"],
            "course_id": session["course_id"],
            "course_code": session.get("course_code"),
            "course_title": session.get("course_title"),
            "lecturer_id": session["lecturer_id"],
            "generated_at": now,
            "records": records,
            "present_count": present_count,
            "total_count": approved_count,
            "absent_count": max(0, approved_count - present_count),
        }

        await self.collection.insert_one(report_doc)
        report_doc["id"] = report_doc.pop("_id")
        return report_doc

    async def get_reports(self, lecturer_id: Optional[str] = None,
                          skip: int = 0, limit: int = 100) -> List[dict]:
        query = {}
        if lecturer_id:
            query["lecturer_id"] = lecturer_id

        cursor = self.collection.find(query, {"records": 0}).sort("generated_at", -1).skip(skip).limit(limit)
        reports = []
        async for doc in cursor:
            doc["id"] = doc.pop("_id")
            reports.append(doc)
        return reports

    async def get_report(self, report_id: str) -> Optional[dict]:
        report = await self.collection.find_one({"_id": report_id})
        if report:
            report["id"] = report.pop("_id")
            return report
        return None

    async def build_session_report_records(self, session_id: str) -> List[dict]:
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
                "$lookup": {
                    "from": "courses",
                    "localField": "course_id",
                    "foreignField": "_id",
                    "as": "course",
                }
            },
            {"$unwind": {"path": "$course", "preserveNullAndEmptyArrays": True}},
            {
                "$project": {
                    "record_id": "$_id",
                    "session_id": 1,
                    "course_id": 1,
                    "student_id": 1,
                    "status": 1,
                    "marked_at": 1,
                    "method": 1,
                    "student_name": "$student.full_name",
                    "student_matric": "$student.matric_number",
                    "course_code": "$course.code",
                    "course_title": "$course.title",
                }
            },
            {"$sort": {"marked_at": -1}},
        ]

        cursor = self.db.attendance_records.aggregate(pipeline)
        results = []
        async for record in cursor:
            record["record_id"] = str(record["record_id"])
            results.append(record)
        return results
