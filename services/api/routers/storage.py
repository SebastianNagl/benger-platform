"""
Storage and CDN endpoints.
Handles file uploads, downloads, multipart uploads, and CDN operations.
"""

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth_module import User, require_superadmin, require_user
from cdn_service import cdn_service
from database import get_db
from models import OrganizationMembership, UploadedData
from object_storage import object_storage
from project_models import Project

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/storage", tags=["storage"])


# ============= Pydantic Models =============


class MultipartUrlsRequest(BaseModel):
    file_key: str
    upload_id: str
    part_numbers: List[int]


class MultipartCompleteRequest(BaseModel):
    file_key: str
    upload_id: str
    parts: List[Dict[str, Any]]
    metadata: Optional[Dict[str, Any]] = None


class CDNInvalidateRequest(BaseModel):
    paths: List[str]
    wait: bool = False


# ============= Storage Endpoints =============


@router.post("/upload-url")
async def get_upload_url(
    filename: str,
    file_type: str = "uploads",
    content_type: Optional[str] = None,
    max_size: Optional[int] = 10 * 1024 * 1024,  # 10MB default
    current_user: User = Depends(require_user),
):
    """Generate presigned URL for direct file upload to object storage"""
    try:
        upload_info = object_storage.get_upload_url(
            filename=filename,
            file_type=file_type,
            user_id=str(current_user.id),
            content_type=content_type,
            max_size=max_size,
        )

        return upload_info

    except Exception as e:
        logger.error(f"Failed to generate upload URL: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate upload URL: {str(e)}",
        )


@router.post("/upload")
async def upload_file_to_storage(
    file: UploadFile = File(...),
    file_type: str = Form("uploads"),
    metadata: Optional[str] = Form(None),
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Upload file to object storage (for environments without direct upload)"""
    try:
        # Read file content
        file_data = await file.read()

        # Parse metadata if provided
        file_metadata = {}
        if metadata:
            try:
                file_metadata = json.loads(metadata)
            except json.JSONDecodeError:
                pass

        # Upload to object storage
        upload_result = object_storage.upload_file(
            file_data=file_data,
            filename=file.filename,
            file_type=file_type,
            user_id=str(current_user.id),
            content_type=file.content_type,
            metadata=file_metadata,
        )

        # Store file reference in database
        uploaded_data = UploadedData(
            id=str(uuid.uuid4()),
            name=file.filename,
            original_filename=file.filename,
            file_path=upload_result["file_key"],  # Store object storage key
            size=upload_result["size"],
            format=(file.filename.split(".")[-1] if "." in file.filename else "unknown"),
            uploaded_by=current_user.id,
            storage_backend=upload_result.get("storage_backend", "local"),
            storage_url=upload_result["url"],
            file_metadata=file_metadata,
        )

        db.add(uploaded_data)
        db.commit()

        return {
            "id": uploaded_data.id,
            "file_key": upload_result["file_key"],
            "url": upload_result["url"],
            "size": upload_result["size"],
            "content_type": upload_result["content_type"],
            "uploaded_at": upload_result["uploaded_at"],
        }

    except Exception as e:
        logger.error(f"Failed to upload file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload file: {str(e)}",
        )


@router.get("/download-url/{file_id}")
async def get_download_url(
    file_id: str,
    expires_in: Optional[int] = 86400,  # 24 hours default
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Generate presigned URL for file download"""
    try:
        # Get file record from database
        uploaded_data = db.query(UploadedData).filter(UploadedData.id == file_id).first()

        if not uploaded_data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

        # Check access permissions
        # Allow access if user is the uploader or superadmin
        if uploaded_data.uploaded_by == current_user.id or current_user.is_superadmin:
            pass  # Access granted
        elif uploaded_data.task_id:
            # If file is associated with a task, check if user has access to that task
            task = db.query(Project).filter(Project.id == uploaded_data.task_id).first()
            if not task:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Associated task not found",
                )

            # Check if user has access to the task through organization membership
            user_org_ids = (
                db.query(OrganizationMembership.organization_id)
                .filter(
                    OrganizationMembership.user_id == current_user.id,
                    OrganizationMembership.is_active == True,
                )
                .all()
            )
            user_org_ids = [org.organization_id for org in user_org_ids]

            # Check if user is in any of the task's organizations
            if task.organization_ids:
                task_org_ids = (
                    task.organization_ids if isinstance(task.organization_ids, list) else []
                )
                if not any(org_id in user_org_ids for org_id in task_org_ids):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Access denied: not a member of task organization",
                    )
            else:
                # Project has no organization restrictions, deny access for non-uploaders
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        else:
            # File not associated with task and user is not uploader
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

        # Generate download URL
        download_url = object_storage.get_download_url(
            file_key=uploaded_data.file_path,
            expires_in=expires_in,
            response_content_disposition=f'attachment; filename="{uploaded_data.original_filename}"',
        )

        return {
            "url": download_url,
            "filename": uploaded_data.original_filename,
            "size": uploaded_data.size,
            "expires_at": (datetime.now() + timedelta(seconds=expires_in)).isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate download URL: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate download URL: {str(e)}",
        )


