# Monthly platform activity

`GET /admin/dashboard/monthly-activity`

Requires `Authorization: Bearer <access_token>` from `/auth/login` and a stored
user role of `admin`. Uses the existing `get_current_user` dependency. Missing,
invalid, expired, or unknown-user tokens receive 401; other roles receive 403.
The stored role is authoritative even when the token claims `admin`.

## Response

HTTP 200 returns `items`, following the existing admin list response convention.
There are always exactly 12 items, oldest first, including the current UTC month.
No query parameters or pagination are required. Month names are English.

Example with no activity when the current month is September 2026:

```json
{
  "items": [
    {"year": 2025, "month": 10, "month_name": "October", "approved_scholarships": 0, "users": 0},
    {"year": 2025, "month": 11, "month_name": "November", "approved_scholarships": 0, "users": 0},
    {"year": 2025, "month": 12, "month_name": "December", "approved_scholarships": 0, "users": 0},
    {"year": 2026, "month": 1, "month_name": "January", "approved_scholarships": 0, "users": 0},
    {"year": 2026, "month": 2, "month_name": "February", "approved_scholarships": 0, "users": 0},
    {"year": 2026, "month": 3, "month_name": "March", "approved_scholarships": 0, "users": 0},
    {"year": 2026, "month": 4, "month_name": "April", "approved_scholarships": 0, "users": 0},
    {"year": 2026, "month": 5, "month_name": "May", "approved_scholarships": 0, "users": 0},
    {"year": 2026, "month": 6, "month_name": "June", "approved_scholarships": 0, "users": 0},
    {"year": 2026, "month": 7, "month_name": "July", "approved_scholarships": 0, "users": 0},
    {"year": 2026, "month": 8, "month_name": "August", "approved_scholarships": 0, "users": 0},
    {"year": 2026, "month": 9, "month_name": "September", "approved_scholarships": 0, "users": 0}
  ]
}
```

## Counting rules and assumptions

- Scholarships must currently have `ScholarshipReviewStatus.APPROVED.value`
  (`approved`). Pending, rejected, unknown, and null statuses are excluded.
  All sources and deadlines are included, matching dashboard total semantics.
- `Scholarship.reviewed_at` determines the month. The model and scholarship
  migration describe this as the last review action, not an immutable first
  approval timestamp. There is no dedicated `approved_at` field, and the current
  scholarship API does not maintain an approval event history.
- If `reviewed_at` is null, use `scraped_at` as the best available approximation
  for legacy/imported approved listings. If both dates are null, exclude the row.
  A review date outside the window never falls back to a scrape date inside it.
- These are counts of currently approved records, not historical approval events:
  a later review, status change, or deletion can change previous months' counts.
- Users are counted by `User.created_at`, including admins, inactive users, and
  unverified users. Null registration dates cannot be assigned to a month and
  are excluded. User timestamps follow the existing naive UTC convention.
- Each bucket includes the first instant of its UTC month and excludes the
  first instant of the next month. The current bucket covers the full calendar
  month. The request's current time is captured once for both datasets.
- Scholarship comparisons use timezone-aware UTC bounds; user comparisons use
  naive UTC bounds, matching their respective model/migration column types.
  PostgreSQL session timezone does not affect the resulting buckets.

## Implementation and validation

`app/api/admin.py` adds a thin authenticated route. `app/schemas/admin.py` adds
the item/response models. `app/services/admin_statistics.py` runs two bounded
SQL queries with conditional `COUNT(CASE ...)` aggregates; only 24 scalar counts
reach Python. Including the existing authentication lookup, a request executes
three SELECTs, independent of row count. There are no joins or per-month queries.
No schema changes, migrations, new dependencies, or frontend changes are needed.

Date comparison behavior follows the
[PostgreSQL date/time documentation](https://www.postgresql.org/docs/current/datatype-datetime.html);
aggregates use [SQLAlchemy expressions](https://docs.sqlalchemy.org/en/20/core/expression_api.html).

Tests in `tests/test_admin_monthly_activity.py` cover authentication, exact
response/month count, review date precedence, fallback and missing dates,
status filtering, all account types, empty months, interval edges, current
month, year rollover, leap day, and constant aggregate query count.

```powershell
.\venv\Scripts\python.exe -m unittest tests.test_admin_monthly_activity -v
.\venv\Scripts\python.exe -m unittest discover -s tests -p 'test_admin_*.py' -v
```

The PostgreSQL integration test additionally runs the same aggregates under
UTC, Asia/Hebron, and America/Los_Angeles, using offset-bearing timestamps near
month boundaries. Set `MONTHLY_ACTIVITY_TEST_DATABASE_URL` to a disposable local
PostgreSQL database whose name starts with `scholarai_monthly_test` to enable it.
It creates only connection-local temporary tables and applies no migrations.

Validation results: all 13 feature tests passed, including PostgreSQL 18.3 with
the three session timezones above. Ruff passed for the new service and test
module; `git diff --check` passed. The admin suite ran 79 tests: 77 passed and
two opt-in PostgreSQL tests were skipped. The new PostgreSQL test was enabled
and passed separately as part of the 13 feature tests.
