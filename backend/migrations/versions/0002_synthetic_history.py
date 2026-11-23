"""Synthetic-only persistent workflow history.
Revision ID: 0002_synthetic_history
Revises: 0001_initial
"""
from alembic import op
from app.models import SyntheticGlosa

revision = "0002_synthetic_history"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

def upgrade():
    SyntheticGlosa.__table__.create(bind=op.get_bind(), checkfirst=True)

def downgrade():
    SyntheticGlosa.__table__.drop(bind=op.get_bind(), checkfirst=True)
