# Admin notifications

Implemented on the existing `feature/admin` branch. The branch includes the latest
`origin/main`; no new Git branch, push, or pull request was created. The merge
preserved both admin and Google authentication model registrations.

## API

All three endpoints reuse application Bearer authentication and the existing admin
role check. The identity comes from the token, never from an `admin_id` parameter.
Missing/invalid authentication returns 401; a student receives 403. Inaccessible
and nonexistent notification IDs return the same 404 response.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/admin/notifications` | Paginated notification content and the caller's read status |
| PATCH | `/admin/notifications/{notification_id}/read` | Mark one notification read for the caller |
| GET | `/admin/notifications/unread-count` | Existing counter, unchanged response contract |

Listing accepts `page` (default 1, minimum 1), `page_size` (default 20, range
1–100), optional boolean `is_read`, and optional enum `type`. Filters combine;
both item and count queries apply the same visibility and filters. Ordering is
`created_at DESC, id DESC`. Empty/out-of-range pages return 200 with `items: []`;
`total` remains the matching count. Invalid parameters return the standard 422.
There are three SELECTs per listing request: authentication, count, and page.

```json
{
  "items": [{
    "id": 42,
    "type": "scholarship_review",
    "title": "New scholarship pending review",
    "message": "New aggregated scholarship \"Example scholarship\" requires review.",
    "created_at": "2026-09-12T10:00:00Z",
    "is_read": false,
    "related_entity_id": 123,
    "action_type": "open_scholarship_review"
  }],
  "total": 1,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

```json
{"id": 42, "is_read": true, "read_at": "2026-09-12T10:15:00Z"}
```

```json
{"unread_count": 0}
```

Optional entity/action fields serialize as `null`. Timestamps use the project's
timezone-aware PostgreSQL timestamps and Pydantic ISO 8601 serialization; the
returned offset follows the database session, so it can be an offset or `Z`.

## Content, ownership, and events

The existing `admin_notifications` table remains the content source. A nullable
`recipient_id` distinguishes global admin content from private notifications.
Global content is visible to all current and future admins. A private recipient
must be an existing admin. The FK uses `ON DELETE CASCADE`, so deleting a recipient
cannot accidentally turn private content into global content.

`admin_notification_reads` records `(admin_id, notification_id, read_at)` with a
composite primary key. A row means read. An atomic `ON CONFLICT DO NOTHING` keeps
the first timestamp across repeated/concurrent requests. No request updates the
old shared `is_read`/`read_at` fields: they remain a frozen historical baseline for
legacy records. New notifications have that baseline set to unread. Listing,
counter, and mutation use the same visibility/read projection. Reading as one
admin never changes another admin's counter or state.

`create_admin_notification` is an internal service, with no public creation route.
Supported types are `general`, `scholarship` (existing legacy usage), and
`scholarship_review`. The action enum contains `open_scholarship_review`. New writes
and filters validate these enums; legacy content with other stored types remains
readable in unfiltered listings.

The real `POST /api/scholarships/` ingestion path creates a global notification
after flushing a new `for9a` or `ministry` scholarship with status `pending`.
Manual sources and non-pending records keep their existing behavior. The service
uses the caller's transaction and never commits. Scholarship and notification
commit together; errors roll back both and propagate normally.

The persisted unique event key scopes a caller's stable event identity by type
and recipient/global audience. The ingestion key uses the scholarship ID and
the initial pending event. Concurrent retries reuse the same notification.
Distinct general notifications can omit a key. Scholarship ingestion retains
the existing `(source, source_id)` duplicate protection and response behavior;
scrapers must supply their stable source ID to identify retries of ingestion.
Existing pending scholarships are not retrospectively backfilled.

## Migrations and existing deployments

Two new revisions are added:

- `20260912_merge01` joins `20260909_admin01` and main's `20260910_01`.
- `20260912_notify01` adds nullable `recipient_id`, `related_entity_id`,
  `action_type`, and `event_key`; the recipient FK; a unique event-key constraint;
  an index on `(recipient_id, created_at, id)`; and the per-admin read table.

Existing notification tables/records are preserved. The old audit migration's
revision identifier was corrected from the colliding `20260909_01` to
`20260909_admin01` with explicit user approval. Its schema operations are unchanged.
Main's preferences and Google auth revision identifiers remain unchanged.

For a database that previously applied the admin audit migration under the old
identifier, run the repair preview before upgrading:

```console
python -m migrations.repair_admin_audit_revision
python -m migrations.repair_admin_audit_revision --apply
python -m alembic upgrade head
```

The repair checks actual table/column presence and migration stamps. It changes
only Alembic bookkeeping for an already-applied audit migration, preserves main's
stamp when needed, rejects inconsistent schemas, and is idempotent. On a main-only
database there is nothing to repair. Use the deployment's direct database
connection for these commands. No deployment database was modified during this task.

Downgrade to `20260912_merge01` succeeds while only legacy-compatible data exists.
It refuses to discard any new read state, private audience, entity/action metadata,
or idempotency keys. It never flattens independent reads into a shared read flag.

## Verification

Tests cover creation validation and rollback, actual ingestion, duplicate events,
pagination and stable ordering, combined filters, null serialization, auth,
private visibility, independent counters, first-read timestamps, concurrency,
OpenAPI, and legacy records/future admins. PostgreSQL 18 ran in an isolated local
temporary cluster; API checks also ran on SQLite.

Migration checks passed for a fresh database, a main-only database, a legacy admin
stamp, and a database with both branches' schemas. They verify preserved records,
repair preview/idempotency, upgrade, safe downgrade/re-upgrade, and guarded
downgrade after new data. Alembic reports one head: `20260912_notify01`.

The focused admin/authentication/ingestion regression run passed **143 tests and
51 subtests**, with five optional checks skipped. It includes all four new
PostgreSQL migration tests and both-database notification API tests.
The preferences migration regression was also run separately against its own
disposable PostgreSQL database: both tests passed, including its data-protecting
downgrade through the combined migration history.

Ruff lint and formatter checks pass for the new service, notification model,
tests, migrations, and repair utility. The other edited files introduce no new
lint diagnostics compared with the pre-change versions. Mypy passes for the
service, response schemas, and repair utility. Broader API type checking still
reports six existing legacy SQLAlchemy typing errors in profile serialization
and scholarship status distribution, outside the new feature.

The full suite reports 335 passed, 11 skipped, and 141 teardown errors, plus 115
passing subtests. The 141 errors come from existing academic/preferences SQLite
fixtures missing `auth_accounts`. A clean archive of `origin/main` reproduces
those same 141 errors, plus its stale migration-head assertion. Unrelated fixtures
were left unchanged. Optional PostgreSQL checks without their dedicated URLs are
skipped; the new PostgreSQL API/concurrency and migration checks were run explicitly.

## Changed feature files

- `app/models/admin_notification.py`
- `app/models/__init__.py`
- `app/services/admin_notifications.py`
- `app/schemas/admin.py`
- `app/api/admin.py`
- `app/api/scholarships.py`
- `alembic/versions/20260909_01_create_audit_logs_table.py` (approved ID correction)
- `alembic/versions/20260912_merge_admin_and_main.py`
- `alembic/versions/20260912_admin_notification_state.py`
- `migrations/repair_admin_audit_revision.py`
- `tests/test_admin_notifications.py`
- `tests/test_admin_notification_migration.py`
- `tests/test_admin_notification_counter.py`
- `tests/test_admin_migration_history.py`
- `tests/test_preferences_migration.py` (current-head assertions only)
- `docs/admin-notifications.md`

Changes outside this feature in the preceding merge are inherited from
`origin/main`. No unrelated implementation refactoring, secrets, local database
files, generated caches, or `.env` files are included in the feature commit.
