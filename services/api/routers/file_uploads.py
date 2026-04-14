"""
File upload endpoints with object storage support
"""

import logging
import mimetypes
import os
import uuid
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth_module import User, require_user
from database import get_db
from models import UploadedData
from object_storage import object_storage

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/files", tags=["files"])

# Use the global object storage service (already initialized)


class FileUploadResponse(BaseModel):
    """Response model for file upload"""

    id: str
    name: str
    size: int
    format: str
    url: str
    cdn_url: Optional[str] = None
    upload_date: str


class FileListResponse(BaseModel):
    """Response model for file listing"""

    id: str
    name: str
    size: int
    format: str
    upload_date: str
    task_id: Optional[str] = None
    url: str
    cdn_url: Optional[str] = None


@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    task_id: Optional[str] = None,
    description: Optional[str] = None,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """
    Upload a file to object storage

    Supports various file types and automatically handles storage backend
    (local filesystem, S3, MinIO, etc.) based on configuration.
    """
    try:
        # Validate file
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="No filename provided"
            )

        # Check file size (limit to 100MB)
        file_content = await file.read()
        file_size = len(file_content)

        if file_size > 100 * 1024 * 1024:  # 100MB
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File size exceeds 100MB limit",
            )

        # Get file format
        file_format = os.path.splitext(file.filename)[1].lstrip(".") or "unknown"
        mime_type = mimetypes.guess_type(file.filename)[0] or "application/octet-stream"

        # Upload to object storage
        storage_result = object_storage.upload_file(
            file_data=file_content,
            filename=file.filename,
            file_type="uploads",
            user_id=current_user.id,
            content_type=mime_type,
            metadata={
                "task_id": task_id or "",
                "description": description or "",
                "uploaded_by": current_user.username,
            },
        )

        # CDN URL is automatically handled by object_storage for static files
        cdn_url = None
        if object_storage.cdn_enabled and storage_result.get("file_key", "").startswith("static/"):
            cdn_url = f"https://{object_storage.cdn_domain}/{object_storage.cdn_prefix}/{storage_result['file_key']}".replace(
                "//", "/"
            )

        # Create database record
        file_record = UploadedData(
            id=str(uuid.uuid4()),
            name=file.filename,
            original_filename=file.filename,
            file_path=storage_result["file_key"],  # Keep for backward compatibility
            storage_key=storage_result["file_key"],
            storage_url=storage_result["url"],
            cdn_url=cdn_url,
            file_hash=storage_result["hash"],
            storage_type=object_storage.storage_backend,
            size=file_size,
            format=file_format,
            description=description,
            task_id=task_id,
            uploaded_by=current_user.id,
        )

        db.add(file_record)
        db.commit()
        db.refresh(file_record)

        logger.info(f"File uploaded successfully: {file_record.id} ({file.filename})")

        return FileUploadResponse(
            id=file_record.id,
            name=file_record.name,
            size=file_record.size,
            format=file_record.format,
            url=file_record.storage_url or storage_result["url"],
            cdn_url=file_record.cdn_url,
            upload_date=file_record.upload_date.isoformat(),
        )

    except Exception as e:
        logger.error(f"Error uploading file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload file: {str(e)}",
        )


@router.get("/", response_model=List[FileListResponse])
async def list_files(
    task_id: Optional[str] = None,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """List uploaded files for the current user"""
    try:
        # Build query
        query = db.query(UploadedData).filter(UploadedData.uploaded_by == current_user.id)

        if task_id:
            query = query.filter(UploadedData.task_id == task_id)

        files = query.order_by(UploadedData.upload_date.desc()).all()

        # Convert to response format
        result = []
        for file in files:
            # Generate fresh URL if needed
            if file.storage_key and not file.storage_url:
                try:
                    file.storage_url = object_storage.get_download_url(file.storage_key)
                except:
                    pass

            result.append(
                FileListResponse(
                    id=file.id,
                    name=file.name,
                    size=file.size,
                    format=file.format,
                    upload_date=file.upload_date.isoformat(),
                    task_id=file.task_id,
                    url=file.storage_url or f"/files/{file.id}/download",
                    cdn_url=file.cdn_url,
                )
            )

        return result

    except Exception as e:
        logger.error(f"Error listing files: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list files: {str(e)}",
        )


@router.get("/{file_id}/download")
async def download_file(
    file_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Download a file or get its download URL"""
    try:
        # Get file record
        file_record = (
            db.query(UploadedData)
            .filter(UploadedData.id == file_id, UploadedData.uploaded_by == current_user.id)
            .first()
        )

        if not file_record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

        # If using object storage, return presigned URL
        if file_record.storage_key:
            url = object_storage.get_download_url(file_record.storage_key, expires_in=3600)

            # Return redirect to presigned URL
            from fastapi.responses import RedirectResponse

            return RedirectResponse(url=url, status_code=302)

        # Fallback for old files using file_path
        if file_record.file_path and os.path.exists(file_record.file_path):
            from fastapi.responses import FileResponse

            return FileResponse(
                path=file_record.file_path,
                filename=file_record.original_filename,
                media_type=mimetypes.guess_type(file_record.original_filename)[0],
            )

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File data not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download file: {str(e)}",
        )


@router.delete("/{file_id}")
async def delete_file(
    file_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Delete an uploaded file"""
    try:
        # Get file record
        file_record = (
            db.query(UploadedData)
            .filter(UploadedData.id == file_id, UploadedData.uploaded_by == current_user.id)
            .first()
        )

        if not file_record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

        # Delete from storage in background
        if file_record.storage_key:
            background_tasks.add_task(object_storage.delete_file, file_record.storage_key)

        # Delete database record
        db.delete(file_record)
        db.commit()

        logger.info(f"File deleted: {file_id}")

        return {"message": "File deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete file: {str(e)}",
        )
