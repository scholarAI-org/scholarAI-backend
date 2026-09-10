import unittest
import warnings
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


class AdminMigrationHistoryTests(unittest.TestCase):
    def test_admin_and_main_migrations_form_one_unambiguous_history(self):
        # Duplicate revision IDs warn rather than necessarily failing `heads`.
        with warnings.catch_warnings():
            warnings.simplefilter("error", UserWarning)
            script = ScriptDirectory.from_config(Config("alembic.ini"))
            self.assertEqual(script.get_heads(), ["20260910_01"])
            revisions = list(script.walk_revisions())
        self.assertEqual(
            [revision.revision for revision in revisions[:5]],
            ["20260910_01", "20260909_01", "20260908_admin01", "20260907_02", "20260907_01"],
        )
        self.assertEqual(
            Path(revisions[0].path).name, "20260910_01_add_scholarship_review_fields.py"
        )
        self.assertEqual(
            Path(revisions[1].path).name, "20260909_01_create_audit_logs_table.py"
        )
        self.assertEqual(
            Path(revisions[2].path).name, "20260907_create_admin_notifications_table.py"
        )
        self.assertEqual(
            Path(revisions[4].path).name, "20260907_academic_info_openalex.py"
        )
