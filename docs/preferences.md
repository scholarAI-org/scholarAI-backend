# Preferences API

`GET /profile/preferences` and `PUT /profile/preferences` require the existing
Bearer authentication and operate only on the authenticated user's profile.
`GET /profile` returns the same object under `preferences`.

## Request and response

```json
{
  "desired_degree_level": "MASTER",
  "target_field_of_study": "Artificial Intelligence",
  "target_field_of_study_openalex_id": "https://openalex.org/subfields/1702",
  "detailed_specialization": null,
  "funding_type": "FULL",
  "preferred_countries": ["DE", "PS"],
  "open_to_all_countries": false
}
```

For PhD:

```json
{
  "desired_degree_level": "PHD",
  "target_field_of_study": "Artificial Intelligence",
  "target_field_of_study_openalex_id": "https://openalex.org/subfields/1702",
  "detailed_specialization": "Distributed Systems",
  "funding_type": "FULL",
  "preferred_countries": [],
  "open_to_all_countries": true
}
```

Responses include these fields plus `is_profile_completed`. New and legacy
drafts may have null degree, target, target ID, specialization and funding.
Country lists default to `[]`; the all-countries flag defaults to false.
`is_profile_completed` requires degree, funding, target, and a nonblank detailed
specialization for PHD. This section flag is separate from the aggregate weighted
completion percentage.

The existing degree values are `BACHELOR`, `MASTER`, `PHD`, `DIPLOMA`, `OTHER`.
Funding values remain `FULL`, `PARTIAL`, `SELF`, `ANY`.

## Validation and partial updates

- PUT remains a partial update. Omitted values are preserved. Explicit null
  retains its historical no-change meaning for degree, funding, countries and
  the all-countries flag. Empty country arrays explicitly clear the list.
- Target names use the existing OpenAlex display-name convention: trimmed,
  nonblank strings of at most 255 characters. There is no new FieldOfStudy enum.
  As confirmed in the product clarification, all degrees use the same OpenAlex
  taxonomy; no invented field/degree exclusions are applied.
- The target ID remains optional, preserving the existing rollout contract.
  Supplied IDs must match `https://openalex.org/subfields/<positive integer>`
  and require a target name. No remote existence or name/ID correspondence
  check is performed, matching the current academic contract.
- Changing the target name without supplying its ID clears the old ID. Explicit
  null can clear the target and its ID. This prevents retaining stale metadata.
- PHD requires a trimmed, nonblank `detailed_specialization` of at most 255
  characters. Validation uses the merged state, so partial specialization-only
  or degree-only updates cannot bypass the rule. Other degrees normalize this
  value to null, including when changing away from PHD without resending it.
- Country values must have two ASCII letters and normalize to uppercase, e.g.
  `" de "` becomes `"DE"`. This validates the project's country-code format;
  it does not introduce an ISO country registry or geographic restrictions.
- When `open_to_all_countries` is true, the response and every new save contain
  `preferred_countries: []`. Legacy contradictory lists are hidden on reads and
  normalized on their next successful preference save.
- Unknown fields, including removed `preferred_fields_of_study`, return standard
  FastAPI 422 validation errors. Invalid merged updates never persist changes.
- Nullable legacy PhD profiles remain readable without a specialization;
  new preference writes must meet the PhD requirement.

`PreferencesState` is the central validator. `preferences_response` is shared
by section and aggregate reads; `save_preferences` merges and validates before
writing. No invalid state is persisted merely because validation occurred after
request parsing.

## Academic ownership and completion

`target_field_of_study` and `target_field_of_study_openalex_id` no longer appear
in academic request/response schemas. Academic PUT rejects them with 422.
`field_of_study` and its ID, GPA, study status, institution, graduation year and
current research specialization remain academic information.

The academic section no longer requires the target to award its existing 22%.
Preferences uses the new canonical target for its existing 8% target-field
weight. No weights or overall completion threshold change, and detailed PhD
specialization does not add a second target score.

## Migration and rollout

New Alembic revision `20260909_01`, following `20260907_02`, adds only nullable
`profiles.detailed_specialization VARCHAR(255)`. No old migration is edited.

The existing target name and OpenAlex ID columns retain their exact values.
The old JSON column `preferred_fields_of_study` remains intact, accessed in the
ORM only as `legacy_preferred_fields_of_study`, and is an archive rather than an
active preference. No first entry is chosen, even for single-item lists; the
multiple-preference list and intended target were distinct concepts. If no
existing target was saved, it stays null until the user chooses one. No current
endpoint reads from or writes to the archive.

Searches found no internal recommendation engine consuming these fields. The
scholarship recommendation feed is independent. All active preference consumers
(GET, PUT, aggregate response, completion) now read the canonical target.

Deploy the migration before the new backend. Coordinate client rollout to send
one target to Preferences, and remove target fields from Academic Information.
The backend deliberately rejects the old write contract rather than selecting
from a list or maintaining two writable sources of truth. This work includes
no frontend changes and does not establish external-client compatibility.

```powershell
python -m alembic upgrade head
```

Downgrade removes the new column only when it is unpopulated. It refuses to
discard stored specializations; export and explicitly resolve those values
before downgrading. Existing target and archived-list columns remain untouched
in either direction. No migration was applied to the configured live database
as part of this change.

## Verification

Tests exercise GET/PUT Preferences, GET Profile, all degree values with shared
OpenAlex fields, partial updates, specialization clearing, invalid payloads,
country normalization, archive preservation, academic ownership, completion
weights, authentication and generated OpenAPI. PostgreSQL migration tests cover
upgrade, existing-data preservation, safe downgrade and data-loss protection.

```powershell
python -m pytest tests -q
python -m ruff check app/services/preferences.py tests/test_preferences.py tests/test_preferences_migration.py alembic/versions/20260909_preferences_target_field.py
python -m mypy --explicit-package-bases --follow-imports=silent --ignore-missing-imports app/services/preferences.py
```

For integration coverage, configure `ACADEMIC_TEST_DATABASE_URL`,
`ACADEMIC_MIGRATION_TEST_DATABASE_URL` and
`PREFERENCES_MIGRATION_TEST_DATABASE_URL` with separate disposable local PostgreSQL
databases. Names must begin with `scholarai_academic_test_`. Upgrade the API test
database to head before running tests. The migration test databases are changed
by tests and must contain no real user data.

Full PostgreSQL-backed verification passed with 364 tests and 64 subtests, with
no skips. Ruff passes for new files; existing touched files have no added Ruff
diagnostics. Mypy passes for the new Preferences service. `alembic check` reports
an existing unrelated missing `ix_scholarships_id` index; the profiles schema
matches the model and new migration. This change does not modify scholarships.
