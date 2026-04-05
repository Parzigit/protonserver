# from fastapi import WebSocket, WebSocketDisconnect, Depends
# from database.session import SessionLocal
# from database.models import PDF, PDFChunk, User
# from utils.auth import decode_access_token
# from utils.search import search_pdf_chunks

# async def get_current_user_ws(websocket: WebSocket):
#     token = websocket.cookies.get("access_token") or websocket.headers.get("Authorization", "").replace("Bearer ", "")
#     payload = decode_access_token(token)
#     if not payload:
#         await websocket.close(1008)
#         return None
#     db = SessionLocal()
#     user = db.query(User).filter(User.username == payload.get("sub")).first()
#     db.close()
#     if not user:
#         await websocket.close(1008)
#         return None
#     return user

# async def handle_chat(websocket: WebSocket, pdf_id: int):
#     await websocket.accept()
#     user = await get_current_user_ws(websocket)
#     db = SessionLocal()
#     pdf = db.query(PDF).get(pdf_id)
#     db.close()
#     if not pdf or pdf.user_id != user.id:
#         await websocket.close(1008)
#         return
#     try:
#         while True:
#             data = await websocket.receive_text()
#             # Use your search logic for top chunks as context, then generate LLM answer
#             context_chunks = search_pdf_chunks(data)
#             # TODO: Call your LLM answer function here using context_chunks
#             answer = "[LLM-generated answer based on context chunks]"
#             await websocket.send_text(answer)
#     except WebSocketDisconnect:
#         pass