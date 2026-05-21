from pydantic import BaseModel, Field, EmailStr, model_validator
from typing import Optional
from app.models.schemas import (
    UserStatus,
    StaffRole,
    StudentStatus,
    LecturerStatus,
    EnrollmentStatus,
    AttendanceStatus,
    AttendanceSessionStatus,
)


# User Schemas
class UserCreate(BaseModel):
    full_name: str
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    matric_number: Optional[str] = None
    picture: Optional[str] = None


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    matric_number: Optional[str] = None
    picture: Optional[str] = None
    status: Optional[UserStatus] = None


class UserResponse(BaseModel):
    id: str
    full_name: str
    email: Optional[str] = None
    phone_number: Optional[str] = None
    matric_number: Optional[str] = None
    picture: Optional[str] = None
    status: UserStatus
    created_at: str


# Staff Schemas
class StaffLogin(BaseModel):
    email: str
    password: str


class StaffCreate(BaseModel):
    name: str
    email: EmailStr
    role: StaffRole
    password: str


class StaffUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[StaffRole] = None


class StaffChangePassword(BaseModel):
    current_password: str
    new_password: str


class StaffResponse(BaseModel):
    id: str
    name: str
    email: str
    role: str
    created_at: Optional[str] = None
    
    class Config:
        from_attributes = True


# QR Token Schemas
class QRTokenResponse(BaseModel):
    id: str
    user_id: str
    is_active: bool
    issued_at: str


class QRCodeGenerateResponse(BaseModel):
    """Response for QR code generation with image data"""
    id: str
    user_id: str
    is_active: bool
    issued_at: str
    qr_code_data: str  # Base64 encoded PNG image


class QRTokenValidate(BaseModel):
    token: str


class QRGenerateRequest(BaseModel):
    user_id: Optional[str] = None
    course_id: Optional[str] = None
    lecture_id: Optional[str] = None
    ttl_minutes: Optional[int] = None
    issued_by: Optional[str] = None
    metadata: Optional[dict] = None


# Session Schemas
class SessionCreate(BaseModel):
    user_id: str
    token: str
    kiosk_id: str


class SessionApprove(BaseModel):
    user_id: str
    token: str
    kiosk_id: str
    notes: Optional[str] = None


class SessionDeny(BaseModel):
    user_id: str
    token: str
    reason: Optional[str] = None


class SessionResponse(BaseModel):
    id: str
    user_id: str
    kiosk_id: str
    entry_time: str
    exit_time: Optional[str] = None
    approved_by: str


# Kiosk Schemas
class KioskRegister(BaseModel):
    device_name: str
    ip_address: Optional[str] = None


class KioskUpdate(BaseModel):
    device_name: Optional[str] = None
    ip_address: Optional[str] = None
    is_active: Optional[bool] = None


class KioskResponse(BaseModel):
    id: str
    device_name: str
    is_active: bool
    registered_at: str
    ip_address: Optional[str] = None


class KioskAssign(BaseModel):
    """Assign a kiosk to a staff operator"""
    staff_id: Optional[str] = None  # None to unassign


class KioskDetailResponse(BaseModel):
    """Detailed kiosk response with operator info"""
    id: str
    device_name: str
    is_active: bool
    registered_at: str
    ip_address: Optional[str] = None
    location: Optional[str] = None
    assigned_to: Optional[str] = None
    operator_name: Optional[str] = None  # Populated from staff lookup
    health_status: Optional[str] = None
    last_seen: Optional[str] = None


# Token Response
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    role: Optional[str] = None
    name: Optional[str] = None


# Audit Log Schemas
class AuditLogResponse(BaseModel):
    id: str
    action: str
    actor_id: str
    timestamp: str
    metadata: dict


# Generic Response
class MessageResponse(BaseModel):
    message: str


class OccupancyResponse(BaseModel):
    current: int
    message: str


# Course & Enrollment Schemas
class CourseCreate(BaseModel):
    code: str
    title: str
    description: Optional[str] = None
    department_id: Optional[str] = None
    lecturer_id: Optional[str] = None


class CourseUpdate(BaseModel):
    code: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    department_id: Optional[str] = None
    lecturer_id: Optional[str] = None


class CourseAssignRequest(BaseModel):
    course_ids: list[str]


class CourseResponse(BaseModel):
    id: str
    code: str
    title: str
    description: Optional[str] = None
    department_id: Optional[str] = None
    lecturer_id: Optional[str] = None
    created_at: str


class EnrollmentCreate(BaseModel):
    user_id: str


class EnrollmentResponse(BaseModel):
    id: str
    user_id: str
    course_id: str
    enrolled_at: str


