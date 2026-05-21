from typing import Optional, List, TYPE_CHECKING
from datetime import datetime, timezone, timedelta
from app.models.schemas import AttendanceSession, AttendanceSessionStatus
from app.utils.qr_generator import generate_uuid

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase


class AttendanceSessionService:
    """Service for attendance session management"""

    def __init__(self, db: 'AsyncIOMotorDatabase'):
        self.db = db
        self.collection = db.attendance_sessions

    async def create_session(self, course_id: str, lecturer_id: str,
                             duration_minutes: int,
                             start_time: datetime | None = None) -> AttendanceSession:
        if start_time is None:
            start_time = datetime.now(timezone.utc)
        elif start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        else:
            start_time = start_time.astimezone(timezone.utc)

        end_time = start_time + timedelta(minutes=duration_minutes)
        session_data = {
            "_id": generate_uuid(),
            "course_id": course_id,
            "lecturer_id": lecturer_id,
            "qr_token": generate_uuid(),
            "duration_minutes": duration_minutes,
            "start_time": start_time,
            "end_time": end_time,
            "status": AttendanceSessionStatus.open,
            "created_at": start_time,
            "closed_at": None,
            "absences_marked": False,
        }
        await self.collection.insert_one(session_data)
        session_data["id"] = session_data.pop("_id")
        return AttendanceSession(**session_data)

    async def get_session(self, session_id: str) -> Optional[AttendanceSession]:
        session = await self.collection.find_one({"_id": session_id})
        if session:
            session["id"] = session.pop("_id")
            return AttendanceSession(**session)
        return None

    async def get_session_by_token(self, qr_token: str) -> Optional[AttendanceSession]:
        session = await self.collection.find_one({"qr_token": qr_token})
        if session:
            session["id"] = session.pop("_id")
            return AttendanceSession(**session)
        return None

    async def get_sessions(self, skip: int = 0, limit: int = 100,
                           course_id: Optional[str] = None,
                           lecturer_id: Optional[str] = None) -> List[AttendanceSession]:
        query = {}
        if course_id:
            query["course_id"] = course_id
        if lecturer_id:
            query["lecturer_id"] = lecturer_id

        cursor = self.collection.find(query).sort("start_time", -1).skip(skip).limit(limit)
        sessions = []
        async for session in cursor:
            session["id"] = session.pop("_id")
            sessions.append(AttendanceSession(**session))
        return sessions

    async def get_sessions_by_course_ids(self, course_ids: list[str], skip: int = 0,
                                         limit: int = 100,
                                         status: Optional[AttendanceSessionStatus] = None
                                         ) -> List[AttendanceSession]:
        if not course_ids:
            return []

        query: dict = {"course_id": {"$in": course_ids}}
        if status:
            query["status"] = status

        cursor = self.collection.find(query).sort("start_time", -1).skip(skip).limit(limit)
        sessions = []
        async for session in cursor:
            session["id"] = session.pop("_id")
            sessions.append(AttendanceSession(**session))
        return sessions

    async def close_session(self, session_id: str) -> Optional[AttendanceSession]:
        result = await self.collection.find_one_and_update(
            {"_id": session_id, "status": AttendanceSessionStatus.open},
            {"$set": {"status": AttendanceSessionStatus.closed, "closed_at": datetime.now(timezone.utc)}},
            return_document=True,
        )
        if result:
            result["id"] = result.pop("_id")
            return AttendanceSession(**result)
        return None

    async def mark_absences_completed(self, session_id: str) -> None:
        await self.collection.update_one(
            {"_id": session_id},
            {"$set": {"absences_marked": True}},
        )
