"""Rename dell switch table for Flask-SQLAlchemy

See the docstring in 'haas/migrations/versions/6a8c19565060_move_to_flask.py'

Revision ID: 099b939261c1
Revises:
Create Date: 2016-03-22 04:34:49.141555

"""
from alembic import op
import sqlalchemy as sa
from hil.model import db
from hil.flaskapp import app

# revision identifiers, used by Alembic.
revision = '099b939261c1'
down_revision = None
branch_labels = ('haas.ext.switches.dell',)


def upgrade():
    metadata = sa.MetaData(bind=db.get_engine(app), reflect=True)
    if 'powerconnect55xx' in metadata.tables:
        op.rename_table('powerconnect55xx', 'power_connect55xx')


def downgrade():
    op.rename_table('power_connect55xx', 'powerconnect55xx')
