# from fastapi import APIRouter, UploadFile, File, Form, Depends, BackgroundTasks, HTTPException, status, Query
# from sqlalchemy.orm import Session
# from database.session import SessionLocal
# from database.models import PDF, PDFChunk, User
# from utils.storage import store_pdf_file
# from utils.background import process_pdf_background
# from utils.search import search_pdf_chunks
# from schemas.pdf import PDFResponse, PDFChunkResponse, SearchResponse, PDFCreate
# from typing import List
# from fastapi.security import OAuth2PasswordBearer
# from jose import JWTError, jwt
# import os

# router = APIRouter(prefix="/api/pdfs")

# @router.get("/search", response_model=SearchResponse)
# def search_endpoint(query: str = Query(...), user_id: int = None):
#     return search_pdf_chunks(query, user_id)

# oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")
# SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key")
# ALGORITHM = "HS256"

# def get_db():
#     db = SessionLocal()
#     try:
#         yield db
#     finally:
#         db.close()

# def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
#     credentials_exception = HTTPException(
#         status_code=status.HTTP_401_UNAUTHORIZED,
#         detail="Could not validate credentials",
#         headers={"WWW-Authenticate": "Bearer"},
#     )
#     try:
#         payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
#         username: str = payload.get("sub")
#         if username is None:
#             raise credentials_exception
#     except JWTError:
#         raise credentials_exception
#     user = db.query(User).filter(User.username == username).first()
#     if user is None:
#         raise credentials_exception
#     return user

# @router.post("/upload", response_model=PDFResponse)
# async def upload_pdf(
#     background_tasks: BackgroundTasks,
#     file: UploadFile = File(...),
#     title: str = Form(...),
#     description: str = Form(None),
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user)
# ):
#     document_link = await store_pdf_file(file)
#     pdf = PDF(
#         title=title,
#         description=description,
#         document_link=document_link,
#         user_id=current_user.id,
#         processing_status="pending"
#     )
#     db.add(pdf)
#     db.commit()
#     db.refresh(pdf)
#     # Dispatch background task with Celery
#     process_pdf_background.delay(pdf.id, document_link)
#     return PDFResponse(**pdf.__dict__)

# @router.get("/user/{user_id}", response_model=List[PDFResponse])
# def get_pdfs_for_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
#     if current_user.id != user_id:
#         raise HTTPException(403, "Not authorized to view these PDFs")
#     pdfs = db.query(PDF).filter(PDF.user_id == user_id).all()
#     return [PDFResponse(**pdf.__dict__) for pdf in pdfs]

# @router.get("/{pdf_id}", response_model=PDFResponse)
# def get_pdf(pdf_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
#     pdf = db.query(PDF).get(pdf_id)
#     if not pdf or pdf.user_id != current_user.id:
#         raise HTTPException(404, "PDF not found")
#     return PDFResponse(**pdf.__dict__)

# @router.get("/{pdf_id}/chunks", response_model=List[PDFChunkResponse])
# def get_chunks(pdf_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
#     pdf = db.query(PDF).get(pdf_id)
#     if not pdf or pdf.user_id != current_user.id:
#         raise HTTPException(404, "PDF not found")
#     chunks = db.query(PDFChunk).filter(PDFChunk.pdf_id == pdf_id).all()
#     return [PDFChunkResponse(**chunk.__dict__) for chunk in chunks]

# @router.get("/{pdf_id}/processing-status")
# def get_processing_status(pdf_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
#     pdf = db.query(PDF).get(pdf_id)
#     if not pdf or pdf.user_id != current_user.id:
#         raise HTTPException(404, "PDF not found")
#     return {"processing_status": pdf.processing_status, "error_message": pdf.error_message}

# @router.get("/search", response_model=SearchResponse)
# def search(query: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
#     return search_pdf_chunks(query)