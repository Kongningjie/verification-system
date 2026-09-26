"""add review records and reports

Revision ID: 20260926_0005
Revises: 20260926_0004
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260926_0005"
down_revision: str | Sequence[str] | None = "20260926_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "review_record",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("result_id", sa.String(36), nullable=False),
        sa.Column("reviewer_name", sa.String(255), nullable=False),
        sa.Column("previous_conclusion", sa.String(31), nullable=False),
        sa.Column("new_conclusion", sa.String(31), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["result_id"], ["check_result.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["verification_task.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_record_task_id", "review_record", ["task_id"])
    op.create_index("ix_review_record_result_id", "review_record", ["result_id"])
    op.create_table(
        "report",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("format", sa.String(31), nullable=False),
        sa.Column("status", sa.String(31), nullable=False),
        sa.Column("relative_path", sa.String(512), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["verification_task.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_report_task_id", "report", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_report_task_id", table_name="report")
    op.drop_table("report")
    op.drop_index("ix_review_record_result_id", table_name="review_record")
    op.drop_index("ix_review_record_task_id", table_name="review_record")
    op.drop_table("review_record")
