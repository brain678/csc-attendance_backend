from typing import Optional, List, TYPE_CHECKING
from datetime import datetime, timezone
from app.models.schemas import AuditLog

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase


class AuditLogService:
    """Service for audit logging"""
    
    def __init__(self, db: 'AsyncIOMotorDatabase'):
        self.db = db
        self.collection = db.audit_logs
    
    async def log_action(self, action: str, actor_id: str, metadata: dict = None) -> AuditLog:
        """Log an action"""
        log_data = {
            "action": action,
            "actor_id": actor_id,
            "timestamp": datetime.now(timezone.utc),
            "metadata": metadata or {}
        }
        result = await self.collection.insert_one(log_data)
        log_data["_id"] = str(result.inserted_id)
        return AuditLog(**log_data)
    
    async def get_logs(self, skip: int = 0, limit: int = 100) -> List[AuditLog]:
        """Get audit logs with pagination"""
        cursor = self.collection.find().sort("timestamp", -1).skip(skip).limit(limit)
        logs = []
        async for log in cursor:
            log["_id"] = str(log["_id"])
            logs.append(AuditLog(**log))
        return logs
    
    async def get_actor_logs(self, actor_id: str, skip: int = 0, limit: int = 100) -> List[AuditLog]:
        """Get logs for a specific actor"""
        cursor = self.collection.find({"actor_id": actor_id}).sort("timestamp", -1).skip(skip).limit(limit)
        logs = []
        async for log in cursor:
            log["_id"] = str(log["_id"])
            logs.append(AuditLog(**log))
        return logs
    
    async def get_action_logs(self, action: str, skip: int = 0, limit: int = 100) -> List[AuditLog]:
        """Get logs for a specific action"""
        cursor = self.collection.find({"action": action}).sort("timestamp", -1).skip(skip).limit(limit)
        logs = []
        async for log in cursor:
            log["_id"] = str(log["_id"])
            logs.append(AuditLog(**log))
        return logs
    
    async def get_user_activity(self, user_id: str, skip: int = 0, limit: int = 100) -> List[AuditLog]:
        """Get activity logs related to a user"""
        cursor = self.collection.find({"metadata.user_id": user_id}).sort("timestamp", -1).skip(skip).limit(limit)
        logs = []
        async for log in cursor:
            log["_id"] = str(log["_id"])
            logs.append(AuditLog(**log))
        return logs
