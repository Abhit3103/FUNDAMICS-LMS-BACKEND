"""academic_board_notices_and_settings

Revision ID: a1b2c3d4e5f6
Revises: 549197cf5a09
Create Date: 2026-10-14 01:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '549197cf5a09'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add board column to classes
    op.add_column('classes', sa.Column('board', sa.String(length=50), nullable=False, server_default='CBSE'))

    # 2. Add document_file_id column to results
    op.add_column('results', sa.Column('document_file_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_results_document_file_id'), 'results', ['document_file_id'], unique=False)
    op.create_foreign_key('fk_results_document_file_id_files', 'results', 'files', ['document_file_id'], ['id'], ondelete='SET NULL')

    # 3. Add institute_status and erp_messaging_enabled to institute_settings
    op.add_column('institute_settings', sa.Column('institute_status', sa.String(length=30), nullable=False, server_default='OPEN'))
    op.add_column('institute_settings', sa.Column('erp_messaging_enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')))

    # 4. Create notices table
    op.create_table(
        'notices',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('target_audience', sa.String(length=50), nullable=False, server_default='ALL'),
        sa.Column('class_id', sa.UUID(), nullable=True),
        sa.Column('batch_id', sa.UUID(), nullable=True),
        sa.Column('priority', sa.String(length=30), nullable=False, server_default='NORMAL'),
        sa.Column('attachment_file_id', sa.UUID(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['attachment_file_id'], ['files.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['batch_id'], ['batches.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['class_id'], ['classes.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_notices_id'), 'notices', ['id'], unique=False)
    op.create_index(op.f('ix_notices_is_active'), 'notices', ['is_active'], unique=False)
    op.create_index(op.f('ix_notices_class_id'), 'notices', ['class_id'], unique=False)
    op.create_index(op.f('ix_notices_batch_id'), 'notices', ['batch_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_notices_batch_id'), table_name='notices')
    op.drop_index(op.f('ix_notices_class_id'), table_name='notices')
    op.drop_index(op.f('ix_notices_is_active'), table_name='notices')
    op.drop_index(op.f('ix_notices_id'), table_name='notices')
    op.drop_table('notices')

    op.drop_column('institute_settings', 'erp_messaging_enabled')
    op.drop_column('institute_settings', 'institute_status')

    op.drop_constraint('fk_results_document_file_id_files', 'results', type_='foreignkey')
    op.drop_index(op.f('ix_results_document_file_id'), table_name='results')
    op.drop_column('results', 'document_file_id')

    op.drop_column('classes', 'board')
