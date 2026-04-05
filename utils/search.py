# from sqlalchemy.orm import Session
# from database.models import PDFChunk, PDF
# from database.session import SessionLocal
# from schemas.pdf import SearchResponse, SearchResult
# from sentence_transformers import SentenceTransformer
# from sklearn.metrics.pairwise import cosine_similarity
# import numpy as np

# embedder = SentenceTransformer("all-MiniLM-L6-v2")

# def search_pdf_chunks(query: str, user_id: int = None) -> SearchResponse:
#     db = SessionLocal()
#     try:
#         query_emb = embedder.encode([query])[0]
#         # Optionally filter by user_id, or fetch all
#         chunks_query = db.query(PDFChunk)
#         if user_id:
#             chunks_query = chunks_query.join(PDF).filter(PDF.user_id == user_id)
#         chunks = chunks_query.all()

#         if not chunks:
#             return SearchResponse(query=query, results=[], count=0)

#         chunk_contents = [c.content for c in chunks]
#         chunk_embeddings = np.array([c.embedding for c in chunks])
#         similarities = cosine_similarity([query_emb], chunk_embeddings)[0]

#         top_indices = similarities.argsort()[::-1][:10]
#         results = []
#         for idx in top_indices:
#             c = chunks[idx]
#             pdf = db.query(PDF).get(c.pdf_id)
#             results.append(SearchResult(
#                 pdf_id=c.pdf_id,
#                 pdf_title=pdf.title if pdf else "",
#                 chunk_id=c.id,
#                 content=c.content,
#                 page_number=c.page_number,
#                 similarity=float(similarities[idx]),
#                 metadata=c.metadata,
#             ))
#         return SearchResponse(query=query, results=results, count=len(results))
#     finally:
#         db.close()