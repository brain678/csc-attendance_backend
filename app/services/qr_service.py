from typing import Optional, TYPE_CHECKING
from datetime import datetime, timezone
from app.models.schemas import QRToken
from app.utils.qr_generator import generate_uuid
from datetime import timedelta
from typing import Dict

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase


class QRTokenService:
    """Service for QR token management"""
    
    def __init__(self, db: 'AsyncIOMotorDatabase'):
        self.db = db
        self.collection = db.qr_tokens
    
    async def create_qr_token(self, user_id: str, course_id: Optional[str] = None,
                              lecture_id: Optional[str] = None, ttl_minutes: Optional[int] = None,
                              issued_by: Optional[str] = None, metadata: Optional[dict] = None) -> QRToken:
        """Create a new QR token for a user.

        Optionally associate the token with a course/lecture and set a TTL (minutes).
        """
        issued_at = datetime.now(timezone.utc)
        expires_at = None
        if ttl_minutes is not None:
            expires_at = issued_at + timedelta(minutes=ttl_minutes)

        token_data = {
            "_id": generate_uuid(),
            "user_id": user_id,
            "is_active": True,
            "issued_at": issued_at,
            "revoked_at": None,
            "course_id": course_id,
            "lecture_id": lecture_id,
            "expires_at": expires_at,
            "issued_by": issued_by,
            "metadata": metadata or {}
        }
        await self.collection.insert_one(token_data)
        token_data["id"] = token_data.pop("_id")
        return QRToken(**token_data)
    
    async def get_qr_token(self, token_id: str) -> Optional[QRToken]:
        """Get QR token by ID"""
        token = await self.collection.find_one({"_id": token_id})
        if token:
            token["id"] = token.pop("_id")
            return QRToken(**token)
        return None
    
    async def get_user_tokens(self, user_id: str) -> list:
        """Get all tokens for a user"""
        cursor = self.collection.find({"user_id": user_id})
        tokens = []
        async for token in cursor:
            token["id"] = token.pop("_id")
            tokens.append(QRToken(**token))
        return tokens
    
    async def get_all_tokens(self) -> list:
        """Get all QR tokens"""
        cursor = self.collection.find().sort("issued_at", -1)
        tokens = []
        async for token in cursor:
            token["id"] = token.pop("_id")
            tokens.append(QRToken(**token))
        return tokens
    
    async def validate_token(self, token_id: str) -> bool:
        """Validate if a token is active and not expired.

        If the token has expired, mark it revoked in the database to prevent reuse.
        Returns True when valid, False otherwise.
        """
        token = await self.get_qr_token(token_id)
        if not token:
            return False

        # Check active flag first
        if not token.is_active:
            return False

        # Check expiry
        if token.expires_at:
            now = datetime.now(timezone.utc)
            # pydantic may parse expires_at as datetime; ensure timezone-aware
            exp = token.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if now > exp:
                # Revoke token in DB to avoid future valid reads
                await self.collection.update_one({"_id": token_id}, {"$set": {"is_active": False, "revoked_at": now}})
                return False

        return True
    
    async def revoke_token(self, token_id: str) -> Optional[QRToken]:
        """Revoke a QR token"""
        result = await self.collection.find_one_and_update(
            {"_id": token_id},
            {
                "$set": {
                    "is_active": False,
                    "revoked_at": datetime.now(timezone.utc)
                }
            },
            return_document=True
        )
        if result:
            result["id"] = result.pop("_id")
            return QRToken(**result)
        return None
    
    async def revoke_all_user_tokens(self, user_id: str) -> int:
        """Revoke all tokens for a user"""
        result = await self.collection.update_many(
            {"user_id": user_id, "is_active": True},
            {
                "$set": {
                    "is_active": False,
                    "revoked_at": datetime.now(timezone.utc)
                }
            }
        )
        return result.modified_count
