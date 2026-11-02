"""Which vision model transcribes a project's handwritten solution uploads.

The organization keeps a default in ``organizations.settings`` under
:data:`SETTINGS_KEY` (JSON column, no migration; set through
``PUT /organizations/{id}/ocr-model``). A project switches handwritten
uploads on with ``projects.handwriting_ocr_enabled`` and may override the
model with ``projects.handwriting_ocr_model`` (NULL = follow the
organization). The OCR flow itself is an extended feature; this module is
the generic lookup both the api and the workers use.
"""

from typing import Any, Mapping, Optional

SETTINGS_KEY = "handwriting_ocr_model"
MAX_MODEL_ID_LENGTH = 255


def org_ocr_model(settings: Optional[Mapping[str, Any]]) -> Optional[str]:
    """The organization's default OCR model id, or None."""
    if isinstance(settings, Mapping):
        value = settings.get(SETTINGS_KEY)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def with_ocr_model(settings: Optional[Mapping[str, Any]], model_id: Optional[str]) -> dict:
    """A copy of ``settings`` with the default set (None/blank removes it)."""
    out = dict(settings) if isinstance(settings, Mapping) else {}
    model = (model_id or "").strip()
    if model:
        if len(model) > MAX_MODEL_ID_LENGTH:
            raise ValueError("model id too long")
        out[SETTINGS_KEY] = model
    else:
        out.pop(SETTINGS_KEY, None)
    return out


def project_org_ocr_model(db, project) -> Optional[str]:
    """The first default among the project's organizations (stable order)."""
    from models import Organization
    from project_models import ProjectOrganization

    rows = (
        db.query(Organization.settings)
        .join(ProjectOrganization, ProjectOrganization.organization_id == Organization.id)
        .filter(ProjectOrganization.project_id == project.id)
        .order_by(Organization.id)
        .all()
    )
    for (settings,) in rows:
        model = org_ocr_model(settings)
        if model:
            return model
    return None


def effective_ocr_model(db, project) -> Optional[str]:
    """The model an OCR job of ``project`` runs, or None when handwritten
    uploads are off (switch off, or no project model and no org default)."""
    if project is None or not getattr(project, "handwriting_ocr_enabled", False):
        return None
    override = getattr(project, "handwriting_ocr_model", None)
    if isinstance(override, str) and override.strip():
        return override.strip()
    return project_org_ocr_model(db, project)
