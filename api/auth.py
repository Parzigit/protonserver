# from fastapi import FastAPI, WebSocket
# from api.pdfs import router as pdf_router
# from api.auth import router as auth_router
# from websocket.chat_server import handle_chat

# app = FastAPI()
# app.include_router(pdf_router)
# app.include_router(auth_router)

# @app.websocket("/ws/chat/{pdf_id}")
# async def websocket_endpoint(websocket: WebSocket, pdf_id: int):
#     await handle_chat(websocket, pdf_id)