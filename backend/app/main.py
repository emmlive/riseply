from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from app.database import Base, engine
from app.config import settings
from app.routers import auth, me, profiles, pipeline, billing, interview, job_buddy, rise_index

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Riseply API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(me.router)
app.include_router(profiles.router)
app.include_router(pipeline.router)
app.include_router(billing.router)
app.include_router(interview.router)
app.include_router(job_buddy.router)
app.include_router(rise_index.router)

# Serve tailored resume .docx files for download
os.makedirs("data/tailored_resumes", exist_ok=True)
app.mount("/files/tailored_resumes", StaticFiles(directory="data/tailored_resumes"), name="tailored_resumes")


@app.get("/health")
def health():
    return {"status": "ok"}
