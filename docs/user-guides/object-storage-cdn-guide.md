# Object Storage and CDN Implementation Guide

This guide covers the implementation of object storage and CDN functionality in BenGER, providing scalable file handling and global content delivery.

## Overview

BenGER's object storage and CDN system provides:
- **Scalable File Storage**: S3-compatible object storage for all file types
- **CDN Integration**: Global content delivery with cache management
- **Secure Access**: Presigned URLs and access control
- **Multi-backend Support**: Local, S3, MinIO, and custom storage backends
- **Performance Optimization**: Asset versioning and cache management

## Architecture

```
Frontend ──┬─→ Direct Upload (Presigned URLs) ──→ Object Storage (S3/MinIO)
           │                                      │
           └─→ API Upload ────────────────────────┼─→ Database (Metadata)
                                                  │
Users ─────────→ CDN (CloudFront/Cloudflare) ────┴─→ Static Assets
```

## Components

### Object Storage Service (`object_storage.py`)

The core service that handles all file operations:

```python
from object_storage import object_storage

# Upload a file
result = object_storage.upload_file(
    file_data=file_content,
    filename="document.pdf",
    file_type="uploads",
    user_id="user123"
)

# Generate presigned upload URL
upload_info = object_storage.get_upload_url(
    filename="large-file.zip",
    file_type="uploads",
    user_id="user123",
    max_size=100 * 1024 * 1024  # 100MB
)

# Generate download URL
download_url = object_storage.get_download_url(
    file_key="uploads/2025/07/14/user123/document.pdf",
    expires_in=3600
)
```

### CDN Service (`cdn_service.py`)

Manages CDN configuration and cache operations:

```python
from cdn_service import cdn_service

# Get CDN URL for static asset
cdn_url = cdn_service.get_asset_url("/js/app.js")

# Invalidate cache
invalidation_id = cdn_service.invalidate_cache([
    "/static/*",
    "/api/tasks/*"
])

# Check invalidation status
status = cdn_service.get_invalidation_status(invalidation_id)
```

## Configuration

### Environment Variables

Create `.env` file with storage and CDN configuration:

```bash
# Storage Backend
STORAGE_BACKEND=s3  # 'local', 's3', 'minio'

# S3/MinIO Configuration
S3_BUCKET_NAME=benger-production-storage
S3_REGION=us-east-1
S3_ACCESS_KEY_ID=your-access-key
S3_SECRET_ACCESS_KEY=your-secret-key
S3_ENDPOINT_URL=  # Leave empty for AWS S3, set for MinIO

# CDN Configuration
CDN_PROVIDER=cloudfront  # 'none', 'cloudfront', 'cloudflare', 'custom'
CDN_ENABLED=true
CDN_DOMAIN=cdn.benger.example.com

# CloudFront (if using)
CLOUDFRONT_DISTRIBUTION_ID=E1234567890ABC
CLOUDFRONT_KEY_PAIR_ID=KEYPAIRID123
CLOUDFRONT_PRIVATE_KEY_PATH=/path/to/private-key.pem

# Cloudflare (if using)
CLOUDFLARE_ZONE_ID=zone123456
CLOUDFLARE_API_TOKEN=your-api-token
```

### Development Setup

For local development:

```bash
# Use local storage
STORAGE_BACKEND=local
LOCAL_STORAGE_PATH=/tmp/benger-storage

# Disable CDN
CDN_PROVIDER=none
CDN_ENABLED=false
```

### Production Setup

#### Option 1: AWS S3 + CloudFront

```bash
STORAGE_BACKEND=s3
S3_BUCKET_NAME=benger-production-storage
S3_REGION=us-east-1
# Set AWS credentials

CDN_PROVIDER=cloudfront
CDN_ENABLED=true
CDN_DOMAIN=cdn.benger.example.com
CLOUDFRONT_DISTRIBUTION_ID=your-distribution-id
```

#### Option 2: MinIO + Cloudflare

