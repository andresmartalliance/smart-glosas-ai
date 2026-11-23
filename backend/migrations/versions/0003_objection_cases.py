"""Create tenant-scoped objection workflow; retire demo-only table.

Revision ID: 0003_objection_cases
Revises: 0002_synthetic_history
"""
from alembic import op
from app.models import ObjectionCase

revision = "0003_objection_cases"
down_revision = "0002_synthetic_history"
branch_labels = None
depends_on = None

def upgrade():
    ObjectionCase.__table__.create(bind=op.get_bind(), checkfirst=True)
    op.execute("DROP TABLE IF EXISTS synthetic_glosas")

def downgrade():
    ObjectionCase.__table__.drop(bind=op.get_bind(), checkfirst=True)
    # Old demonstration-only data is deliberately not restored.
