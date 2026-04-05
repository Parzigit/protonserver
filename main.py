import os
import uuid
import shutil
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import httpx
import jwt as pyjwt

from worker import process_pdf
from qa import answer_question
from tools import router as tools_router

load_dotenv()

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="ProtonPDF API", version="2.0.0")

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
JWT_SECRET = os.getenv("JWT_SECRET", "protonpdf-dev-secret-change-in-prod")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 72

CORS_ORIGINS = list(set([
    FRONTEND_URL,
    "http://localhost:3000",
    "http://localhost:3001",
    "https://protonpdf.vercel.app",
]))

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tools_router)

# ---------------------------------------------------------------------------
# SQLite (lightweight, no Postgres needed for free tier)
# ---------------------------------------------------------------------------
DB_PATH = os.getenv("DB_PATH", "./data/protonpdf.db")

def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            name TEXT,
            picture TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS pdfs (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            status TEXT DEFAULT 'processing',
            error TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """)
    conn.commit()
    conn.close()

init_db()

# ---------------------------------------------------------------------------
# Job status tracking (in-memory, resets on restart — fine for free tier)
# ---------------------------------------------------------------------------
job_status: dict = {}  # job_id -> {"status": "processing"|"done"|"failed", "error": str|None}

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def create_jwt(user_id: str, email: str, name: str, picture: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "name": name,
        "picture": picture,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_jwt(token: str) -> dict:
    try:
        return pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def get_current_user(request: Request) -> dict:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization")
    token = auth_header.split(" ", 1)[1]
    return decode_jwt(token)

# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------
@app.post("/auth/google")
async def google_auth(request: Request):
    """Exchange Google OAuth code for user session."""
    body = await request.json()
    code = body.get("code")
    redirect_uri = body.get("redirect_uri", f"{FRONTEND_URL}/auth/callback")

    if not code:
        raise HTTPException(status_code=400, detail="Missing code")

    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if token_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to exchange code")
        tokens = token_resp.json()

        # Get user info
        userinfo_resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        if userinfo_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to get user info")
        userinfo = userinfo_resp.json()

    user_id = userinfo["id"]
    email = userinfo["email"]
    name = userinfo.get("name", email)
    picture = userinfo.get("picture", "")

    # Upsert user
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO users (id, email, name, picture) VALUES (?, ?, ?, ?)",
        (user_id, email, name, picture),
    )
    conn.commit()
    conn.close()

    # Create JWT
    token = create_jwt(user_id, email, name, picture)
    return {"token": token, "user": {"id": user_id, "email": email, "name": name, "picture": picture}}

@app.get("/auth/me")
async def get_me(user: dict = Depends(get_current_user)):
    return {"id": user["sub"], "email": user["email"], "name": user["name"], "picture": user["picture"]}

# ---------------------------------------------------------------------------
# PDF endpoints
# ---------------------------------------------------------------------------
@app.post("/upload")
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    file_id = str(uuid.uuid4())
    path = f"./uploads/{file_id}.pdf"
    os.makedirs("./uploads", exist_ok=True)

    with open(path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Save to DB
    conn = get_db()
    conn.execute(
        "INSERT INTO pdfs (id, user_id, filename, status) VALUES (?, ?, ?, ?)",
        (file_id, user["sub"], file.filename, "processing"),
    )
    conn.commit()
    conn.close()

    # Track status
    job_status[file_id] = {"status": "processing", "error": None}

    # Process in background (no Redis needed!)
    background_tasks.add_task(_process_and_update, path, file_id)

    return {"job_id": file_id, "filename": file.filename}

def _process_and_update(path: str, file_id: str):
    """Background task wrapper that updates status."""
    try:
        result = process_pdf(path, file_id)
        job_status[file_id] = {"status": "done", "error": None}
        conn = get_db()
        conn.execute("UPDATE pdfs SET status = 'done' WHERE id = ?", (file_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        job_status[file_id] = {"status": "failed", "error": str(e)}
        conn = get_db()
        conn.execute("UPDATE pdfs SET status = 'failed', error = ? WHERE id = ?", (str(e), file_id))
        conn.commit()
        conn.close()

@app.get("/status/{job_id}")
async def get_status(job_id: str):
    status = job_status.get(job_id)
    if not status:
        # Check DB
        conn = get_db()
        row = conn.execute("SELECT status, error FROM pdfs WHERE id = ?", (job_id,)).fetchone()
        conn.close()
        if row:
            return {"status": row["status"], "error": row["error"]}
        raise HTTPException(status_code=404, detail="Job not found")
    return status

class AskRequest(BaseModel):
    job_id: str
    question: str
    history: list = []

@app.post("/ask")
async def ask_question_endpoint(
    req: AskRequest,
    user: dict = Depends(get_current_user),
):
    try:
        result = answer_question(req.job_id, req.question, req.history)
        # result is now {"answer": str, "sources": list}
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/pdf/{job_id}")
def serve_pdf(job_id: str):
    path = f"./uploads/{job_id}.pdf"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(path, media_type="application/pdf")

@app.get("/my-pdfs")
async def get_my_pdfs(user: dict = Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute(
        "SELECT id, filename, status, error, created_at FROM pdfs WHERE user_id = ? ORDER BY created_at DESC",
        (user["sub"],),
    ).fetchall()
    conn.close()
    return {
        "pdfs": [
            {
                "file_id": row["id"],
                "filename": row["filename"],
                "status": row["status"],
                "error": row["error"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]
    }

@app.delete("/pdf/{job_id}")
async def delete_pdf(job_id: str, user: dict = Depends(get_current_user)):
    conn = get_db()
    row = conn.execute("SELECT user_id FROM pdfs WHERE id = ?", (job_id,)).fetchone()
    if not row or row["user_id"] != user["sub"]:
        conn.close()
        raise HTTPException(status_code=404, detail="PDF not found")
    conn.execute("DELETE FROM pdfs WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()

    # Clean up files
    pdf_path = f"./uploads/{job_id}.pdf"
    vec_path = f"./vectorstores/{job_id}.pkl"
    for p in [pdf_path, vec_path]:
        if os.path.exists(p):
            os.remove(p)

    return {"detail": "Deleted"}

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}
