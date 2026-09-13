# Scholarship review listing

`GET /admin/scholarships/review?page=1&page_size=20&status=pending`

The full review page has a dedicated listing independent of the Dashboard limit.
Following the clarified requirement, filtering uses the existing scholarship
`status`, not an issue/problem status. The route is `/review` because it supports
approved and rejected listings as well as the default pending listings.

## Current listing contract

Requires the existing Bearer authentication and a stored user role of `admin`.
Missing/invalid authentication returns 401; a non-admin user receives 403.

- `page`: integer, minimum 1, default 1.
- `page_size`: integer, range 1–100, default 20.
- `status`: `pending` (default), `approved`, or `rejected`, validated by
  `ScholarshipReviewStatus`. Values are case-sensitive. `published`, `all`,
  empty strings and unknown values are rejected.
- Invalid pagination/status uses FastAPI's standard 422 `detail` validation array.
- `total` counts all matches before pagination; `total_pages` rounds up.
- Empty matches return `items: []`, `total: 0`, `total_pages: 0`.
- Pages beyond the last return `items: []` with the matching total retained.

```json
{
  "items": [
    {
      "id": 42,
      "title": "Scholarship 42",
      "organization_name": "Example University",
      "country": "Palestine",
      "deadline": "2026-10-01",
      "no_deadline": false,
      "source": "for9a",
      "source_url": "https://example.com/scholarship",
      "status": "pending",
      "scraped_at": "2026-09-09T10:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

`organization_name`, `country`, `deadline`, `no_deadline`, `source_url`, and
`scraped_at` may be null. The table columns follow the existing admin Dashboard
schema. There is no frontend checkout available in this workspace.

## Data conventions

The model stores statuses as lowercase `pending`, `approved`, and `rejected`.
Omitting `status` returns pending rows only; selecting another value replaces
that default filter. There is no issue-status column or issue-status parameter,
and no schema migration is needed. Automatic aggregation
uses the documented sources `for9a` and `ministry`. Sources such as `manual` or
`admin` and unrecognized sources are excluded. There is no separate provenance
flag to distinguish a manually entered row labeled with a scraper source.

The model has no `created_at`; ordering uses the collected date:
`scraped_at DESC NULLS LAST, id DESC`. IDs make equal timestamps deterministic.
All rows with the selected status from known aggregators are included, even if review metadata
exists. The Dashboard's narrower unreviewed-only predicate is unchanged.

There is no pre-existing page/page_size pagination contract in the repository.
The new API adopts the task's requested metadata and a page-size cap of 100.
The query selects only table columns with SQL LIMIT/OFFSET, plus a separate
matching count. There are at most two scholarship queries and no N+1 lookups;
out-of-range or empty pages need only the count. Authentication has its own
existing user lookup.

The existing `/admin/dashboard/recent-pending-scholarships` implementation is
untouched. It returns five rows with `limit=5`; its actual existing default is
10, and its maximum is 50. The new listing has no Dashboard result-size limit.

## Checks

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_admin_pending_scholarships_review.py tests/test_admin_recent_pending_scholarships.py -q
.\venv\Scripts\python.exe -m ruff check --select E9,F,I app/api/admin.py app/schemas/admin.py tests/test_admin_pending_scholarships_review.py
.\venv\Scripts\python.exe -m mypy --explicit-package-bases --follow-imports=silent --ignore-missing-imports app/api/admin.py app/schemas/admin.py
```

Tests cover source/status exclusions, filtering each allowed status, ordering,
pagination, empty results, null fields, admin authorization, bounded SQL queries,
the existing latest-five Dashboard behavior and generated OpenAPI. The existing
PostgreSQL integration test requires a disposable database via
`PENDING_TEST_DATABASE_URL` and otherwise skips.

The full suite passed with 239 tests and 108 subtests; three PostgreSQL integration
tests were skipped without configured disposable databases. An existing Alembic
configuration deprecation warning remains. Targeted review and Dashboard tests
passed with 29 tests, 42 subtests and one PostgreSQL skip.

Ruff E9/F/I checks for the app files, full Ruff for the new tests, formatting,
compileall and `git diff --check` passed. Mypy reports the same four existing
Column-to-scalar type errors in the unrelated admin-profile response as the
pre-change baseline, with no new type errors.
