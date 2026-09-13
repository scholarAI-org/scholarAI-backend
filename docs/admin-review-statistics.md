# Pending scholarship review statistics

`GET /admin/scholarships/review/statistics`

Send the application's existing Bearer token. The stored user role must be
`admin`; the route uses the same authentication and 403 response as the review
listing. No request parameters are needed.

```json
{
  "pending_count": 120,
  "approved_this_week": 24,
  "reviewed_this_week": 37,
  "missing_source_url_count": 15
}
```

All four values are nonnegative integers, including zero on an empty database.
The endpoint counts existing scholarship records across **all sources** as
requested. It does not apply the listing's for9a/ministry source filter or any
pagination. Missing URLs are counted across all statuses.

## Fields and definitions

- `pending_count`: `scholarships.status` equals
  `ScholarshipReviewStatus.PENDING.value` (`pending`).
- `approved_this_week`: current status is `approved`, and the latest matching
  approval audit timestamp is within this week. The existing audit fields are
  `audit_logs.entity_type = scholarship`, `entity_id = scholarships.id`,
  `action IN (publish, approve)`, and `created_at`. Both current approval routes
  write `publish`; `approve` is also supported by the audit service. Multiple
  audit rows count a scholarship only once. If no approval audit exists, use
  `scholarships.reviewed_at`, which the approval workflow records.
- `reviewed_this_week`: current status is `approved` or `rejected`, and
  `scholarships.reviewed_at` is within this week. Both decision workflows write
  this field. Pending records with old review metadata are not completed reviews.
- `missing_source_url_count`: `scholarships.source_url` is SQL NULL, empty, or
  contains only spaces, tabs, line feeds, carriage returns, form feeds, or
  vertical tabs. A nonempty but invalid URL is not a missing URL.

The week begins **Monday 00:00:00 UTC**, inclusive, and ends at the request's
current UTC time, inclusive. Future-dated records are excluded. Boundaries are
computed once in Python and compared with the stored timezone-aware timestamp
columns, following the existing admin workflow's UTC convention.

There is no `approved_at` database column. `approved_at` in the aggregate query
is only an alias for the latest approval audit timestamp. `updated_at` and
`scraped_at` never determine these weekly statistics. Ordinary detail edits log
`edit` and leave `reviewed_at` unchanged, so they cannot inflate weekly counts.

## Data limitations

These are counts of current records and their latest recorded decisions, not
historical event totals. Deleted records are excluded; a record returned to
pending is not a completed review, and a currently rejected record is not an
approved scholarship. The existing status endpoint records another decision
even when the requested status equals the stored status; this API follows that
existing behavior without changing the workflow.

Legacy records without an approval audit and without `reviewed_at` are excluded
from weekly approvals. A record without `reviewed_at` is excluded from weekly
reviews even if it has an approval audit. Dates are never inferred from unrelated
updates or ingestion. Existing historical inaccuracies cannot be repaired by a
read-only statistics endpoint.

## Implementation and validation

The existing admin router delegates to `app/services/admin_statistics.py`.
One aggregate query joins a grouped approval-history subquery, returning four
counts without loading scholarship records. Authentication performs its normal
user lookup. No schema changes, migrations, or workflow mutations are required.

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_admin_review_statistics.py -q
.\venv\Scripts\python.exe -m ruff check app/services/admin_statistics.py tests/test_admin_review_statistics.py
```

Tests use an isolated SQLite database following the existing statistics fixtures,
with a frozen clock. They cover statuses and sources, audit precedence and repeat
approvals, unrelated edits, missing metadata, Monday/Sunday/year boundaries,
future timestamps, blank URLs, authentication, and aggregate query count.
