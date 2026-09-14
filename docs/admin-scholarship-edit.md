# Admin scholarship content edits

`PATCH /admin/scholarships/{scholarship_id}`

Uses the existing application Bearer token (`get_current_user`) and requires the
stored user role `admin`. The response uses `ScholarshipResponse`, matching the
existing admin `PUT` endpoint, including the ID, content, status and updated_at.

```json
{
  "title": "Updated Scholarship Title",
  "organization_name": "Updated Organization",
  "country": "Germany",
  "description_html": "<p>Updated description</p>"
}
```

`AdminScholarshipUpdate` inherits the existing `ScholarshipUpdate` validation and
types. All fields may be omitted. Only explicitly supplied fields are compared
and changed. Explicit null clears nullable content; null title is rejected, and
the inherited title minimum length is two characters. String lengths respect
the existing database limits for country, study_level and funding_type (100),
apply_email (255), and apply_phone (50). URL/contact values retain the existing
string schema; mandatory publication validation still runs when approving.

Editable fields:

- title, organization_name, country, deadline, no_deadline
- image_url, description_html, source_url
- apply_link, apply_email, apply_phone
- study_level, funding_type, majors, required_documents
- pdf_url, attachments, is_extension

All other fields are rejected with 422, including id, source, source_id, slug,
scraped_at, reviewed_at, reviewed_by, rejection_reason, admin_id, rejected_at,
updated_at and status. There is no scholarship created_at/created_by column;
these names are also rejected. There is no additional_details column or
description request alias; use description_html.

The new review endpoint accepts only `pending`. Existing workflow values are
pending, approved (published), and rejected (archived); approved/rejected or any
other non-pending status returns 409. This is the scope chosen for pre-publication
review, without adding workflow states. Editing leaves status and review metadata
unchanged. Existing PUT, approval, rejection and status endpoints retain their
previous contracts, including the legacy PUT's broader status policy.

Changed values are recorded using the existing `AuditLog` and `create_audit_log`
helper with action `edit`, actor ID/name, scholarship ID, entity type and timestamp.
`details.changes` contains only actual changes, with old/new values. Dates are ISO
strings; nulls, booleans and arrays retain their JSON types. Audit entity_name is
limited to its existing 255-character column; the full changed title is retained
in details. No migration or new dependencies are required.

The service locks the scholarship row on PostgreSQL before checking status and
comparing values. The existing audit helper commits the scholarship and audit
together. Exceptions roll back the session and use the existing application error
handlers. Empty/identical requests return 200 without writing an audit or changing
updated_at. Actual edits set updated_at in UTC, following existing admin routes.

Errors: 401 missing/invalid authentication; 403 non-admin; 404 missing scholarship;
422 invalid payload/path; 409 non-pending scholarship. Database exceptions keep
the existing sanitized error responses (400 for integrity errors, 503 for other
database errors).

Verification uses SQLite API tests with the real authentication and database
dependencies overridden only for database isolation. Coverage includes partial
updates, immutable fields, validation, no-ops, typed audit values, attachments,
rollback on update/audit/commit failures, long titles, OpenAPI, and the existing
review/approval/PUT workflow. SQLite does not verify PostgreSQL row locking.

```text
python -m unittest discover -s tests -p "test_admin_*.py"
python -m pytest tests/test_admin_notifications.py tests/test_admin_notification_migration.py tests/test_recommendation_scholarships.py tests/test_duplicate_detection.py -q
python -m ruff check app/schemas/admin_scholarship_edit.py app/services/admin_scholarship_edit.py tests/test_admin_scholarship_edit.py
python -m ruff format --check app/schemas/admin_scholarship_edit.py app/services/admin_scholarship_edit.py tests/test_admin_scholarship_edit.py
python -m mypy --explicit-package-bases --follow-imports=silent --ignore-missing-imports app/schemas/admin_scholarship_edit.py app/services/admin_scholarship_edit.py
```

Results: 16 new endpoint tests pass. The combined admin, recommendation and
duplicate-detection suite reports 176 passed, 30 skipped, and 93 subtests passed.
The new files pass Ruff lint/format checks; the new schema and service pass mypy.
The existing admin router has six pre-existing Ruff findings, reproduced on
origin/main, with no additional findings introduced here.

The full suite encounters an existing academic-info fixture teardown error:
`no such table: auth_accounts`. This was reproduced on an isolated, unmodified
origin/main checkout (9bb5650). No live database migration or PostgreSQL test was
run for this change.