# Attendance Schemas
class AttendanceCreate(BaseModel):
    user_id: str
    course_id: str
    lecture_id: Optional[str] = None
    method: Optional[str] = "qr"
    kiosk_id: Optional[str] = None
    qr_token_id: Optional[str] = None


class AttendanceResponse(BaseModel):
    id: str
    user_id: str
    course_id: str
    lecture_id: Optional[str] = None
    timestamp: str
    status: str
    method: str
    kiosk_id: Optional[str] = None
    qr_token_id: Optional[str] = None


class AttendanceReportItem(BaseModel):
    date: str
    present: int
    absent: int


# Department Schemas
class DepartmentCreate(BaseModel):
    name: str
    code: str


class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None


class DepartmentResponse(BaseModel):
    id: str
    name: str
    code: str
    created_at: str


# Lecturer Schemas
class LecturerCreate(BaseModel):
    full_name: str
    email: EmailStr
    department_id: Optional[str] = None
    password: str


class LecturerUpdate(BaseModel):
    full_name: Optional[str] = None
    department_id: Optional[str] = None
    status: Optional[LecturerStatus] = None


class LecturerLogin(BaseModel):
    email: EmailStr
    password: str


class LecturerResponse(BaseModel):
    id: str
    full_name: str
    email: str
    department_id: Optional[str] = None
    status: LecturerStatus
    created_at: str


# Student Schemas
class StudentRegister(BaseModel):
    full_name: str
    email: EmailStr
    matric_number: str
    department_id: Optional[str] = None
    password: str
    course_codes: Optional[list[str]] = None


class StudentLogin(BaseModel):
    email: Optional[EmailStr] = None
    matric_number: Optional[str] = None
    password: str

    @model_validator(mode='after')
    def require_email_or_matric(cls, values):
        email, matric_number = values.email, values.matric_number
        if not email and not matric_number:
            raise ValueError('Email or matric number is required')
        return values


class StudentUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    matric_number: Optional[str] = None
    department_id: Optional[str] = None
    status: Optional[StudentStatus] = None


class StudentResponse(BaseModel):
    id: str
    full_name: str
    email: str
    matric_number: str
    department_id: Optional[str] = None
    status: StudentStatus
    created_at: str
    course_codes: list[str] = Field(default_factory=list)


# Enrollment Schemas
class EnrollmentRequest(BaseModel):
    course_code: str


class EnrollmentBulkRequest(BaseModel):
    course_codes: list[str]


class EnrollmentBatchRequest(BaseModel):
    enrollment_ids: list[str]


class EnrollmentUpdate(BaseModel):
    status: EnrollmentStatus


class EnrollmentDetail(BaseModel):
    id: str
    student_id: str
    course_id: str
    status: EnrollmentStatus
    requested_at: str
    reviewed_at: Optional[str] = None
    reviewed_by: Optional[str] = None


class AdminEnrollment(BaseModel):
    id: str
    student_id: str
    course_id: str
    course_code: str
    course_title: str
    status: EnrollmentStatus
    requested_at: str
    reviewed_at: Optional[str] = None
    reviewed_by: Optional[str] = None


class StudentDetailResponse(BaseModel):
    id: str
    full_name: str
    email: str
    matric_number: str
    department_id: Optional[str] = None
    department_name: Optional[str] = None
    status: StudentStatus
    created_at: str
    course_codes: list[str] = Field(default_factory=list)
    enrollments: list[AdminEnrollment] = Field(default_factory=list)


# Attendance Session Schemas
class AttendanceSessionCreate(BaseModel):
    course_id: str
    duration_minutes: int
    start_time: str | None = None


class AttendanceSessionResponse(BaseModel):
    id: str
    course_id: str
    lecturer_id: str
    qr_token: str
    duration_minutes: int
    start_time: str
    end_time: str
    status: AttendanceSessionStatus
    created_at: str
    closed_at: Optional[str] = None


class AttendanceSessionQRResponse(BaseModel):
    qr_token: str
    qr_code_data: str


# Attendance Record Schemas
class AttendanceMarkRequest(BaseModel):
    qr_token: str


class AttendanceRecordResponse(BaseModel):
    id: str
    session_id: str
    student_id: str
    course_id: str
    status: AttendanceStatus
    marked_at: str
    method: str


class LiveAttendanceRecordResponse(BaseModel):
    id: str
    session_id: str
    student_id: str
    student_name: Optional[str] = None
    student_matric: Optional[str] = None
    course_id: str
    status: AttendanceStatus
    marked_at: str
    method: str

