# Academic Information API

`PUT /profile/academic-info` replaces the complete academic section and returns
the normalized saved object. It requires the existing Bearer authentication.
`GET /profile/academic-info` and `GET /profile` use the same academic serializer.

## Frontend contract

```json
{
  "academic_level": "BACHELOR",
  "field_of_study": "Artificial Intelligence",
  "field_of_study_openalex_id": "https://openalex.org/subfields/1702",
  "institution": null,
  "gpa": {"value": 3.4, "scale": "SCALE_4"},
  "current_study_language": ["English"],
  "expected_graduation_year": 2027,
  "study_status": "CURRENTLY_STUDYING",
  "target_field_of_study": "Computer Science Applications",
  "target_field_of_study_openalex_id": "https://openalex.org/subfields/1706",
  "research_specialization": null,
  "research_specialization_openalex_id": null
}
```

Required on every PUT: `academic_level`, `field_of_study`, `gpa`,
`expected_graduation_year`, `study_status`, `target_field_of_study`.
PUT is not a partial update. Unknown keys return 422 to catch contract mistakes.

- `AcademicLevel` remains `TAWJIHI`, `BACHELOR`, `MASTER`, `PHD`.
- `TAWJIHI` permits exactly `SCIENTIFIC`, `LITERARY`, `SHARIA`, `INDUSTRIAL`.
  Its current-field OpenAlex ID must be null or omitted.
- University levels require a nonblank Subfield display name and canonical
  `https://openalex.org/subfields/<numeric-id>` ID. The old mixed `FieldOfStudy`
  enum is no longer the schema or storage type.
- `study_status`: `CURRENTLY_STUDYING` or `GRADUATED`; stored, never inferred.
- The target name is required at every level. The target Subfield ID is accepted
  and persisted, but may be null/omitted during frontend migration. No frontend
  repository was available to confirm full ID persistence rollout. The frontend
  should send both selected values; making the target ID mandatory is a future
  coordinated contract change.
- Only PhD accepts research specialization; its name and canonical
  `https://openalex.org/T<numeric-id>` Topic ID must appear together. Omitting
  them in a later PUT clears old values, including when changing academic level.
- Names are trimmed, nonblank, and limited to 255 characters. Institution is
  optional, nullable, may be empty, and is trimmed with the existing 255 limit.
- `current_study_language` is preserved as a list, defaulting to `[]`.
- GPA requires an actual finite JSON number: values from zero through 4, 5, 10,
  or 100 for the corresponding unchanged `GPAScale`. Numeric strings and booleans
  are rejected. Low scores (45/100, 1.5/4) remain valid.
- Graduation year requires an integer between runtime current year minus 50
  and current year plus 10, inclusively. This is documented in OpenAPI without
  a stale static maximum. The example year is illustrative, not a fixed bound.

IDs and labels are stored separately. Shape validation checks entity type and
canonical URL; it does not verify existence or name/ID correspondence remotely.
There are no OpenAlex calls during saves. The canonical formats were verified
against [OpenAlex Subfields](https://help.openalex.org/data/subfields/) and
[OpenAlex Topics](https://help.openalex.org/data/topics/).

## Legacy reads and completion

`AcademicInfoUpdate` validates new writes; `AcademicInfoResponse` allows nullable
legacy fields. Old labels such as `COMPUTER_SCIENCE` are returned unchanged,
without inventing target fields, status, IDs, or deleting data. Old additional
high-school tracks remain readable but cannot be saved again under the new rules.
Reads do not reapply the sliding graduation-year bounds to historical data.
Partial profiles return a valid nullable response object; a completely empty
academic section returns `200 null` (previously section GET returned 404).
`UserProfile.academic_info` contains the identical object or null.

The centralized completion function validates academic completeness against the
same write contract, including required current IDs at university levels. Missing
status/target prevents completion. Institution and research are optional, and a
high-school current OpenAlex ID is never required. GPA zero is valid. Completion
continues to be computed for full-profile reads rather than trusting the existing
cached database percentage column. No unrelated section scoring was changed.

## Persistence and rollout

Academic data is stored in separate `profiles` columns, not an `academic_info`
JSON document. Alembic revision `20260907_01` (parent `20260906_02`) converts
`field_of_study` from PostgreSQL enum to `VARCHAR(255)` preserving exact values,
and adds six nullable fields: five name/ID columns and the `studystatus` enum
column. Nullable database fields allow existing records and registration drafts;
the API enforces the strict complete-section write contract.

Apply `python -m alembic upgrade head` on the deployment database before starting
the new backend. Verify `alembic current` and `alembic heads` show `20260907_01`.
Use a direct PostgreSQL connection for Alembic. Schema changes were tested on
disposable local PostgreSQL databases, then applied to the configured Neon
database with user approval on 2026-09-07. Revision `20260907_01`, profile columns,
server health and the new OpenAPI contract were verified afterward.

Downgrade restores the original enum when all records remain legacy-compatible
and the new columns contain no data. It refuses to discard newly saved academic
information; export/transform that data explicitly before downgrading. The
old enum type is intentionally retained during upgrade for this purpose.

## Verification

`python -m pytest -q` runs API, validation, authentication, persistence, legacy,
completion and OpenAPI tests using isolated SQLite databases.

For real migrated PostgreSQL coverage, set `ACADEMIC_TEST_DATABASE_URL` to a
migrated disposable local database named `scholarai_academic_test_*`. The same
academic API tests then run against both SQLite and PostgreSQL. Set
`ACADEMIC_MIGRATION_TEST_DATABASE_URL` to a separate disposable local database
with the same name prefix for upgrade/downgrade and populated legacy-data tests.
The migration test is skipped when this environment variable is absent.

Verified on 2026-09-07 with both PostgreSQL test database variables set:
`python -m pytest -q` passed **256 tests and 8 subtests**, with no skips. Alembic
`upgrade head`, `current`, and `heads` agreed on `20260907_01`. Full lint passed
for the new service, migration and test files; E9/F/I checks passed for the touched
profile API/model/schema files. `compileall` and `git diff --check` passed.
Repository-wide Ruff still reports existing violations outside this change;
there is no configured/installed mypy or pyright check.
