"""${message}
Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from typing import Union
from alembic import op
import sqlalchemy as sa
revision: str = ${repr(up_revision)}
down_revision: Union[str,None] = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}
def upgrade(): ${upgrades if upgrades else 'pass'}
def downgrade(): ${downgrades if downgrades else 'pass'}
