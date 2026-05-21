from typing import Optional, List, TYPE_CHECKING
from datetime import datetime, timezone
from app.models.schemas import Session
from app.utils.qr_generator import generate_uuid

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase


class SessionService:
    """Service for session management with transaction support"""
    
    def __init__(self, db: 'AsyncIOMotorDatabase'):
        self.db = db
        self.collection = db.sessions
    
    async def get_active_session(self, user_id: str) -> Optional[Session]:
        """Get active session for a user"""
        session = await self.collection.find_one({
            "user_id": user_id,
            "exit_time": None
        })
        if session:
            session["id"] = session.pop("_id")
            return Session(**session)
        return None
    
    async def create_session(self, user_id: str, kiosk_id: str, approved_by: str) -> Session:
        """Create a new session (atomic operation)"""
        session_data = {
            "_id": generate_uuid(),
            "user_id": user_id,
            "kiosk_id": kiosk_id,
            "entry_time": datetime.now(timezone.utc),
            "exit_time": None,
            "approved_by": approved_by
        }
        await self.collection.insert_one(session_data)
        session_data["id"] = session_data.pop("_id")
        return Session(**session_data)
    
    async def end_session(self, session_id: str) -> Optional[Session]:
        """End a session by setting exit_time"""
        result = await self.collection.find_one_and_update(
            {"_id": session_id},
            {"$set": {"exit_time": datetime.now(timezone.utc)}},
            return_document=True
        )
        if result:
            result["id"] = result.pop("_id")
            return Session(**result)
        return None
    
    async def get_session(self, session_id: str) -> Optional[Session]:
        """Get session by ID"""
        session = await self.collection.find_one({"_id": session_id})
        if session:
            session["id"] = session.pop("_id")
            return Session(**session)
        return None
    
    async def get_active_sessions(self, skip: int = 0, limit: int = 100) -> List[Session]:
        """Get all active sessions"""
        cursor = self.collection.find({"exit_time": None}).skip(skip).limit(limit)
        sessions = []
        async for session in cursor:
            session["id"] = session.pop("_id")
            sessions.append(Session(**session))
        return sessions
    
    async def get_user_sessions(self, user_id: str, skip: int = 0, limit: int = 100) -> List[Session]:
        """Get all sessions for a user"""
        cursor = self.collection.find({"user_id": user_id}).skip(skip).limit(limit)
        sessions = []
        async for session in cursor:
            session["id"] = session.pop("_id")
            sessions.append(Session(**session))
        return sessions
    
    async def get_occupancy_count(self) -> int:
        """Get current occupancy (active sessions)"""
        count = await self.collection.count_documents({"exit_time": None})
        return count    
    async def get_completed_sessions(self, start_date: Optional[datetime] = None, 
                                    end_date: Optional[datetime] = None,
                                    skip: int = 0, limit: int = 1000) -> List[dict]:
        """Get completed sessions with user details for reporting"""
        query = {"exit_time": {"$ne": None}}
        
        # Add date range filters if provided
        if start_date or end_date:
            date_query = {}
            if start_date:
                date_query["$gte"] = start_date
            if end_date:
                date_query["$lte"] = end_date
            query["entry_time"] = date_query
        
        # Use aggregation pipeline to join with users collection
        pipeline = [
            {"$match": query},
            {
                "$lookup": {
                    "from": "users",
                    "localField": "user_id",
                    "foreignField": "_id",
                    "as": "user_details"
                }
            },
            {"$unwind": "$user_details"},
            {
                "$project": {
                    "session_id": "$_id",
                    "user_id": 1,
                    "full_name": "$user_details.full_name",
                    "matric_number": "$user_details.matric_number",
                    "entry_time": 1,
                    "exit_time": 1,
                    "approved_by": 1,
                    "kiosk_id": 1
                }
            },
            {"$sort": {"entry_time": -1}},
            {"$skip": skip},
            {"$limit": limit}
        ]
        
        cursor = self.collection.aggregate(pipeline)
        sessions = []
        async for session in cursor:
            sessions.append(session)
        
        return sessions