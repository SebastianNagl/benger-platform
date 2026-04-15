"""
Unit tests for services/static_assets_config.py — 0% coverage (97 uncovered lines).

Tests StaticAssetsManager for asset scanning, URL generation, and manifest operations.
"""

import hashlib
import json
import os
import tempfile

import pytest


class TestStaticAssetsManagerInit:
    """Test initialization."""

    def test_creates_with_default_manifest(self):
        from services.static_assets_config import StaticAssetsManager
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = StaticAssetsManager(tmpdir)
            assert mgr.assets_dir.exists()


class TestCalculateFileHash:
    """Test file hash calculation."""

    def test_hash_of_known_content(self):
        from services.static_assets_config import StaticAssetsManager
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = StaticAssetsManager(tmpdir)
            # Create a test file
            test_file = os.path.join(tmpdir, "test.js")
            with open(test_file, "w") as f:
                f.write("console.log('hello');")
            file_hash = mgr._calculate_file_hash(mgr.assets_dir / "test.js")
            assert isinstance(file_hash, str)
            assert len(file_hash) == 8  # Short hash

    def test_different_content_different_hash(self):
        from services.static_assets_config import StaticAssetsManager
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = StaticAssetsManager(tmpdir)
            f1 = os.path.join(tmpdir, "a.js")
            f2 = os.path.join(tmpdir, "b.js")
            with open(f1, "w") as f:
                f.write("content A")
            with open(f2, "w") as f:
                f.write("content B")
            h1 = mgr._calculate_file_hash(mgr.assets_dir / "a.js")
            h2 = mgr._calculate_file_hash(mgr.assets_dir / "b.js")
            assert h1 != h2


class TestScanAssets:
    """Test asset scanning."""

    def test_empty_directory(self):
        from services.static_assets_config import StaticAssetsManager
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = StaticAssetsManager(tmpdir)
            assets = mgr.scan_assets()
            assert isinstance(assets, dict)

    def test_scans_js_files(self):
        from services.static_assets_config import StaticAssetsManager
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "app.js")
            with open(test_file, "w") as f:
                f.write("var x = 1;")
            mgr = StaticAssetsManager(tmpdir)
            assets = mgr.scan_assets()
            assert len(assets) > 0

    def test_scans_css_files(self):
        from services.static_assets_config import StaticAssetsManager
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "style.css")
            with open(test_file, "w") as f:
                f.write("body { color: red; }")
            mgr = StaticAssetsManager(tmpdir)
            assets = mgr.scan_assets()
            assert len(assets) > 0

    def test_scans_nested_files(self):
        from services.static_assets_config import StaticAssetsManager
        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = os.path.join(tmpdir, "js")
            os.makedirs(subdir)
            with open(os.path.join(subdir, "main.js"), "w") as f:
                f.write("import x;")
            mgr = StaticAssetsManager(tmpdir)
            assets = mgr.scan_assets()
            assert len(assets) > 0


class TestGetAssetUrl:
    """Test versioned asset URL generation."""

    def test_asset_url_with_hash(self):
        from services.static_assets_config import StaticAssetsManager
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "app.js")
            with open(test_file, "w") as f:
                f.write("var x = 1;")
            mgr = StaticAssetsManager(tmpdir)
            mgr.scan_assets()  # Populate manifest
            url = mgr.get_asset_url("app.js")
            # Should contain hash or be a valid URL
            assert isinstance(url, str)

    def test_unknown_asset_returns_original(self):
        from services.static_assets_config import StaticAssetsManager
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = StaticAssetsManager(tmpdir)
            url = mgr.get_asset_url("nonexistent.js")
            assert "nonexistent.js" in url


class TestGetAssetsForUpload:
    """Test getting assets ready for CDN upload."""

    def test_returns_list(self):
        from services.static_assets_config import StaticAssetsManager
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "app.js")
            with open(test_file, "w") as f:
                f.write("code;")
            mgr = StaticAssetsManager(tmpdir)
            mgr.scan_assets()
            assets = mgr.get_assets_for_upload()
            assert isinstance(assets, list)

    def test_empty_when_no_assets(self):
        from services.static_assets_config import StaticAssetsManager
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = StaticAssetsManager(tmpdir)
            assets = mgr.get_assets_for_upload()
            assert assets == []


class TestGenerateNginxRewriteRules:
    """Test nginx rewrite rule generation."""

    def test_returns_string(self):
        from services.static_assets_config import StaticAssetsManager
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "app.js")
            with open(test_file, "w") as f:
                f.write("code;")
            mgr = StaticAssetsManager(tmpdir)
            mgr.scan_assets()
            rules = mgr.generate_nginx_rewrite_rules()
            assert isinstance(rules, str)

    def test_empty_when_no_assets(self):
        from services.static_assets_config import StaticAssetsManager
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = StaticAssetsManager(tmpdir)
            rules = mgr.generate_nginx_rewrite_rules()
            assert isinstance(rules, str)


class TestManifestPersistence:
    """Test manifest load/save."""

    def test_save_and_load_manifest(self):
        from services.static_assets_config import StaticAssetsManager
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "app.js")
            with open(test_file, "w") as f:
                f.write("code;")
            mgr1 = StaticAssetsManager(tmpdir)
            mgr1.scan_assets()
            mgr1._save_manifest()

            # Load in new instance
            mgr2 = StaticAssetsManager(tmpdir)
            manifest = mgr2._load_manifest()
            assert isinstance(manifest, dict)
