from typing import Optional, List, TYPE_CHECKING
from datetime import datetime, timezone
from app.models.schemas import Department
from app.utils.qr_generator import generate_uuid

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase


class DepartmentService:
    """Service for department management"""

    def __init__(self, db: 'AsyncIOMotorDatabase'):
        self.db = db
        self.collection = db.departments

    async def create_department(self, name: str, code: str) -> Department:
        code_normalized = code.strip().upper()
        department_data = {
            "_id": generate_uuid(),
            "name": name.strip(),
            "code": code_normalized,
            "created_at": datetime.now(timezone.utc),
        }
        await self.collection.insert_one(department_data)
        department_data["id"] = department_data.pop("_id")
        return Department(**department_data)

    async def get_department(self, department_id: str) -> Optional[Department]:
        department = await self.collection.find_one({"_id": department_id})
        if department:
            department["id"] = department.pop("_id")
            return Department(**department)
        return None

    async def get_department_by_code(self, code: str) -> Optional[Department]:
        code_normalized = code.strip().upper()
        department = await self.collection.find_one({"code": code_normalized})
        if department:
            department["id"] = department.pop("_id")
            return Department(**department)
        return None

    async def get_all_departments(self, skip: int = 0, limit: int = 100) -> List[Department]:
        cursor = self.collection.find().sort("name", 1).skip(skip).limit(limit)
        departments = []
        async for department in cursor:
            department["id"] = department.pop("_id")
            departments.append(Department(**department))
        return departments

    async def update_department(self, department_id: str, name: Optional[str] = None,
                               code: Optional[str] = None) -> Optional[Department]:
        update_data = {}
        if name is not None:
            update_data["name"] = name.strip()
        if code is not None:
            update_data["code"] = code.strip().upper()

        if not update_data:
            return await self.get_department(department_id)

        result = await self.collection.find_one_and_update(
            {"_id": department_id},
            {"$set": update_data},
            return_document=True,
        )
        if result:
            result["id"] = result.pop("_id")
            return Department(**result)
        return None

    async def delete_department(self, department_id: str) -> bool:
        result = await self.collection.delete_one({"_id": department_id})
        return result.deleted_count > 0
