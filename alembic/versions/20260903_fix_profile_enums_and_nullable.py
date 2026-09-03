from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision = '20260903_01'
down_revision = '1023f6ed1956'
branch_labels = None
depends_on = None

def upgrade():
    # ──────────────────────────────────────────────────────────────────────────
    # ALTER TYPE ADD VALUE requires AUTOCOMMIT mode in PostgreSQL.
    # We use Alembic's built-in autocommit_block().
    # ──────────────────────────────────────────────────────────────────────────
    enum_statements = [
        "ALTER TYPE academiclevel ADD VALUE IF NOT EXISTS 'TAWJIHI'",
        "ALTER TYPE fieldofstudy ADD VALUE IF NOT EXISTS 'SCIENTIFIC'",
        "ALTER TYPE fieldofstudy ADD VALUE IF NOT EXISTS 'LITERARY'",
        "ALTER TYPE fieldofstudy ADD VALUE IF NOT EXISTS 'SHARIA'",
        "ALTER TYPE fieldofstudy ADD VALUE IF NOT EXISTS 'INDUSTRIAL'",
        "ALTER TYPE fieldofstudy ADD VALUE IF NOT EXISTS 'ENTREPRENEURSHIP_BUSINESS'",
        "ALTER TYPE fieldofstudy ADD VALUE IF NOT EXISTS 'AGRICULTURAL'",
        "ALTER TYPE fieldofstudy ADD VALUE IF NOT EXISTS 'HOME_ECONOMICS'",
    ]
    with op.get_context().autocommit_block():
        for stmt in enum_statements:
            op.execute(sa.text(stmt))

    # ──────────────────────────────────────────────────────────────────────────
    # Relax NOT NULL constraints — profiles are created empty and filled later.
    # Run inside a new transaction (Alembic handles this automatically).
    # ──────────────────────────────────────────────────────────────────────────
    cols = [
        ('first_name',           sa.String(50)),
        ('last_name',            sa.String(50)),
        ('email',                sa.String(255)),
        ('birth_date',           sa.Date()),
        ('gender',               sa.Enum('MALE', 'FEMALE', name='gender')),
        ('nationality',          sa.String(2)),
        ('country_of_residence', sa.String(2)),
        ('academic_level',  sa.Enum('TAWJIHI', 'BACHELOR', 'MASTER', 'PHD',
                                    name='academiclevel')),
        ('field_of_study',  sa.Enum('SCIENTIFIC', 'LITERARY', 'SHARIA', 'INDUSTRIAL',
                                    'ENTREPRENEURSHIP_BUSINESS', 'AGRICULTURAL',
                                    'HOME_ECONOMICS', 'ENGINEERING', 'COMPUTER_SCIENCE',
                                    'MEDICINE', 'BUSINESS', 'ARTS', 'OTHER',
                                    name='fieldofstudy')),
        ('institution',          sa.String(255)),
        ('gpa_value',            sa.Float()),
        ('gpa_scale',       sa.Enum('SCALE_4', 'SCALE_5', 'SCALE_10', 'SCALE_100',
                                    name='gpascale')),
    ]
    for col, typ in cols:
        op.alter_column('profiles', col, existing_type=typ, nullable=True)


def downgrade():
    cols = [
        ('gpa_scale', sa.Enum('SCALE_4','SCALE_5','SCALE_10','SCALE_100', name='gpascale')),
        ('gpa_value', sa.Float()),
        ('institution', sa.String(255)),
        ('field_of_study', sa.Enum('SCIENTIFIC','LITERARY','SHARIA','INDUSTRIAL','ENTREPRENEURSHIP_BUSINESS','AGRICULTURAL','HOME_ECONOMICS','ENGINEERING','COMPUTER_SCIENCE','MEDICINE','BUSINESS','ARTS','OTHER', name='fieldofstudy')),
        ('academic_level', sa.Enum('TAWJIHI','BACHELOR','MASTER','PHD', name='academiclevel')),
        ('country_of_residence', sa.String(2)),
        ('nationality', sa.String(2)),
        ('gender', sa.Enum('MALE', 'FEMALE', name='gender')),
        ('birth_date', sa.Date()),
        ('email', sa.String(255)),
        ('last_name', sa.String(50)),
        ('first_name', sa.String(50)),
    ]
    for col, typ in cols:
        op.alter_column('profiles', col, existing_type=typ, nullable=False)
