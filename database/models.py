# from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON, Float
# from sqlalchemy.orm import relationship, declarative_base
# from datetime import datetime

# Base = declarative_base()

# class User(Base):
#     __tablename__ = "users"
#     id = Column(Integer, primary_key=True)
#     username = Column(String(50), unique=True, nullable=False)
#     hashed_password = Column(String(255), nullable=False)

# class PDF(Base):
#     __tablename__ = "pdfs"
#     id = Column(Integer, primary_key=True)
#     title = Column(String(200))
#     description = Column(Text)
#     document_link = Column(String(500))
#     user_id = Column(Integer, ForeignKey("users.id"))
#     created_at = Column(DateTime, default=datetime.utcnow)
#     updated_at = Column(DateTime, default=datetime.utcnow)
#     processing_status = Column(String(50), default="pending")
#     processing_progress = Column(Float, default=0)
#     error_message = Column(Text)
#     user = relationship("User")

# class PDFChunk(Base):
#     __tablename__ = "pdf_chunks"
#     id = Column(Integer, primary_key=True)
#     pdf_id = Column(Integer, ForeignKey("pdfs.id"))
#     content = Column(Text)
#     chunk_index = Column(Integer)
#     page_number = Column(Integer)
#     chunk_metadata = Column(JSON)  # <-- renamed here!
#     created_at = Column(DateTime, default=datetime.utcnow)
#     embedding = Column(JSON)  # Store embedding as JSON list
#     pdf = relationship("PDF")