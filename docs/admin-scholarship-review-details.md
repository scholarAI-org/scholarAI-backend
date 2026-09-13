# Scholarship review details

`GET /admin/scholarships/{scholarship_id}/review-details`

Requires the existing application Bearer access token and a user with stored role
`admin`. Returns 401 for missing/invalid authentication, 403 for other roles,
404 when the scholarship does not exist, and 422 for an invalid integer ID.

```json
{
  "title": "Istanbul Technical University Scholarship",
  "organization_name": "Istanbul Technical University",
  "country": "Turkey",
  "description": "<p>A scholarship for international postgraduate students.</p>",
  "additional_details": null
}
```

The response contains exactly these five nullable string fields. Title,
organization_name, and country come directly from scholarships. Description maps
from description_html, preserving source HTML, as the existing recommendation
feed does. No related tables or joins are needed; one projected scholarship query
is executed after authentication.

There is no separate additional_details column or equivalent independent text
field on origin/main. Benefits and qualifications columns were removed by
migration f67f854cd00c. The complete available description remains in description;
additional_details is null rather than duplicating the description or treating
attachment URLs as prose. No migration or ingestion change is introduced.

This router is isolated because origin/main does not yet contain the Dashboard
and pending-review routes present on feature/admin. Existing scholarship routes
are unchanged.

Verification:

```text
python -m pytest tests/test_admin_scholarship_review_details.py tests/test_recommendation_scholarships.py tests/test_admin_scholarship_status_distribution.py -q
python -m ruff check app/api/scholarship_review_details.py app/schemas/scholarship_review_details.py tests/test_admin_scholarship_review_details.py
python -m ruff format --check app/api/scholarship_review_details.py app/schemas/scholarship_review_details.py tests/test_admin_scholarship_review_details.py
python -m mypy --explicit-package-bases --follow-imports=silent --ignore-missing-imports app/api/scholarship_review_details.py app/schemas/scholarship_review_details.py
```

The endpoint tests validate the generated OpenAPI document, response keys,
nullable fields, path parameter and Bearer security declaration.
