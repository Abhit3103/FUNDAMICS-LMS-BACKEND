"""add_purpose_to_token_tables

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-10-22 17:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add purpose column to verification_tokens
    op.add_column(
        'verification_tokens',
        sa.Column('purpose', sa.String(length=50), nullable=False, server_default='EMAIL_VERIFICATION'),
    )
    op.create_index(
        op.f('ix_verification_tokens_purpose'),
        'verification_tokens',
        ['purpose'],
        unique=False,
    )

    # Add purpose column to password_reset_tokens
    op.add_column(
        'password_reset_tokens',
        sa.Column('purpose', sa.String(length=50), nullable=False, server_default='PASSWORD_RESET'),
    )
    op.create_index(
        op.f('ix_password_reset_tokens_purpose'),
        'password_reset_tokens',
        ['purpose'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_password_reset_tokens_purpose'), table_name='password_reset_tokens')
    op.drop_column('password_reset_tokens', 'purpose')
    op.drop_index(op.f('ix_verification_tokens_purpose'), table_name='verification_tokens')
    op.drop_column('verification_tokens', 'purpose')
