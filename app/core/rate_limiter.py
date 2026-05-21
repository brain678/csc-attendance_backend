"""
Rate limiting service for preventing abuse
"""
from typing import Optional, Dict
from datetime import datetime, timedelta, timezone
from app.core.mongodb import get_database
from fastapi import HTTPException, status


class RateLimiter:
    """Token-based rate limiter with MongoDB backend"""
    
    def __init__(self, db):
        self.db = db
        self.collection = db.rate_limits
        # Default: 10 attempts per minute per IP/user
        self.defaults = {
            "qr_validate": {"attempts": 10, "window_minutes": 1},
            "qr_scan": {"attempts": 30, "window_minutes": 1},
            "login": {"attempts": 5, "window_minutes": 5},
        }
    
    async def check_limit(
        self,
        key: str,
        limit_type: str = "qr_validate",
        custom_attempts: Optional[int] = None,
        custom_window_minutes: Optional[int] = None
    ) -> bool:
        """
        Check if rate limit is exceeded
        Returns True if allowed, raises HTTPException if limit exceeded
        """
        config = self.defaults.get(limit_type, self.defaults["qr_validate"])
        attempts = custom_attempts or config["attempts"]
        window_minutes = custom_window_minutes or config["window_minutes"]
        
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(minutes=window_minutes)
        
        # Count recent attempts
        count = await self.collection.count_documents({
            "key": key,
            "limit_type": limit_type,
            "timestamp": {"$gte": window_start}
        })
        
        if count >= attempts:
            # Clean up old entries
            await self.collection.delete_many({
                "key": key,
                "timestamp": {"$lt": window_start}
            })
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Try again in {window_minutes} minute(s)."
            )
        
        # Record this attempt
        await self.collection.insert_one({
            "key": key,
            "limit_type": limit_type,
            "timestamp": now
        })
        
        # Clean old entries older than 1 hour
        await self.collection.delete_many({
            "timestamp": {"$lt": now - timedelta(hours=1)}
        })
        
        return True
    
    async def reset(self, key: str, limit_type: str = "qr_validate") -> None:
        """Reset rate limit for a key"""
        await self.collection.delete_many({
            "key": key,
            "limit_type": limit_type
        })
    
    async def get_remaining(
        self,
        key: str,
        limit_type: str = "qr_validate"
    ) -> int:
        """Get remaining attempts in current window"""
        config = self.defaults.get(limit_type, self.defaults["qr_validate"])
        window_minutes = config["window_minutes"]
        
        window_start = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
        count = await self.collection.count_documents({
            "key": key,
            "limit_type": limit_type,
            "timestamp": {"$gte": window_start}
        })
        
        return max(0, config["attempts"] - count)


class TokenSecurityValidator:
    """Validate token security and freshness"""
    
    def __init__(self, db):
        self.db = db
        self.collection = db.token_cache
        # Cache valid tokens for 30 seconds
        self.cache_ttl_seconds = 30
    
    async def is_token_cached_valid(self, token_id: str) -> bool:
        """Check if token is in cache and valid"""
        cached = await self.collection.find_one({"token_id": token_id})
        if cached and cached.get("is_valid"):
            return True
        return False
    
    async def cache_token_validation(
        self,
        token_id: str,
        is_valid: bool,
        user_id: Optional[str] = None
    ) -> None:
        """Cache token validation result"""
        await self.collection.update_one(
            {"token_id": token_id},
            {
                "$set": {
                    "token_id": token_id,
                    "is_valid": is_valid,
                    "user_id": user_id,
                    "validated_at": datetime.now(timezone.utc),
                    "expires_at": datetime.now(timezone.utc) + timedelta(seconds=self.cache_ttl_seconds)
                }
            },
            upsert=True
        )
        
        # Create TTL index (auto-delete after expiry)
        await self.collection.create_index(
            "expires_at",
            expireAfterSeconds=0
        )
    
    async def check_duplicate_scan(
        self,
        token_id: str,
        kiosk_id: str,
        window_seconds: int = 120
    ) -> bool:
        """
        Check if same token was just scanned on same kiosk
        Prevents accidental double-scans within 2 minutes (120 seconds)
        """
        recent_scan = await self.db.scan_history.find_one({
            "token_id": token_id,
            "kiosk_id": kiosk_id,
            "timestamp": {
                "$gte": datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
            }
        })
        return recent_scan is not None
    
    async def record_scan(
        self,
        token_id: str,
        kiosk_id: str,
        success: bool = True
    ) -> None:
        """Record a scan attempt"""
        await self.db.scan_history.insert_one({
            "token_id": token_id,
            "kiosk_id": kiosk_id,
            "success": success,
            "timestamp": datetime.now(timezone.utc)
        })
        
        # Create TTL index (keep scan history for 1 hour)
        await self.db.scan_history.create_index(
            "timestamp",
            expireAfterSeconds=3600
        )
