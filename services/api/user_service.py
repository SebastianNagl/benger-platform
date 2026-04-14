"""
Backward-compatible shim — canonical implementation in auth_module.user_service

All user service functions have been consolidated into auth_module/user_service.py
as part of Issue #1207 (API Architecture Cleanup). This file re-exports everything
for backward compatibility with any remaining imports.
"""

from auth_module.user_service import *  # noqa: F401, F403
