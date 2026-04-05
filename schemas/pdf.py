# from pydantic import BaseModel
# from typing import Optional, List, Dict, Any
# from datetime import datetime

# class PDFBase(BaseModel):
#     title: str
#     description: Optional[str] = None
#     document_link: str

# class PDFCreate(PDFBase):
#     user_id: int

# class PDFResponse(PDFBase):
#     id: int
#     created_at: datetime
#     updated_at: datetime
#     user_id: int
#     processing_status: str = "pending"
#     processing_progress: Optional[float] = 0
#     total_pages: Optional[int] = None
#     error_message: Optional[str] = None
#     indexing_step: Optional[str] = None
#     chunks_processed: Optional[int] = None
#     embeddings_created: Optional[int] = None

# class PDFChunkBase(BaseModel):
#     content: str
#     chunk_index: int
#     page_number: Optional[int] = None
#     metadata: Optional[Dict[str, Any]] = None

# class PDFChunkCreate(PDFChunkBase):
#     pdf_id: int

# class PDFChunkResponse(PDFChunkBase):
#     id: int
#     created_at: datetime
#     pdf_id: int

# class SearchResult(BaseModel):
#     pdf_id: int
#     pdf_title: str
#     chunk_id: int
#     content: str
#     page_number: Optional[int] = None
#     similarity: float
#     metadata: Optional[Dict[str, Any]] = None

# class SearchResponse(BaseModel):
#     query: str
#     results: List[SearchResult]
#     count: int

# class UserCreate(BaseModel):
#     username: str
#     password: str

# class UserResponse(BaseModel):
#     id: int
#     username: str