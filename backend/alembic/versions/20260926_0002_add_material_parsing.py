"""add material parsing tables

Revision ID: 20260926_0002
Revises: 20260926_0001
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260926_0002"
down_revision: str | Sequence[str] | None = "20260926_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "verification_task",
        sa.Column("schema_version", sa.String(length=16), nullable=False, server_default="1.0"),
    )
    op.add_column(
        "verification_task",
        sa.Column("warning_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("verification_task", sa.Column("error_code", sa.String(length=64), nullable=True))
    op.add_column("verification_task", sa.Column("error_message", sa.Text(), nullable=True))

    op.create_table(
        "task_file",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("category", sa.String(length=31), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("storage_path", sa.String(length=512), nullable=False),
        sa.Column("declared_mime", sa.String(length=127), nullable=False),
        sa.Column("detected_mime", sa.String(length=127), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("parse_status", sa.String(length=31), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["verification_task.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "sha256", name="uq_task_file_task_sha256"),
    )
    op.create_index("ix_task_file_task_id", "task_file", ["task_id"])

    op.create_table(
        "document_block",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_file_id", sa.String(length=36), nullable=False),
        sa.Column("block_id", sa.String(length=64), nullable=False),
        sa.Column("block_type", sa.String(length=31), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("heading_path", sa.JSON(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("locator", sa.JSON(), nullable=False),
        sa.Column("related_asset_ids", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["task_file_id"], ["task_file.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_file_id", "block_id", name="uq_document_block_file_block"),
    )
    op.create_index("ix_document_block_task_file_id", "document_block", ["task_file_id"])

    op.create_table(
        "template_comment",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_file_id", sa.String(length=36), nullable=False),
        sa.Column("comment_id", sa.String(length=64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("selected_text", sa.Text(), nullable=False),
        sa.Column("heading_path", sa.JSON(), nullable=False),
        sa.Column("anchor_block_id", sa.String(length=64), nullable=True),
        sa.Column("context_before", sa.Text(), nullable=True),
        sa.Column("context_after", sa.Text(), nullable=True),
        sa.Column("locator", sa.JSON(), nullable=False),
        sa.Column("warning_codes", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["task_file_id"], ["task_file.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_file_id", "comment_id", name="uq_template_comment_file_comment"),
    )
    op.create_index("ix_template_comment_task_file_id", "template_comment", ["task_file_id"])

    op.create_table(
        "document_asset",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_file_id", sa.String(length=36), nullable=False),
        sa.Column("asset_id", sa.String(length=64), nullable=False),
        sa.Column("media_type", sa.String(length=127), nullable=False),
        sa.Column("storage_path", sa.String(length=512), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("relationship_id", sa.String(length=64), nullable=True),
        sa.Column("locator", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["task_file_id"], ["task_file.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_file_id", "asset_id", name="uq_document_asset_file_asset"),
    )
    op.create_index("ix_document_asset_task_file_id", "document_asset", ["task_file_id"])

    op.create_table(
        "parse_warning",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("task_file_id", sa.String(length=36), nullable=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("locator", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["task_file_id"], ["task_file.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["verification_task.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_parse_warning_task_id", "parse_warning", ["task_id"])
    op.create_index("ix_parse_warning_task_file_id", "parse_warning", ["task_file_id"])

    op.create_table(
        "project_metadata",
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("normalized_data", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["verification_task.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("task_id"),
    )


def downgrade() -> None:
    op.drop_table("project_metadata")
    op.drop_index("ix_parse_warning_task_file_id", table_name="parse_warning")
    op.drop_index("ix_parse_warning_task_id", table_name="parse_warning")
    op.drop_table("parse_warning")
    op.drop_index("ix_document_asset_task_file_id", table_name="document_asset")
    op.drop_table("document_asset")
    op.drop_index("ix_template_comment_task_file_id", table_name="template_comment")
    op.drop_table("template_comment")
    op.drop_index("ix_document_block_task_file_id", table_name="document_block")
    op.drop_table("document_block")
    op.drop_index("ix_task_file_task_id", table_name="task_file")
    op.drop_table("task_file")
    op.drop_column("verification_task", "error_message")
    op.drop_column("verification_task", "error_code")
    op.drop_column("verification_task", "warning_count")
    op.drop_column("verification_task", "schema_version")