```bash
STORAGE_BACKEND=minio
S3_ENDPOINT_URL=https://minio.benger.example.com
S3_BUCKET_NAME=benger-storage
# Set MinIO credentials

CDN_PROVIDER=cloudflare
CDN_ENABLED=true
CDN_DOMAIN=cdn.benger.example.com
CLOUDFLARE_ZONE_ID=your-zone-id
CLOUDFLARE_API_TOKEN=your-api-token
```

## API Endpoints

### File Upload

#### Get Presigned Upload URL

```http
POST /storage/upload-url
Authorization: Bearer <token>
Content-Type: application/x-www-form-urlencoded

filename=document.pdf&file_type=uploads&content_type=application/pdf&max_size=10485760
```

Response:
```json
{
  "upload_url": "https://benger-storage.s3.amazonaws.com/",
  "method": "POST",
  "file_key": "uploads/2025/07/14/user123/20250714_120000_document.pdf",
  "fields": {
    "key": "uploads/2025/07/14/user123/20250714_120000_document.pdf",
    "Content-Type": "application/pdf"
  },
  "expires_at": "2025-07-14T13:00:00Z"
}
```

#### Direct Upload via API

```http
POST /storage/upload
Authorization: Bearer <token>
Content-Type: multipart/form-data

file: (binary data)
file_type: uploads
metadata: {"description": "Important document"}
```

Response:
```json
{
  "id": "file-uuid-123",
  "file_key": "uploads/2025/07/14/user123/document.pdf",
  "url": "https://benger-storage.s3.amazonaws.com/signed-url",
  "size": 1048576,
  "content_type": "application/pdf",
  "uploaded_at": "2025-07-14T12:00:00Z"
}
```

### File Download

#### Get Download URL

```http
GET /storage/download-url/{file_id}?expires_in=3600
Authorization: Bearer <token>
```

Response:
```json
{
  "url": "https://benger-storage.s3.amazonaws.com/signed-download-url",
  "filename": "document.pdf",
  "size": 1048576,
  "expires_at": "2025-07-14T13:00:00Z"
}
```

### Multipart Upload (Large Files)

#### Initialize Multipart Upload

```http
POST /storage/multipart/init
Authorization: Bearer <token>

{
  "filename": "large-video.mp4",
  "file_type": "uploads",
  "content_type": "video/mp4"
}
```

#### Get Part Upload URLs

```http
POST /storage/multipart/urls
Authorization: Bearer <token>

{
  "file_key": "uploads/large-video.mp4",
  "upload_id": "upload123",
  "part_numbers": [1, 2, 3, 4, 5]
}
```

#### Complete Upload

```http
POST /storage/multipart/complete
Authorization: Bearer <token>

{
  "file_key": "uploads/large-video.mp4",
  "upload_id": "upload123",
  "parts": [
    {"PartNumber": 1, "ETag": "\"part1-etag\""},
    {"PartNumber": 2, "ETag": "\"part2-etag\""}
  ],
  "metadata": {"original_filename": "large-video.mp4"}
}
```

### CDN Management

#### Invalidate Cache (Admin Only)

```http
POST /cdn/invalidate
Authorization: Bearer <admin-token>

{
  "paths": ["/static/*", "/api/tasks/*"],
  "wait": false
}
```

#### Get Asset CDN URL

```http
GET /cdn/assets/js/app.js
```

Response:
```json
{
  "asset_path": "js/app.js",
  "cdn_url": "https://cdn.benger.example.com/js/app.abc123.js?v=20250714",
  "cdn_enabled": true
}
```

## File Organization

Files are automatically organized by type and date:

```
bucket/
├── uploads/
│   └── 2025/
│       └── 07/
│           └── 14/
│               └── user123/
│                   └── 20250714_120000_document.pdf
├── exports/
│   └── 2025/
│       └── 07/
│           └── task_export_20250714_120000.json
├── static/
│   └── assets/
│       ├── js/
│       ├── css/
│       └── images/
└── backups/
    └── 2025/
        └── 07/
            └── database_backup_20250714.sql
```

