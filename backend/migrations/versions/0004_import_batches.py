"""Record each import and enable clearing institution-specific uploads.

Revision ID: 0004_import_batches
Revises: 0003_objection_cases
"""
from alembic import op
import sqlalchemy as sa
from app.models import ImportBatch

revision = "0004_import_batches"
down_revision = "0003_objection_cases"
branch_labels = None
depends_on = None

def upgrade():
    ImportBatch.__table__.create(bind=op.get_bind(), checkfirst=True)
    op.add_column("objection_cases", sa.Column("batch_id", sa.String(36), nullable=True))
    op.create_index("ix_objection_cases_batch_id", "objection_cases", ["batch_id"])
    op.create_foreign_key("fk_objection_batch", "objection_cases",
                          "import_batches", ["batch_id"], ["id"], ondelete="SET NULL")

def downgrade():
    op.drop_constraint("fk_objection_batch", "objection_cases", type_="foreignkey")
    op.drop_index("ix_objection_cases_batch_id", table_name="objection_cases")
    op.drop_column("objection_cases", "batch_id")
    ImportBatch.__table__.drop(bind=op.get_bind(), checkfirst=True)
