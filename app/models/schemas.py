from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime, timezone
from enum import Enum


class UserStatus(str, Enum):
    active = "active"
    suspended = "suspended"


class StudentStatus(str, Enum):
    pending = "pending"
    active = "active"
    suspended = "suspended"


class LecturerStatus(str, Enum):
    active = "active"
    inactive = "inactive"


class EnrollmentStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    denied = "denied"


class AttendanceSessionStatus(str, Enum):
    open = "open"
    closed = "closed"


class AttendanceStatus(str, Enum):
    present = "present"
    absent = "absent"


class User(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
    id: Optional[str] = Field(None, alias="_id")
    full_name: str
    email: Optional[str] = None
    phone_number: Optional[str] = None
    matric_number: Optional[str] = None
    picture: Optional[str] = None
    status: UserStatus = UserStatus.active
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class QRToken(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
    id: Optional[str] = Field(None, alias="_id")
    user_id: str
    is_active: bool = True
    issued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    revoked_at: Optional[datetime] = None
    course_id: Optional[str] = None
    lecture_id: Optional[str] = None
    expires_at: Optional[datetime] = None
    issued_by: Optional[str] = None
    metadata: Optional[dict] = None


class Session(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
    id: Optional[str] = Field(None, alias="_id")
    user_id: str
    kiosk_id: str
    entry_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    exit_time: Optional[datetime] = None
    approved_by: str


class StaffRole(str, Enum):
    admin = "admin"
    operator = "operator"


class Staff(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
    id: Optional[str] = Field(None, alias="_id")
    name: str
    email: str
    role: StaffRole
    password_hash: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Department(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = Field(None, alias="_id")
    name: str
    code: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Course(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = Field(None, alias="_id")
    code: str
    title: str
    description: Optional[str] = None
    department_id: Optional[str] = None
    lecturer_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Lecturer(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = Field(None, alias="_id")
    full_name: str
    email: str
    department_id: Optional[str] = None
    password_hash: str
    status: LecturerStatus = LecturerStatus.active
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Student(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = Field(None, alias="_id")
    full_name: str
    email: str
    matric_number: str
    department_id: Optional[str] = None
    password_hash: str
    status: StudentStatus = StudentStatus.active
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Enrollment(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = Field(None, alias="_id")
    student_id: str
    course_id: str
    status: EnrollmentStatus = EnrollmentStatus.pending
    requested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None


class AttendanceSession(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = Field(None, alias="_id")
    course_id: str
    lecturer_id: str
    qr_token: str
    duration_minutes: int
    start_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: datetime
    status: AttendanceSessionStatus = AttendanceSessionStatus.open
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    closed_at: Optional[datetime] = None
    absences_marked: bool = False


class AttendanceRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = Field(None, alias="_id")
    session_id: str
    student_id: str
    course_id: str
    status: AttendanceStatus
    marked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    method: str = "qr"
    recorded_by: Optional[str] = None


class Kiosk(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
    id: Optional[str] = Field(None, alias="_id")
    device_name: str
    is_active: bool = True
    registered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ip_address: Optional[str] = None
    hardware_id: Optional[str] = None
    location: Optional[str] = None
    health_status: Optional[str] = None
    last_seen: Optional[datetime] = None
    assigned_to: Optional[str] = None  # Staff ID who operates this kiosk


class AuditLog(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
    id: Optional[str] = Field(None, alias="_id")
    action: str
    actor_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = Field(default_factory=dict)