## Security

### Access Control

- **Presigned URLs**: Temporary, signed URLs for secure direct access
- **User Isolation**: Files organized by user ID with access controls
- **Time-limited Access**: Configurable expiration times for URLs
- **Role-based Permissions**: Different access levels based on user roles

### File Validation

```python
# Example validation in upload endpoint
if not file.filename.endswith(('.pdf', '.docx', '.txt')):
    raise HTTPException(400, "Invalid file type")

if file.size > 10 * 1024 * 1024:  # 10MB
    raise HTTPException(400, "File too large")
```

### Signed URLs for Private Content

```python
# Generate signed URL for private content
download_url = object_storage.get_download_url(
    file_key="private/sensitive-document.pdf",
    expires_in=1800,  # 30 minutes
    response_content_disposition='attachment; filename="document.pdf"'
)
```

## Performance Optimization

### Asset Versioning

Static assets are automatically versioned for cache busting:

```python
# Automatic asset fingerprinting
versioned_url = cdn_service.get_asset_url("/js/app.js")
# Result: https://cdn.example.com/js/app.abc123.js?v=20250714
```

### Cache Control Headers

Different cache policies for different content types:

```python
cache_headers = cdn_service.get_cache_headers("static")
# Result: {"Cache-Control": "public, max-age=31536000, immutable"}

cache_headers = cdn_service.get_cache_headers("documents")
# Result: {"Cache-Control": "private, max-age=3600"}
```

### Cache Warming

Pre-warm CDN cache for critical assets:

```python
urls = [
    "https://cdn.example.com/js/app.js",
    "https://cdn.example.com/css/styles.css"
]
results = cdn_service.warm_cache(urls)
```

## Monitoring and Health Checks

### Storage Health Check

```http
GET /storage/health
Authorization: Bearer <admin-token>
```

Response:
```json
{
  "storage": {
    "healthy": true,
    "storage_backend": "s3",
    "details": {
      "bucket": "benger-production-storage",
      "endpoint": "AWS S3"
    }
  },
  "cdn": {
    "healthy": true,
    "cdn_enabled": true,
    "cdn_provider": "cloudfront",
    "details": {
      "cdn_domain": "cdn.benger.example.com",
      "distribution_status": "Deployed"
    }
  },
  "timestamp": "2025-07-14T12:00:00Z"
}
```

### Metrics to Monitor

- **Upload Success Rate**: Percentage of successful uploads
- **Download Response Time**: Average time to generate download URLs
- **Cache Hit Rate**: CDN cache effectiveness
- **Storage Costs**: Monthly storage and bandwidth usage
- **Error Rates**: Failed operations by type

## Migration from Local Storage

### Step 1: Deploy with Dual Storage

```bash
# Enable both local and object storage
STORAGE_BACKEND=s3
# Keep existing local files accessible
```

### Step 2: Migrate Existing Files

```python
# Migration script example
from object_storage import object_storage
from models import UploadedData

for file_record in db.query(UploadedData).filter(
    UploadedData.storage_backend == "local"
):
    # Read local file
    with open(file_record.file_path, 'rb') as f:
        file_data = f.read()
    
    # Upload to object storage
    result = object_storage.upload_file(
        file_data=file_data,
        filename=file_record.original_filename,
        file_type="uploads",
        user_id=str(file_record.uploaded_by)
    )
    
    # Update database record
    file_record.storage_backend = "s3"
    file_record.file_path = result["file_key"]
    file_record.storage_url = result["url"]
    
    db.commit()
```

### Step 3: Update Application Configuration

```bash
# Remove local storage path
# STORAGE_BACKEND=s3 (already set)

# Enable CDN
CDN_ENABLED=true
CDN_DOMAIN=cdn.benger.example.com
```

## Troubleshooting

### Common Issues

#### S3 Connection Errors

```
Error: Failed to initialize s3 storage: Unable to locate credentials
```

