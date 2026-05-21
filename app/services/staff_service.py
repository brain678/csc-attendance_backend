from typing import Optional, List, TYPE_CHECKING
from datetime import datetime, timezone
from app.models.schemas import Staff, StaffRole
from app.core.security import get_password_hash, verify_password
from app.utils.qr_generator import generate_uuid

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase as AsyncIOMotorDatabaseType


class StaffService:
    """Service for staff account management"""
    
    def __init__(self, db: "AsyncIOMotorDatabaseType"):
        self.db = db
        self.collection = db.staff
    
    async def create_staff(self, name: str, email: str, role: StaffRole, password: str) -> Staff:
        """Create a new staff member"""
        staff_data = {
            "_id": generate_uuid(),
            "name": name,
            "email": email,
            "role": role,
            "password_hash": get_password_hash(password),
            "created_at": datetime.now(timezone.utc)
        }
        await self.collection.insert_one(staff_data)
        staff_data["id"] = staff_data.pop("_id")
        return Staff(**staff_data)
    
    async def get_staff(self, staff_id: str) -> Optional[Staff]:
        """Get staff by ID"""
        staff = await self.collection.find_one({"_id": staff_id})
        if staff:
            staff["id"] = staff.pop("_id")
            return Staff(**staff)
        return None
    
    async def get_staff_by_email(self, email: str) -> Optional[Staff]:
        """Get staff by email"""
        staff = await self.collection.find_one({"email": email})
        if staff:
            staff["id"] = staff.pop("_id")
            return Staff(**staff)
        return None
    
    async def get_all_staff(self, skip: int = 0, limit: int = 100) -> List[Staff]:
        """Get all staff members"""
        cursor = self.collection.find().skip(skip).limit(limit)
        staff_list = []
        async for staff in cursor:
            staff["id"] = staff.pop("_id")
            staff_list.append(Staff(**staff))
        return staff_list
    
    async def authenticate_staff(self, email: str, password: str) -> Optional[Staff]:
        """Authenticate staff member"""
        staff = await self.get_staff_by_email(email)
        if staff and verify_password(password, staff.password_hash):
            return staff
        return None
    
    async def update_staff(self, staff_id: str, name: Optional[str] = None, 
                          role: Optional[StaffRole] = None) -> Optional[Staff]:
        """Update staff information"""
        update_data = {}
        if name:
            update_data["name"] = name
        if role:
            update_data["role"] = role
        
        result = await self.collection.find_one_and_update(
            {"_id": staff_id},
            {"$set": update_data},
            return_document=True
        )
        if result:
            result["id"] = result.pop("_id")
            return Staff(**result)
        return None
    
    async def delete_staff(self, staff_id: str) -> bool:
        """Delete staff member"""
        result = await self.collection.delete_one({"_id": staff_id})
        return result.deleted_count > 0
    
    async def change_password(self, staff_id: str, new_password: str) -> Optional[Staff]:
        """Change staff password"""
        result = await self.collection.find_one_and_update(
            {"_id": staff_id},
            {"$set": {"password_hash": get_password_hash(new_password)}},
            return_document=True
        )
        if result:
            result["id"] = result.pop("_id")
            return Staff(**result)
        return None
