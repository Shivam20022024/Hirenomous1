from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import resume_routes, voice_routes, demo_voice_routes, simulation_routes, email_routes, job_board_routes, bolna_routes, auth_routes, superadmin_routes, analytics_routes, ai_recruiter_routes, interview_routes
from app.core.database import connect_to_mongo, close_mongo_connection
from app.core.config import settings
from app.services.interview_service import ensure_interview_indexes

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Production-ready AI Hiring Automation Pipeline"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Lifecycle events
@app.on_event("startup")
async def startup_db_client():
    print(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}...")
    print(f"DEBUG: Connecting to database defined in .env.local...")
    await connect_to_mongo()
    await ensure_interview_indexes()
    print(f"API is ready on port 8001")


@app.on_event("shutdown")
async def shutdown_db_client():
    await close_mongo_connection()

# Routes
app.include_router(auth_routes.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(superadmin_routes.router, prefix="/api/superadmin", tags=["Super Admin"])
app.include_router(resume_routes.router, tags=["Resume Analysis"])
# app.include_router(demo_voice_routes.router, tags=["Demo Voice Interaction"])
app.include_router(bolna_routes.router, tags=["Bolna Integration"])
# app.include_router(simulation_routes.router, tags=["System Simulation"])
app.include_router(email_routes.router, tags=["Email Interaction"])
app.include_router(job_board_routes.router, tags=["Job Board Interaction"])
app.include_router(analytics_routes.router, prefix="/analytics", tags=["Analytics"])
app.include_router(ai_recruiter_routes.router, prefix="/api", tags=["AI Recruiter"])
app.include_router(interview_routes.recruiter_router, tags=["AI Interview"])
app.include_router(interview_routes.candidate_router, tags=["AI Interview (Candidate)"])


@app.get("/")
def read_root():
    return {"message": "Welcome to Hireonomous AI Recruiter API"}

@app.get("/ping")
def ping():
    return {"ping": "pong"}

@app.get("/health")
async def health_check():
    return {
        "status": "ok"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8001, reload=True)
