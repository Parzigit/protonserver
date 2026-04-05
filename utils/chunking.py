# from database.models import PDFChunk
# from database.session import SessionLocal
# from datetime import datetime
# from transformers import AutoTokenizer
# from sentence_transformers import SentenceTransformer

# tokenizer = AutoTokenizer.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")
# embedder = SentenceTransformer("all-MiniLM-L6-v2")

# def split_text_into_chunks(text, max_tokens=500):
#     sentences = text.split('. ')
#     chunks = []
#     current_chunk = ""
#     current_tokens = 0

#     for sentence in sentences:
#         tokens = tokenizer.encode(sentence, add_special_tokens=False)
#         if current_tokens + len(tokens) > max_tokens:
#             if current_chunk:
#                 chunks.append(current_chunk.strip())
#             current_chunk = sentence + ". "
#             current_tokens = len(tokens)
#         else:
#             current_chunk += sentence + ". "
#             current_tokens += len(tokens)
#     if current_chunk:
#         chunks.append(current_chunk.strip())
#     return chunks

# def chunk_pdf_and_store(pdf_id: int, text: str, page_map: dict = None):
#     db = SessionLocal()
#     try:
#         chunks = split_text_into_chunks(text)
#         embeddings = embedder.encode(chunks, convert_to_numpy=True).tolist()
#         for i, chunk in enumerate(chunks):
#             db_chunk = PDFChunk(
#                 pdf_id=pdf_id,
#                 content=chunk,
#                 chunk_index=i,
#                 page_number=page_map.get(i) if page_map else None,
#                 metadata={},
#                 embedding=embeddings[i],
#                 created_at=datetime.utcnow()
#             )
#             db.add(db_chunk)
#         db.commit()
#     finally:
#         db.close()