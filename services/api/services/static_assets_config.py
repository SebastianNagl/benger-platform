"""
Static assets configuration for CDN delivery
"""

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class StaticAssetsManager:
    """Manages static assets for CDN delivery"""

    def __init__(
        self,
        assets_dir: str,
        manifest_file: str = "assets-manifest.json",
        cdn_base_url: Optional[str] = None,
    ):
        self.assets_dir = Path(assets_dir)
        self.manifest_file = self.assets_dir / manifest_file
        self.cdn_base_url = cdn_base_url
        self.manifest = self._load_manifest()

    def _load_manifest(self) -> Dict[str, Dict[str, str]]:
        """Load assets manifest with versioning info"""
        if self.manifest_file.exists():
            try:
                with open(self.manifest_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load assets manifest: {e}")
        return {}

    def _save_manifest(self):
        """Save assets manifest"""
        try:
            with open(self.manifest_file, "w") as f:
                json.dump(self.manifest, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save assets manifest: {e}")

    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate hash of file content for versioning"""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()[:8]  # Use first 8 chars

    def scan_assets(self) -> Dict[str, Dict[str, str]]:
        """Scan assets directory and update manifest"""
        new_manifest = {}

        # Define asset patterns to include
        asset_patterns = [
            "**/*.js",
            "**/*.css",
            "**/*.jpg",
            "**/*.jpeg",
            "**/*.png",
            "**/*.gif",
            "**/*.svg",
            "**/*.woff",
            "**/*.woff2",
            "**/*.ttf",
            "**/*.eot",
        ]

        for pattern in asset_patterns:
            for file_path in self.assets_dir.glob(pattern):
                if file_path.is_file():
                    relative_path = file_path.relative_to(self.assets_dir)
                    file_hash = self._calculate_file_hash(file_path)

                    # Create versioned filename
                    base_name = file_path.stem
                    extension = file_path.suffix
                    versioned_name = f"{base_name}.{file_hash}{extension}"

                    new_manifest[str(relative_path)] = {
                        "hash": file_hash,
                        "versioned": versioned_name,
                        "size": file_path.stat().st_size,
                        "mtime": file_path.stat().st_mtime,
                    }

        self.manifest = new_manifest
        self._save_manifest()
        return new_manifest

    def get_asset_url(self, asset_path: str) -> str:
        """Get CDN URL for an asset with cache busting"""
        # Normalize path
        asset_path = asset_path.lstrip("/")

        # Check if asset is in manifest
        if asset_path in self.manifest:
            # Use versioned filename for cache busting
            versioned = self.manifest[asset_path]["versioned"]
            dir_path = os.path.dirname(asset_path)

            if dir_path:
                versioned_path = f"{dir_path}/{versioned}"
            else:
                versioned_path = versioned

            if self.cdn_base_url:
                return f"{self.cdn_base_url}/{versioned_path}"
            else:
                return f"/static/{versioned_path}"

        # Fallback to original path
        if self.cdn_base_url:
            return f"{self.cdn_base_url}/{asset_path}"
        else:
            return f"/static/{asset_path}"

    def get_assets_for_upload(self) -> List[Dict[str, str]]:
        """Get list of assets that need to be uploaded to CDN"""
        assets = []

        for relative_path, info in self.manifest.items():
            file_path = self.assets_dir / relative_path
            if file_path.exists():
                assets.append(
                    {
                        "local_path": str(file_path),
                        "cdn_path": info["versioned"],
                        "original_path": relative_path,
                        "hash": info["hash"],
                        "size": info["size"],
                    }
                )

        return assets

    def generate_nginx_rewrite_rules(self) -> str:
        """Generate nginx rewrite rules for versioned assets"""
        rules = []
        rules.append("# Auto-generated asset rewrite rules")
        rules.append("# Rewrite versioned assets to original files")

        for original, info in self.manifest.items():
            versioned = info["versioned"]
            # Escape special characters in regex
            versioned_escaped = versioned.replace(".", r"\.")
            rules.append(f"rewrite ^/static/{versioned_escaped}$ /static/{original} last;")

        return "\n".join(rules)


def sync_assets_to_cdn(
    assets_manager: StaticAssetsManager, storage_service, cdn_service=None
) -> Dict[str, int]:
    """Sync static assets to CDN storage"""

    # Scan assets
    assets_manager.scan_assets()
    assets = assets_manager.get_assets_for_upload()

    uploaded = 0
    errors = 0

    for asset in assets:
        try:
            # Read file content
            with open(asset["local_path"], "rb") as f:
                content = f.read()

            # Upload to storage
            result = storage_service.upload_file(
                file_data=content,
                filename=asset["versioned"],
                user_id="system",
                file_type="static",
                metadata={
                    "original_path": asset["original_path"],
                    "content_hash": asset["hash"],
                },
            )

            logger.info(f"Uploaded asset: {asset['original_path']} -> {asset['versioned']}")
            uploaded += 1

        except Exception as e:
            logger.error(f"Failed to upload asset {asset['original_path']}: {e}")
            errors += 1

    # Warm CDN cache if configured
    if cdn_service and uploaded > 0:
        cdn_paths = [f"static/{asset['versioned']}" for asset in assets]
        cdn_service.warm_cache(cdn_paths)

    return {"uploaded": uploaded, "errors": errors}
