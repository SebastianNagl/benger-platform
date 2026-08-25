"""backfill projects.kind from label-config structure

The extended edition's student surfaces (Entdecken, deck/exam listings) key
discovery off the explicit ``projects.kind`` flag as the single source of
truth; the old structural detection (Klausurlösung-shaped config for exams,
``$front``-bound config + front/back card data for decks) is demoted to
owner-facing validation warnings. This one-time backfill stamps the kind on
pre-existing kind-NULL rows so projects that were discoverable (or meant to
be) under the structural rules stay reachable under the flag rule:

- ``kind='exam'``: label config uses the Klausurlösung component set
  (detected via the ``<Angabe`` tag — deliberately a broad LIKE; owners can
  clear a wrong flag via the now-editable kind control).
- ``kind='flashcard_collection'``: config binds ``$front``, is not
  Klausurlösung-shaped, and at least one task actually carries front/back
  card keys.

Consequence worth knowing (extended edition): ``kind='exam'`` denies the
FULL access tier to ANNOTATOR-role org members (participant tier instead)
and removes the project from their generic project browser — deliberate for
teaching exams, accepted for finished annotation campaigns.

Community edition: the flags themselves change no community behavior (kind
is only read by the ``?kind=`` list filter there); the backfill is inert
noise at worst.

Irreversible by design: downgrade cannot know which rows were NULL before,
and clearing flags would hide student-visible exams. ``downgrade`` is a
no-op.

Revision ID: 094_backfill_project_kind
Revises: 093_add_project_soft_delete
"""

from alembic import op

revision = "094_backfill_project_kind"
down_revision = "093_add_project_soft_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE projects
           SET kind = 'exam'
         WHERE kind IS NULL
           AND label_config LIKE '%<Angabe%'
        """
    )
    # ::jsonb cast keeps the `?` key-exists operator working even where the
    # column is plain json (test shims); on prod it is already jsonb.
    op.execute(
        """
        UPDATE projects
           SET kind = 'flashcard_collection'
         WHERE kind IS NULL
           AND label_config LIKE '%$front%'
           AND label_config NOT LIKE '%<Angabe%'
           AND EXISTS (
                 SELECT 1
                   FROM tasks t
                  WHERE t.project_id = projects.id
                    AND t.data::jsonb ? 'front'
                    AND t.data::jsonb ? 'back'
               )
        """
    )


def downgrade() -> None:
    # Irreversible data backfill (see module docstring).
    pass