@router.delete("/file/{file_id}")
async def delete_file_from_storage(
    file_id: str,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Delete file from object storage"""
    try:
        # Get file record from database
        uploaded_data = db.query(UploadedData).filter(UploadedData.id == file_id).first()

        if not uploaded_data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

        # Check permissions
        if uploaded_data.uploaded_by != current_user.id and not current_user.is_superadmin:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

        # Delete from object storage
        success = object_storage.delete_file(uploaded_data.file_path)

        if success:
            # Delete from database
            db.delete(uploaded_data)
            db.commit()

            return {"message": "File deleted successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete file from storage",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete file: {str(e)}",
        )


# ============= Multipart Upload Endpoints =============


@router.post("/multipart/init")
async def init_multipart_upload(
    filename: str,
    file_type: str = "uploads",
    content_type: Optional[str] = None,
    current_user: User = Depends(require_user),
):
    """Initialize multipart upload for large files"""
    try:
        upload_info = object_storage.create_multipart_upload(
            filename=filename,
            file_type=file_type,
            user_id=str(current_user.id),
            content_type=content_type,
        )

        return upload_info

    except Exception as e:
        logger.error(f"Failed to initialize multipart upload: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize multipart upload: {str(e)}",
        )


@router.post("/multipart/urls")
async def get_multipart_urls(
    request: MultipartUrlsRequest,
    current_user: User = Depends(require_user),
):
    """Get presigned URLs for multipart upload parts"""
    try:
        urls = object_storage.get_multipart_upload_urls(
            file_key=request.file_key,
            upload_id=request.upload_id,
            part_numbers=request.part_numbers,
        )

        return {"urls": urls}

    except Exception as e:
        logger.error(f"Failed to get multipart URLs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get multipart URLs: {str(e)}",
        )


@router.post("/multipart/complete")
async def complete_multipart_upload(
    request: MultipartCompleteRequest,
    current_user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Complete multipart upload and create database record"""
    try:
        # Complete multipart upload
        result = object_storage.complete_multipart_upload(
            file_key=request.file_key, upload_id=request.upload_id, parts=request.parts
        )

        # Extract filename from file_key
        filename = request.file_key.split("/")[-1]

        # Store file reference in database
        uploaded_data = UploadedData(
            id=str(uuid.uuid4()),
            name=filename,
            original_filename=(
                request.metadata.get("original_filename", filename)
                if request.metadata
                else filename
            ),
            file_path=request.file_key,
            size=result.get("size", 0),
            format=filename.split(".")[-1] if "." in filename else "unknown",
            uploaded_by=current_user.id,
            storage_backend=result["storage_backend"],
            file_metadata=request.metadata,
        )

        db.add(uploaded_data)
        db.commit()

        return {
            "id": uploaded_data.id,
            "file_key": request.file_key,
            "size": result.get("size", 0),
            "etag": result.get("etag"),
            "completed_at": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to complete multipart upload: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to complete multipart upload: {str(e)}",
        )


# ============= CDN Endpoints =============


@router.post("/cdn/invalidate")
async def invalidate_cdn_cache(
    request: CDNInvalidateRequest,
    current_user: User = Depends(require_superadmin),
):
    """Invalidate CDN cache for specified paths (admin only)"""
    try:
        invalidation_id = cdn_service.invalidate_cache(request.paths, request.wait)

        if invalidation_id:
            return {
                "invalidation_id": invalidation_id,
                "paths": request.paths,
                "status": "completed" if request.wait else "initiated",
            }
        else:
            return {
                "message": "CDN invalidation not available",
                "cdn_enabled": cdn_service.cdn_enabled,
            }

    except Exception as e:
        logger.error(f"Failed to invalidate CDN cache: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to invalidate CDN cache: {str(e)}",
        )


@router.get("/cdn/assets/{path:path}")
async def get_cdn_asset_url(path: str):
    """Get CDN URL for a static asset"""
    try:
        cdn_url = cdn_service.get_asset_url(f"/{path}")

        return {
            "asset_path": path,
            "cdn_url": cdn_url,
            "cdn_enabled": cdn_service.cdn_enabled,
        }

    except Exception as e:
        logger.error(f"Failed to get CDN asset URL: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get CDN asset URL: {str(e)}",
        )


# ============= Health Check Endpoints =============


@router.get("/health")
@router.get("/cdn/health")
async def check_storage_cdn_health(current_user: User = Depends(require_superadmin)):
    """Check health of object storage and CDN services (admin only)"""
    try:
        storage_health = object_storage.health_check()
        cdn_health = cdn_service.health_check()

        return {
            "storage": storage_health,
            "cdn": cdn_health,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to check storage/CDN health: {e}")
        return {"error": str(e), "timestamp": datetime.now().isoformat()}
