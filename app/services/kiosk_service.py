from typing import List, Optional, Dict, TYPE_CHECKING
from datetime import datetime, timezone
from app.models.schemas import Kiosk
from app.utils.qr_generator import generate_uuid
import httpx

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase


class KioskService:
    """Service for kiosk management"""
    
    def __init__(self, db: 'AsyncIOMotorDatabase'):
        self.db = db
        self.collection = db.kiosks
    
    async def register_kiosk(self, device_name: str, ip_address: Optional[str] = None) -> Kiosk:
        """Register a new kiosk device"""
        kiosk_data = {
            "_id": generate_uuid(),
            "device_name": device_name,
            "is_active": True,
            "registered_at": datetime.now(timezone.utc),
            "ip_address": ip_address,
            "last_seen": datetime.now(timezone.utc),
            "health_status": "online"
        }
        await self.collection.insert_one(kiosk_data)
        kiosk_data["id"] = kiosk_data.pop("_id")
        return Kiosk(**kiosk_data)
    
    async def get_kiosk(self, kiosk_id: str) -> Optional[Kiosk]:
        """Get kiosk by ID"""
        kiosk = await self.collection.find_one({"_id": kiosk_id})
        if kiosk:
            kiosk["id"] = kiosk.pop("_id")
            return Kiosk(**kiosk)
        return None
    
    async def get_all_kiosks(self, skip: int = 0, limit: int = 100) -> List[Kiosk]:
        """Get all kiosks"""
        cursor = self.collection.find().skip(skip).limit(limit)
        kiosks = []
        async for kiosk in cursor:
            kiosk["id"] = kiosk.pop("_id")
            kiosks.append(Kiosk(**kiosk))
        return kiosks
    
    async def get_active_kiosks(self) -> List[Kiosk]:
        """Get all active kiosks"""
        cursor = self.collection.find({"is_active": True})
        kiosks = []
        async for kiosk in cursor:
            kiosk["id"] = kiosk.pop("_id")
            kiosks.append(Kiosk(**kiosk))
        return kiosks
    
    async def update_kiosk(self, kiosk_id: str, device_name: Optional[str] = None, 
                          ip_address: Optional[str] = None, is_active: Optional[bool] = None) -> Optional[Kiosk]:
        """Update kiosk information"""
        update_data = {}
        if device_name:
            update_data["device_name"] = device_name
        if ip_address:
            update_data["ip_address"] = ip_address
        if is_active is not None:
            update_data["is_active"] = is_active
        
        result = await self.collection.find_one_and_update(
            {"_id": kiosk_id},
            {"$set": update_data},
            return_document=True
        )
        if result:
            result["id"] = result.pop("_id")
            return Kiosk(**result)
        return None
    
    async def delete_kiosk(self, kiosk_id: str) -> bool:
        """Delete kiosk"""
        result = await self.collection.delete_one({"_id": kiosk_id})
        return result.deleted_count > 0
    
    async def deactivate_kiosk(self, kiosk_id: str) -> Optional[Kiosk]:
        """Deactivate a kiosk"""
        return await self.update_kiosk(kiosk_id, is_active=False)
    
    async def activate_kiosk(self, kiosk_id: str) -> Optional[Kiosk]:
        """Activate a kiosk"""
        return await self.update_kiosk(kiosk_id, is_active=True)
    
    async def assign_to_staff(self, kiosk_id: str, staff_id: Optional[str]) -> Optional[Kiosk]:
        """Assign a kiosk to a staff operator (or unassign if staff_id is None)"""
        result = await self.collection.find_one_and_update(
            {"_id": kiosk_id},
            {"$set": {"assigned_to": staff_id}},
            return_document=True
        )
        if result:
            result["id"] = result.pop("_id")
            return Kiosk(**result)
        return None
    
    async def get_kiosks_by_staff(self, staff_id: str) -> List[Kiosk]:
        """Get all kiosks assigned to a staff member"""
        cursor = self.collection.find({"assigned_to": staff_id})
        kiosks = []
        async for kiosk in cursor:
            kiosk["id"] = kiosk.pop("_id")
            kiosks.append(Kiosk(**kiosk))
        return kiosks
    
    async def check_kiosk_health(self, kiosk_id: str) -> Dict[str, any]:
        """Check kiosk connectivity and health status"""
        kiosk = await self.get_kiosk(kiosk_id)
        if not kiosk:
            return {"status": "error", "message": "Kiosk not found"}
        
        # Try to ping the kiosk
        is_online = False
        error_message = None
        
        if kiosk.ip_address:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(
                        f"http://{kiosk.ip_address}:8080/health",
                        timeout=5.0
                    )
                    is_online = response.status_code == 200
            except Exception as e:
                error_message = str(e)
        
        # Update last seen and health status
        health_status = "online" if is_online else "offline"
        await self.collection.find_one_and_update(
            {"_id": kiosk_id},
            {
                "$set": {
                    "last_seen": datetime.now(timezone.utc),
                    "health_status": health_status
                }
            },
            return_document=True
        )
        
        return {
            "status": "success",
            "kiosk_id": kiosk_id,
            "device_name": kiosk.device_name,
            "is_online": is_online,
            "health_status": health_status,
            "ip_address": kiosk.ip_address,
            "last_seen": datetime.now(timezone.utc).isoformat(),
            "error": error_message
        }
