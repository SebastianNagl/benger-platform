"""Storage and CDN services.

Canonical home (issue #158): relocated from services/api/services/storage so the
export/import worker — whose image carries only services/workers/* + /shared —
can import the same ObjectStorageService singleton. /shared is first on sys.path
in both containers, so ``from storage.object_storage import object_storage``
resolves here. The old ``services/api/services/storage/*`` paths remain as thin
re-export shims that bind to this same module (singleton identity preserved).
"""
