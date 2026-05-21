from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from motor.motor_asyncio import AsyncIOMotorClient as MotorClient, AsyncIOMotorDatabase as MotorDatabase
from .config import settings


# Global database connection
client: Optional[MotorClient] = None
database: Optional[MotorDatabase] = None


async def connect_to_mongo():
    """Connect to MongoDB"""
    global client, database
    client = MotorClient(settings.mongodb_url)
    database = client[settings.mongodb_database]
    await database.attendance_records.create_index(
        [("session_id", 1), ("student_id", 1)],
        unique=True,
        background=True,
        name="session_student_unique",
    )
    print("Connected to MongoDB")


async def close_mongo_connection():
    """Close MongoDB connection"""
    global client
    if client:
        client.close()
        print("Closed MongoDB connection")


def get_database() -> MotorDatabase:
    """Get database instance"""
    return database
