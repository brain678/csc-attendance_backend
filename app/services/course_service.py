from typing import Optional, List, TYPE_CHECKING
from datetime import datetime, timezone
from app.models.schemas import Course
from app.utils.qr_generator import generate_uuid

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase


class CourseService:
    """Service for course management"""

    def __init__(self, db: 'AsyncIOMotorDatabase'):
        self.db = db
        self.collection = db.courses

    async def create_course(self, code: str, title: str, description: Optional[str] = None,
                            department_id: Optional[str] = None,
                            lecturer_id: Optional[str] = None) -> Course:
        code_normalized = code.strip().upper()
        course_data = {
            "_id": generate_uuid(),
            "code": code_normalized,
            "title": title.strip(),
            "description": description.strip() if description else None,
            "department_id": department_id,
            "lecturer_id": lecturer_id,
            "created_at": datetime.now(timezone.utc),
        }
        await self.collection.insert_one(course_data)
        course_data["id"] = course_data.pop("_id")
        return Course(**course_data)

    async def get_course(self, course_id: str) -> Optional[Course]:
        course = await self.collection.find_one({"_id": course_id})
        if course:
            course["id"] = course.pop("_id")
            return Course(**course)
        return None

    async def get_course_by_code(self, code: str) -> Optional[Course]:
        code_normalized = code.strip().upper()
        course = await self.collection.find_one({"code": code_normalized})
        if course:
            course["id"] = course.pop("_id")
            return Course(**course)
        return None

    async def get_courses(self, skip: int = 0, limit: int = 100,
                          department_id: Optional[str] = None,
                          lecturer_id: Optional[str] = None) -> List[Course]:
        query = {}
        if department_id:
            query["department_id"] = department_id
        if lecturer_id:
            query["lecturer_id"] = lecturer_id

        cursor = self.collection.find(query).sort("code", 1).skip(skip).limit(limit)
        courses = []
        async for course in cursor:
            course["id"] = course.pop("_id")
            courses.append(Course(**course))
        return courses

    async def update_course(self, course_id: str, code: Optional[str] = None,
                            title: Optional[str] = None, description: Optional[str] = None,
                            department_id: Optional[str] = None,
                            lecturer_id: Optional[str] = None) -> Optional[Course]:
        update_data = {}
        if code is not None:
            update_data["code"] = code.strip().upper()
        if title is not None:
            update_data["title"] = title.strip()
        if description is not None:
            update_data["description"] = description.strip() if description else None
        if department_id is not None:
            update_data["department_id"] = department_id
        if lecturer_id is not None:
            update_data["lecturer_id"] = lecturer_id

        if not update_data:
            return await self.get_course(course_id)

        result = await self.collection.find_one_and_update(
            {"_id": course_id},
            {"$set": update_data},
            return_document=True,
        )
        if result:
            result["id"] = result.pop("_id")
            return Course(**result)
        return None

    async def delete_course(self, course_id: str) -> bool:
        result = await self.collection.delete_one({"_id": course_id})
        return result.deleted_count > 0