**Solution**: Verify AWS credentials are set:
```bash
export AWS_ACCESS_KEY_ID=your-key
export AWS_SECRET_ACCESS_KEY=your-secret
# Or use IAM roles
```

#### CDN Cache Not Updating

```
Problem: Static assets not updating despite new deployment
```

**Solution**: Invalidate CDN cache:
```bash
curl -X POST "https://api.benger.example.com/cdn/invalidate" \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"paths": ["/static/*"]}'
```

#### Large File Upload Failures

```
Error: Request timeout during file upload
```

**Solution**: Use multipart upload for files > 5MB:
```javascript
// Frontend implementation
const uploadLargeFile = async (file) => {
  // 1. Initialize multipart upload
  const initResponse = await fetch('/storage/multipart/init', {
    method: 'POST',
    body: new URLSearchParams({
      filename: file.name,
      content_type: file.type
    })
  });
  
  // 2. Upload parts in parallel
  // 3. Complete upload
};
```

### Performance Issues

#### Slow Download Speeds

**Diagnosis**: Check CDN cache hit rates
**Solution**: 
1. Verify CDN configuration
2. Warm cache for frequently accessed files
3. Optimize cache headers

#### High Storage Costs

**Diagnosis**: Review storage usage by file type
**Solution**:
1. Implement file lifecycle policies
2. Archive old files to cheaper storage tiers
3. Clean up unused files

## Best Practices

### File Upload

1. **Validate file types** and sizes before upload
2. **Use presigned URLs** for direct browser uploads
3. **Implement progress tracking** for large files
4. **Handle upload failures** gracefully with retry logic
5. **Generate unique filenames** to prevent conflicts

### Security

1. **Never expose storage credentials** to frontend
2. **Use time-limited presigned URLs**
3. **Implement proper access controls**
4. **Scan uploaded files** for malware
5. **Encrypt sensitive files** at rest

### Performance

1. **Use CDN for static assets**
2. **Implement proper cache headers**
3. **Optimize image sizes** and formats
4. **Use multipart uploads** for large files
5. **Monitor and optimize** storage costs

### Monitoring

1. **Track upload/download metrics**
2. **Monitor storage usage** and costs
3. **Set up alerts** for errors
4. **Regular health checks**
5. **Backup critical files**

## Integration with Frontend

### React File Upload Component

```typescript
import { useCallback } from 'react';

const FileUploader = () => {
  const uploadFile = useCallback(async (file: File) => {
    try {
      // Get presigned upload URL
      const uploadResponse = await fetch('/storage/upload-url', {
        method: 'POST',
        body: new URLSearchParams({
          filename: file.name,
          file_type: 'uploads',
          content_type: file.type
        })
      });
      
      const uploadInfo = await uploadResponse.json();
      
      // Upload directly to storage
      const formData = new FormData();
      Object.entries(uploadInfo.fields).forEach(([key, value]) => {
        formData.append(key, value as string);
      });
      formData.append('file', file);
      
      const uploadResult = await fetch(uploadInfo.upload_url, {
        method: 'POST',
        body: formData
      });
      
      if (uploadResult.ok) {
        console.log('Upload successful!');
      }
    } catch (error) {
      console.error('Upload failed:', error);
    }
  }, []);
  
  return (
    <input
      type="file"
      onChange={(e) => {
        const file = e.target.files?.[0];
        if (file) uploadFile(file);
      }}
    />
  );
};
```

### CDN Asset Helper

```typescript
const getCDNUrl = async (assetPath: string): Promise<string> => {
  const response = await fetch(`/cdn/assets${assetPath}`);
  const data = await response.json();
  return data.cdn_url;
};

// Usage
const appJsUrl = await getCDNUrl('/js/app.js');
// Result: https://cdn.benger.example.com/js/app.abc123.js?v=20250714
```

This comprehensive object storage and CDN system provides BenGER with enterprise-grade file handling capabilities, ensuring scalability, performance, and security for all file operations.