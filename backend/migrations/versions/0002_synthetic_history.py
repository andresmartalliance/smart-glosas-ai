"""Legacy migration record. Demonstration tables are retired in revision 0003.

Revision ID: 0002_synthetic_history
Revises: 0001_initial
"""
revision = "0002_synthetic_history"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

def upgrade():
    # An ephemeral demonstration table is no longer provisioned.
    pass

def downgrade():
    pass
