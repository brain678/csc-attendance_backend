from typing import Optional, List, TYPE_CHECKING
from datetime import datetime, timezone
from app.models.schemas import Lecturer, LecturerStatus
from app.core.security import get_password_hash, verify_password
from app.utils.qr_generator import generate_uuid

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase


class LecturerService:
    """Service for lecturer management"""

    def __init__(self, db: 'AsyncIOMotorDatabase'):
        self.db = db
        self.collection = db.lecturers

    async def create_lecturer(self, full_name: str, email: str, department_id: Optional[str],
                              password: str) -> Lecturer:
        lecturer_data = {
            "_id": generate_uuid(),
            "full_name": full_name.strip(),
            "email": email.strip().lower(),
            "department_id": department_id,
            "password_hash": get_password_hash(password),
            "status": LecturerStatus.active,
            "created_at": datetime.now(timezone.utc),
        }
        await self.collection.insert_one(lecturer_data)
        lecturer_data["id"] = lecturer_data.pop("_id")
        return Lecturer(**lecturer_data)

    async def get_lecturer(self, lecturer_id: str) -> Optional[Lecturer]:
        lecturer = await self.collection.find_one({"_id": lecturer_id})
        if lecturer:
            lecturer["id"] = lecturer.pop("_id")
            return Lecturer(**lecturer)
        return None

    async def get_lecturer_by_email(self, email: str) -> Optional[Lecturer]:
        lecturer = await self.collection.find_one({"email": email.strip().lower()})
        if lecturer:
            lecturer["id"] = lecturer.pop("_id")
            return Lecturer(**lecturer)
        return None

    async def get_all_lecturers(self, skip: int = 0, limit: int = 100) -> List[Lecturer]:
        cursor = self.collection.find().sort("full_name", 1).skip(skip).limit(limit)
        lecturers = []
        async for lecturer in cursor:
            lecturer["id"] = lecturer.pop("_id")
            lecturers.append(Lecturer(**lecturer))
        return lecturers

    async def authenticate_lecturer(self, email: str, password: str) -> Optional[Lecturer]:
        lecturer = await self.get_lecturer_by_email(email)
        if lecturer and verify_password(password, lecturer.password_hash):
            return lecturer
        return None

    async def update_lecturer(self, lecturer_id: str, full_name: Optional[str] = None,
                              department_id: Optional[str] = None,
                              status: Optional[LecturerStatus] = None) -> Optional[Lecturer]:
        update_data = {}
        if full_name is not None:
            update_data["full_name"] = full_name.strip()
        if department_id is not None:
            update_data["department_id"] = department_id
        if status is not None:
            update_data["status"] = status

        if not update_data:
            return await self.get_lecturer(lecturer_id)

        result = await self.collection.find_one_and_update(
            {"_id": lecturer_id},
            {"$set": update_data},
            return_document=True,
        )
        if result:
            result["id"] = result.pop("_id")
            return Lecturer(**result)
        return None

    async def delete_lecturer(self, lecturer_id: str) -> bool:
        result = await self.collection.delete_one({"_id": lecturer_id})
        return result.deleted_count > 0

    async def change_password(self, lecturer_id: str, new_password: str) -> Optional[Lecturer]:
        result = await self.collection.find_one_and_update(
            {"_id": lecturer_id},
            {"$set": {"password_hash": get_password_hash(new_password)}},
            return_document=True,
        )
        if result:
            result["id"] = result.pop("_id")
            return Lecturer(**result)
        return None
