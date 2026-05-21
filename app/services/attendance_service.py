from typing import Optional, List, TYPE_CHECKING
from datetime import datetime, timezone
from pymongo.errors import DuplicateKeyError
from app.models.schemas import AttendanceRecord, AttendanceStatus
from app.utils.qr_generator import generate_uuid

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase


class AttendanceService:
    """Service for attendance records"""

    def __init__(self, db: 'AsyncIOMotorDatabase'):
        self.db = db
        self.collection = db.attendance_records

    async def record_attendance(self, session_id: str, student_id: str, course_id: str,
                                status: AttendanceStatus = AttendanceStatus.present,
                                method: str = "qr", recorded_by: Optional[str] = None) -> AttendanceRecord:
        existing = await self.collection.find_one({
            "session_id": session_id,
            "student_id": student_id,
        })
        if existing:
            existing["id"] = existing.pop("_id")
            return AttendanceRecord(**existing)

        record_data = {
            "_id": generate_uuid(),
            "session_id": session_id,
            "student_id": student_id,
            "course_id": course_id,
            "status": status,
            "marked_at": datetime.now(timezone.utc),
            "method": method,
            "recorded_by": recorded_by,
        }
        try:
            await self.collection.insert_one(record_data)
        except DuplicateKeyError:
            existing = await self.collection.find_one({
                "session_id": session_id,
                "student_id": student_id,
            })
            if existing:
                existing["id"] = existing.pop("_id")
                return AttendanceRecord(**existing)
            raise
        record_data["id"] = record_data.pop("_id")
        return AttendanceRecord(**record_data)

    async def get_session_records(self, session_id: str) -> List[AttendanceRecord]:
        cursor = self.collection.find({"session_id": session_id}).sort("marked_at", 1)
        records = []
        async for record in cursor:
            record["id"] = record.pop("_id")
            records.append(AttendanceRecord(**record))
        return records

    async def get_student_records(self, student_id: str) -> List[AttendanceRecord]:
        cursor = self.collection.find({"student_id": student_id}).sort("marked_at", -1)
        records = []
        async for record in cursor:
            record["id"] = record.pop("_id")
            records.append(AttendanceRecord(**record))
        return records

    async def mark_absences(self, session_id: str, course_id: str,
                            student_ids: List[str], recorded_by: Optional[str] = None) -> int:
        if not student_ids:
            return 0

        existing_ids = await self.collection.distinct(
            "student_id",
            {"session_id": session_id, "student_id": {"$in": student_ids}},
        )
        missing_ids = [student_id for student_id in student_ids if student_id not in set(existing_ids)]
        if not missing_ids:
            return 0

        now = datetime.now(timezone.utc)
        records = [
            {
                "_id": generate_uuid(),
                "session_id": session_id,
                "student_id": student_id,
                "course_id": course_id,
                "status": AttendanceStatus.absent,
                "marked_at": now,
                "method": "system",
                "recorded_by": recorded_by,
            }
            for student_id in missing_ids
        ]
        await self.collection.insert_many(records)
        return len(records)

    async def get_report(self, course_id: Optional[str] = None,
                         student_id: Optional[str] = None,
                         lecturer_id: Optional[str] = None,
                         start_date: Optional[datetime] = None,
                         end_date: Optional[datetime] = None) -> List[dict]:
        match = {}
        if course_id:
            match["course_id"] = course_id
        if student_id:
            match["student_id"] = student_id
        if start_date or end_date:
            date_query = {}
            if start_date:
                date_query["$gte"] = start_date
            if end_date:
                date_query["$lte"] = end_date
            match["marked_at"] = date_query

        pipeline = [
            {"$match": match},
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
                "$lookup": {
                    "from": "attendance_sessions",
                    "localField": "session_id",
                    "foreignField": "_id",
                    "as": "session",
                }
            },
            {"$unwind": {"path": "$session", "preserveNullAndEmptyArrays": True}},
        ]

        if lecturer_id:
            pipeline.append({"$match": {"session.lecturer_id": lecturer_id}})

        pipeline.extend([
            {
                "$project": {
                    "record_id": "$_id",
                    "session_id": 1,
                    "course_id": 1,
                    "student_id": 1,
                    "status": 1,
                    "marked_at": 1,
                    "student_name": "$student.full_name",
                    "student_matric": "$student.matric_number",
                    "course_code": "$course.code",
                    "course_title": "$course.title",
                    "session_start": "$session.start_time",
                    "session_end": "$session.end_time",
                    "lecturer_id": "$session.lecturer_id",
                }
            },
            {"$sort": {"marked_at": -1}},
        ])

        cursor = self.collection.aggregate(pipeline)
        results = []
        async for record in cursor:
            results.append(record)
        return results
