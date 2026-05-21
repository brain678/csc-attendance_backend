from typing import List, Optional, TYPE_CHECKING
from datetime import datetime, timezone
from app.models.schemas import User, UserStatus
from app.utils.qr_generator import generate_uuid

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase


class UserService:
    """Service for user management"""
    
    def __init__(self, db: 'AsyncIOMotorDatabase'):
        self.db = db
        self.collection = db.users
    
    async def create_user(self, full_name: str, email: Optional[str] = None, 
                         phone_number: Optional[str] = None, matric_number: Optional[str] = None,
                         picture: Optional[str] = None) -> User:
        """Create a new user"""
        user_data = {
            "_id": generate_uuid(),
            "full_name": full_name,
            "email": email,
            "phone_number": phone_number,
            "matric_number": matric_number,
            "picture": picture,
            "status": UserStatus.active,
            "created_at": datetime.now(timezone.utc)
        }
        result = await self.collection.insert_one(user_data)
        user_data["id"] = user_data.pop("_id")
        return User(**user_data)
    
    async def get_user(self, user_id: str) -> Optional[User]:
        """Get user by ID"""
        user = await self.collection.find_one({"_id": user_id})
        if user:
            user["id"] = user.pop("_id")
            return User(**user)
        return None
    
    async def get_all_users(self, skip: int = 0, limit: int = 100) -> List[User]:
        """Get all users with pagination"""
        cursor = self.collection.find().skip(skip).limit(limit)
        users = []
        async for user in cursor:
            user["id"] = user.pop("_id")
            users.append(User(**user))
        return users
    
    async def update_user(self, user_id: str, full_name: Optional[str] = None, 
                         email: Optional[str] = None, phone_number: Optional[str] = None,
                         matric_number: Optional[str] = None, picture: Optional[str] = None,
                         status: Optional[UserStatus] = None) -> Optional[User]:
        """Update user"""
        update_data = {}
        if full_name:
            update_data["full_name"] = full_name
        if email is not None:
            update_data["email"] = email
        if phone_number is not None:
            update_data["phone_number"] = phone_number
        if matric_number is not None:
            update_data["matric_number"] = matric_number
        if picture is not None:
            update_data["picture"] = picture
        if status:
            update_data["status"] = status
        
        result = await self.collection.find_one_and_update(
            {"_id": user_id},
            {"$set": update_data},
            return_document=True
        )
        if result:
            result["id"] = result.pop("_id")
            return User(**result)
        return None
    
    async def delete_user(self, user_id: str) -> bool:
        """Delete user"""
        result = await self.collection.delete_one({"_id": user_id})
        return result.deleted_count > 0
    
    async def suspend_user(self, user_id: str) -> Optional[User]:
        """Suspend a user"""
        return await self.update_user(user_id, status=UserStatus.suspended)
    
    async def activate_user(self, user_id: str) -> Optional[User]:
        """Activate a user"""
        return await self.update_user(user_id, status=UserStatus.active)
    
    async def user_has_active_session(self, user_id: str) -> bool:
        """Check if user has an active session"""
        session = await self.db.sessions.find_one({
            "user_id": user_id,
            "exit_time": None
        })
        return session is not None
