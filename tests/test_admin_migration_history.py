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
            self.assertEqual(script.get_heads(), ["20260912_notify01"])
            revisions = list(script.walk_revisions())
        self.assertEqual(
            script.get_revision("20260912_merge01").down_revision,
            ("20260909_admin01", "20260910_01"),
        )
        self.assertEqual(
            Path(script.get_revision("20260909_admin01").path).name,
            "20260909_01_create_audit_logs_table.py",
        )
        self.assertEqual(
            script.get_revision("20260909_admin01").down_revision, "20260908_admin01"
        )
        self.assertEqual(
            script.get_revision("20260909_01").down_revision, "20260907_02"
        )
        self.assertEqual(len({r.revision for r in revisions}), len(revisions))
