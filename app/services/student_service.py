from typing import Optional, List, TYPE_CHECKING
from datetime import datetime, timezone
from app.models.schemas import Student, StudentStatus
from app.core.security import get_password_hash, verify_password
from app.utils.qr_generator import generate_uuid

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorDatabase


class StudentService:
    """Service for student management"""

    def __init__(self, db: 'AsyncIOMotorDatabase'):
        self.db = db
        self.collection = db.students

    async def create_student(self, full_name: str, email: str, matric_number: str,
                             department_id: Optional[str], password: str,
                             status: StudentStatus = StudentStatus.active) -> Student:
        student_data = {
            "_id": generate_uuid(),
            "full_name": full_name.strip(),
            "email": email.strip().lower(),
            "matric_number": matric_number.strip().upper(),
            "department_id": department_id,
            "password_hash": get_password_hash(password),
            "status": status,
            "created_at": datetime.now(timezone.utc),
        }
        await self.collection.insert_one(student_data)
        student_data["id"] = student_data.pop("_id")
        return Student(**student_data)

    async def get_student(self, student_id: str) -> Optional[Student]:
        student = await self.collection.find_one({"_id": student_id})
        if student:
            student["id"] = student.pop("_id")
            return Student(**student)
        return None

    async def get_student_by_email(self, email: str) -> Optional[Student]:
        student = await self.collection.find_one({"email": email.strip().lower()})
        if student:
            student["id"] = student.pop("_id")
            return Student(**student)
        return None

    async def get_student_by_matric(self, matric_number: str) -> Optional[Student]:
        student = await self.collection.find_one({"matric_number": matric_number.strip().upper()})
        if student:
            student["id"] = student.pop("_id")
            return Student(**student)
        return None

    async def get_all_students(self, skip: int = 0, limit: int = 100) -> List[Student]:
        cursor = self.collection.find().sort("full_name", 1).skip(skip).limit(limit)
        students = []
        async for student in cursor:
            student["id"] = student.pop("_id")
            students.append(Student(**student))
        return students

    async def authenticate_student(self, email: Optional[str], matric_number: Optional[str],
                                   password: str) -> Optional[Student]:
        query = {}
        if email and matric_number:
            query = {
                "$or": [
                    {"email": email.strip().lower()},
                    {"matric_number": matric_number.strip().upper()},
                ]
            }
        elif email:
            query = {"email": email.strip().lower()}
        elif matric_number:
            query = {"matric_number": matric_number.strip().upper()}
        else:
            return None

        student = await self.collection.find_one(query)
        if student:
            student["id"] = student.pop("_id")
            student_obj = Student(**student)
            if verify_password(password, student_obj.password_hash):
                return student_obj
        return None

    async def update_student(self, student_id: str, full_name: Optional[str] = None,
                             email: Optional[str] = None, matric_number: Optional[str] = None,
                             department_id: Optional[str] = None,
                             status: Optional[StudentStatus] = None) -> Optional[Student]:
        update_data = {}
        if full_name is not None:
            update_data["full_name"] = full_name.strip()
        if email is not None:
            update_data["email"] = email.strip().lower()
        if matric_number is not None:
            update_data["matric_number"] = matric_number.strip().upper()
        if department_id is not None:
            update_data["department_id"] = department_id
        if status is not None:
            update_data["status"] = status

        if not update_data:
            return await self.get_student(student_id)

        result = await self.collection.find_one_and_update(
            {"_id": student_id},
            {"$set": update_data},
            return_document=True,
        )
        if result:
            result["id"] = result.pop("_id")
            return Student(**result)
        return None

    async def delete_student(self, student_id: str) -> bool:
        result = await self.collection.delete_one({"_id": student_id})
        return result.deleted_count > 0

    async def change_password(self, student_id: str, new_password: str) -> Optional[Student]:
        result = await self.collection.find_one_and_update(
            {"_id": student_id},
            {"$set": {"password_hash": get_password_hash(new_password)}},
            return_document=True,
        )
        if result:
            result["id"] = result.pop("_id")
            return Student(**result)
        return None
