# Recent pending scholarships

`GET /admin/dashboard/recent-pending-scholarships?limit=10` uses the existing
Bearer authentication and checks the stored user's `role == "admin"`.
Missing/invalid authentication returns 401; non-admin users receive 403.

The response uses the existing snake_case scholarship field names:

```json
{
  "items": [
    {
      "id": 1,
      "title": "Scholarship title",
      "organization_name": "Example University",
      "country": "Palestine",
      "deadline": "2026-10-01",
      "no_deadline": false,
      "source": "for9a",
      "source_url": "https://example.com/scholarship",
      "status": "pending",
      "scraped_at": "2026-09-08T10:00:00Z"
    }
  ],
  "total": 1
}
```

`organization_name`, `country`, `deadline`, `no_deadline`, `source_url`, and
`scraped_at` may be null. Timestamps retain their timezone offset; UTC may be
serialized as `Z`. There is no scholarship degree-level or creation-time column.
No frontend checkout or separate scraper implementation is available in this
repository; the existing Scholarship model, schemas, and ingestion API define
this table contract.

The SQL predicate is:

```sql
source IN ('for9a', 'ministry')
AND status = 'pending'
AND reviewed_at IS NULL
AND reviewed_by IS NULL
```

The model documents `for9a` and `ministry` as scraper origins. There is no separate
creator/provenance flag: a manual listing marked with one of those sources cannot
be distinguished with the current schema. Unknown sources are excluded. A missing
`source_id`, `source_url`, or `scraped_at` does not exclude a known scraper source
because those existing fields are nullable. Any non-null review metadata excludes
a listing, even if its status remains pending. Published listings use `approved`
in the existing workflow and are excluded.

Results use `scraped_at DESC NULLS LAST, id DESC`. The ID makes timestamp ties
deterministic; unknown scrape times follow all known times. The optional integer
`limit` defaults to 10 and accepts 1 through 50. Invalid values use FastAPI's
standard 422 `detail` array. No shared pagination contract exists in this project.

Two SQL queries count matching rows and select only the ten table columns with
the requested limit. `total` is the matching count before limiting, not the page
length. No full descriptions or attachments are loaded. Empty results are
`{"items": [], "total": 0}`.

## Git integration and migration collision

The existing branch is named `feature/admin`, not `feature-admin`. It was updated
to `origin/feature/admin` and merged with `origin/main` locally. Changes are
published only to `feature/admin`; no PR was created and `main` was not modified.

The merge exposed two migrations with ID `20260907_01`: academic information on
main and admin notifications on the admin branch. The existing notification
migration now uses `20260908_admin01`, after main's `20260907_02`. Main's revisions
and all notification DDL are preserved. No new migration or scholarship column
was added. The migration-history regression test rejects duplicate IDs and checks
that academic, completion, and notification migrations all remain reachable.

Fresh databases and databases on main's history can use `alembic upgrade head`.
If a database already applied the old admin notification revision under the
colliding ID, its migration stamp and actual schema need reconciliation before
deployment; the ambiguous old stamp cannot identify which migration ran.

After implementation, the configured database was inspected with read-only
queries: it was at `20260907_02`, all academic/completion fields were present,
and `admin_notifications` was absent. With explicit user authorization,
`alembic upgrade head` then applied `20260908_admin01`. The new revision,
notification table, and successful unread-count query were verified afterward.

## Verification

Use `venv/Scripts/python.exe` for the commands below on this Windows workspace.

```powershell
python -m pytest -q
python -m ruff check tests/test_admin_recent_pending_scholarships.py tests/test_admin_migration_history.py tests/test_academic_info_migration.py alembic/versions/20260907_create_admin_notifications_table.py
python -m ruff check --select E9,F,I app/api/admin.py app/schemas/admin.py
python -m ruff format --check app/api/admin.py app/schemas/admin.py tests/test_admin_recent_pending_scholarships.py tests/test_admin_migration_history.py tests/test_academic_info_migration.py alembic/versions/20260907_create_admin_notifications_table.py
python -m mypy --explicit-package-bases --follow-imports=silent --ignore-missing-imports app/api/admin.py app/schemas/admin.py
python -m compileall -q app tests alembic/versions
git diff --check
```

For PostgreSQL coverage, set `ACADEMIC_TEST_DATABASE_URL` and
`PENDING_TEST_DATABASE_URL` to a migrated disposable local PostgreSQL database,
and `ACADEMIC_MIGRATION_TEST_DATABASE_URL` to a separate disposable database.
Both database names must start with `scholarai_academic_test_`. Without these
variables the PostgreSQL-specific tests are skipped. Never use production URLs.

Verified with PostgreSQL 18 and all three test variables: **319 tests and 21
subtests passed**, with no skips. This includes the real PostgreSQL scholarship
query, timezone ordering, full migration upgrades, legacy-data preservation,
and downgrade protection. `alembic heads` and `alembic current` identify
`20260908_admin01`. Two existing Alembic configuration deprecation warnings remain.

The listed Ruff, formatting, compileall, and whitespace checks pass. Full Ruff on
the touched app files still reports existing `RUF100`, `UP045`, and `BLE001`
violations in notification/profile code. Mypy passes for the response schemas;
checking the router also reports four existing `Column[...]` argument-type errors
in `get_current_admin_profile`. A `--shadow-file` comparison against the Git HEAD
baseline confirmed exactly the same four errors before and after this change.
Mypy was installed only in the local virtual environment; dependencies were not
changed.
