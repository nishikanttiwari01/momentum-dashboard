"""Merge heads 20250921_01 & 20250912_0002

Revision ID: d65fc156cce6
Revises: 20250921_01, 20250912_0002
Create Date: 2025-09-21 18:18:05.814541

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd65fc156cce6'
down_revision = ('20250921_01', '20250912_0002')
branch_labels = None
depends_on = None

def upgrade():
    pass

def downgrade():
    pass
