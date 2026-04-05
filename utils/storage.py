# import os
# import aiofiles
# from fastapi import UploadFile

# UPLOAD_FOLDER = "pdf_storage"
# os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# async def store_pdf_file(file: UploadFile) -> str:
#     file_path = os.path.join(UPLOAD_FOLDER, file.filename)
#     async with aiofiles.open(file_path, "wb") as out:
#         content = await file.read()
#         await out.write(content)
#     return file_path