"""add merchant is_test flag for archiving E2E/test merchants

Revision ID: 8f2c1a9b4d7e
Revises: 06c7dad78bad
Create Date: 2026-09-04

The live demo database accumulates merchants created by E2E test runs
(unique emails per run, no expected_outcome ground truth). These dilute
the /admin/batch-test accuracy report with "could not score" rows. This
migration adds Merchant.is_test and backfills it: any merchant-role
account WITHOUT an expected_outcome audit entry is test data (the seeded
ground-truth merchants all have one), so it gets flagged and excluded
from the batch test + admin queue.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8f2c1a9b4d7e'
down_revision: Union[str, Sequence[str], None] = '06c7dad78bad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Idempotent: db.py's init_db() safety net (_ensure_is_test_column)
    # may already have added this column when seed.py runs standalone
    # before migrations. Skip the ALTER in that case so re-running this
    # migration never fails with DuplicateColumn.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("merchants")}
    if "is_test" not in columns:
        with op.batch_alter_table('merchants', schema=None) as batch_op:
            batch_op.add_column(sa.Column('is_test', sa.Boolean(), nullable=False, server_default=sa.false()))

    # Backfill: merchants without an expected_outcome audit entry are
    # E2E/test-created accounts and can never be scored by batch-test.
    # is_test is BOOLEAN — bind a real boolean, because PostgreSQL rejects
    # `SET boolean_col = 1` with DatatypeMismatch (SQLite tolerates it,
    # which hid this bug until the first live PG deploy). op.execute() in
    # alembic >= 1.13 no longer accepts bind params, so run it through the
    # migration connection directly.
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE merchants SET is_test = :val "
            "WHERE role = 'merchant' AND id NOT IN "
            "(SELECT merchant_id FROM audit_logs WHERE action = 'expected_outcome')"
        ),
        {"val": True},
    )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('merchants', schema=None) as batch_op:
        batch_op.drop_column('is_test')