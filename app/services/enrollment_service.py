from typing import Optional, List, TYPE_CHECKING
from datetime import datetime, timezone
from app.models.schemas import Enrollment, EnrollmentStatus
from app.utils.qr_generator import generate_uuid

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase


class EnrollmentService:
    """Service for enrollment management"""

    def __init__(self, db: 'AsyncIOMotorDatabase'):
        self.db = db
        self.collection = db.enrollments

    async def request_enrollment(self, student_id: str, course_id: str) -> Enrollment:
        existing = await self.collection.find_one({
            "student_id": student_id,
            "course_id": course_id,
        })
        if existing:
            existing["id"] = existing.pop("_id")
            return Enrollment(**existing)

        enrollment_data = {
            "_id": generate_uuid(),
            "student_id": student_id,
            "course_id": course_id,
            "status": EnrollmentStatus.pending,
            "requested_at": datetime.now(timezone.utc),
            "reviewed_at": None,
            "reviewed_by": None,
        }
        await self.collection.insert_one(enrollment_data)
        enrollment_data["id"] = enrollment_data.pop("_id")
        return Enrollment(**enrollment_data)

    async def get_enrollment(self, enrollment_id: str) -> Optional[Enrollment]:
        enrollment = await self.collection.find_one({"_id": enrollment_id})
        if enrollment:
            enrollment["id"] = enrollment.pop("_id")
            return Enrollment(**enrollment)
        return None

    async def get_enrollments(self, student_id: Optional[str] = None,
                              course_id: Optional[str] = None,
                              status: Optional[EnrollmentStatus] = None,
                              skip: int = 0, limit: int = 100) -> List[Enrollment]:
        query = {}
        if student_id:
            query["student_id"] = student_id
        if course_id:
            query["course_id"] = course_id
        if status:
            query["status"] = status

        cursor = self.collection.find(query).sort("requested_at", -1).skip(skip).limit(limit)
        enrollments = []
        async for enrollment in cursor:
            enrollment["id"] = enrollment.pop("_id")
            enrollments.append(Enrollment(**enrollment))
        return enrollments

    async def get_enrollments_by_courses(self, course_ids: List[str],
                                         status: Optional[EnrollmentStatus] = None,
                                         skip: int = 0, limit: int = 100) -> List[Enrollment]:
        if not course_ids:
            return []

        query = {"course_id": {"$in": course_ids}}
        if status:
            query["status"] = status

        cursor = self.collection.find(query).sort("requested_at", -1).skip(skip).limit(limit)
        enrollments = []
        async for enrollment in cursor:
            enrollment["id"] = enrollment.pop("_id")
            enrollments.append(Enrollment(**enrollment))
        return enrollments

    async def update_status(self, enrollment_id: str, status: EnrollmentStatus,
                            reviewed_by: str) -> Optional[Enrollment]:
        result = await self.collection.find_one_and_update(
            {"_id": enrollment_id},
            {"$set": {
                "status": status,
                "reviewed_at": datetime.now(timezone.utc),
                "reviewed_by": reviewed_by,
            }},
            return_document=True,
        )
        if result:
            result["id"] = result.pop("_id")
            return Enrollment(**result)
        return None
