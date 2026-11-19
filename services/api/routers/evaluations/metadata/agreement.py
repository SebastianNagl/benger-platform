"""Inter-annotator agreement over a project's overlapping annotations."""
from ._common import *  # noqa: F401,F403  (binds _common.__all__ — the shared surface)


class AnnotatorPairAgreement(BaseModel):
    """Agreement of two annotators over the tasks both answered."""

    annotator_a: str
    annotator_b: str
    n_items: int
    cohens_kappa: Optional[float] = None
    pearson_r: Optional[float] = None


class ControlAgreement(BaseModel):
    """Agreement for one control (Label Studio ``from_name``).

    Categorical and ordinal controls (``choices``, ``rating``) carry the
    kappa fields and percent agreement; numeric controls (``number``) carry
    Pearson's r and the mean absolute deviation. ``pairs`` lists at most
    ``annotator_agreement.MAX_PAIRS_PER_CONTROL`` pairs, the ones with the
    most shared tasks first; ``pairs_total`` counts all of them.
    """

    control: str
    type: str
    score_type: str
    multi_select: bool = False
    n_items: int
    n_annotators: int
    n_annotations: int
    categories: List[str] = []
    fleiss_kappa: Optional[float] = None
    cohens_kappa_mean: Optional[float] = None
    percent_agreement: Optional[float] = None
    pearson_r_mean: Optional[float] = None
    mean_absolute_deviation: Optional[float] = None
    pairs: List[AnnotatorPairAgreement] = []
    pairs_total: int = 0


class UnsupportedControl(BaseModel):
    control: str
    type: str


class AnnotatorAgreementResponse(BaseModel):
    """Per-control agreement; ``available`` is false when no task has two annotators."""

    available: bool
    overlap_task_count: int = 0
    annotator_count: int = 0
    controls: List[ControlAgreement] = []
    unsupported_controls: List[UnsupportedControl] = []


@router.get(
    "/projects/{project_id}/annotator-agreement",
    response_model=AnnotatorAgreementResponse,
)
async def get_annotator_agreement(
    project_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_user),
):
    """Agreement between annotators per control, over tasks with two or more annotators.

    Uses ``bg_statistics.compute_agreement`` (Fleiss and pairwise Cohen's
    kappa, percent agreement; Pearson's r and mean absolute deviation for
    number controls). Annotators are shown by pseudonym.
    """
    from annotator_agreement import project_annotator_agreement

    project = (
        await db.execute(select(Project.id).where(Project.id == project_id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found",
        )
    if not await check_project_accessible_async(db, current_user, project_id):
        raise HTTPException(status_code=403, detail="Access denied")

    result = await db.run_sync(lambda sync_db: project_annotator_agreement(sync_db, project_id))
    if result is None:
        return AnnotatorAgreementResponse(available=False)
    return AnnotatorAgreementResponse(available=True, **result)
