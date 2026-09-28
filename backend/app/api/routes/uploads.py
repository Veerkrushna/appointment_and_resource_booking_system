from fastapi import APIRouter, UploadFile, File, HTTPException
import uuid
import os
import shutil

router = APIRouter(prefix="/api/upload", tags=["Upload"])

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/image")
async def upload_image(file: UploadFile = File(...)):
    if not (file.filename.endswith('.jpg') or file.filename.endswith('.jpeg')):
        raise HTTPException(status_code=400, detail="Only .jpg and .jpeg files are allowed.")
    
    # Generate unique filename
    ext = os.path.splitext(file.filename)[1]
    filename = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(UPLOAD_DIR, filename)
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Could not save file")
    
    return {"url": f"/uploads/{filename}"}
