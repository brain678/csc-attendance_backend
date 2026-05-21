from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.mongodb import connect_to_mongo, close_mongo_connection
from app.api import (
    health,
    auth,
    users,
    staff,
    sessions,
    qr,
    kiosks,
    logs,
    dashboard,
    qr_advanced,
    departments,
    courses,
    lecturers,
    students,
    enrollments,
    attendance_sessions,
    attendance,
    reports,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 CSCATTENDANCE - Workspace Center Access Management System Starting...")
    await connect_to_mongo()
    print("✅ Connected to MongoDB")
    yield
    # Shutdown
    print("🛑 Shutting down CSCATTENDANCE...")
    await close_mongo_connection()
    print("✅ Database connection closed")


app = FastAPI(
    title="CSCATTENDANCE - Class Attendance System",
    version=settings.app_version,
    description="Class attendance system with session QR codes and role-based access",
    debug=settings.debug,
    lifespan=lifespan,
)

# CORS configuration - must be first middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://localhost:8000",
        "http://localhost:8001",
        "http://localhost:8002",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3002",
        "http://127.0.0.1:8000",
        "http://127.0.0.1:8001",
        
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Kiosk-ID"],
    expose_headers=["Content-Type"],
    max_age=3600,
)

# Include all routers
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(users.router)
app.include_router(staff.router)
app.include_router(sessions.router)
app.include_router(qr.router)
app.include_router(qr_advanced.router)
app.include_router(kiosks.router)
app.include_router(logs.router)
app.include_router(departments.router)
app.include_router(courses.router)
app.include_router(lecturers.router)
app.include_router(students.router)
app.include_router(enrollments.router)
app.include_router(attendance_sessions.router)
app.include_router(attendance.router)
app.include_router(reports.router)


@app.get("/")
async def root():
    return {
        "service": "CSCATTENDANCE - Class Attendance System",
        "version": settings.app_version,
        "status": "running",
        "docs": "/docs",
        "health": "/api/health"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=settings.debug,
    )
