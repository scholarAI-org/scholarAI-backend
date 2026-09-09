# Recommendation scholarship feed

`GET /api/scholarships/recommendations`

Public endpoint; no authentication or request parameters are required.
Returns all scholarships as a JSON array, ordered by `id` ascending, regardless
of status. Each item retains its exact stored `status`, including custom values,
empty strings, and `null`; no status mapping or filtering is applied.

```json
[
  {
    "id": 1,
    "title": "Example scholarship",
    "slug": "example-scholarship",
    "country": "Palestine",
    "deadline": "2026-10-01",
    "description": "<p>Full scholarship description.</p>",
    "apply_link": "https://example.com/apply",
    "status": "approved"
  }
]
```

`slug`, `country`, `deadline`, `description`, `apply_link`, and `status` can be `null`.
`description` contains the existing `description_html` value, including HTML.
Deadlines use `YYYY-MM-DD`. Past deadlines do not exclude listings.
When the scholarship table is empty, the response is `200 OK` with `[]`.

This endpoint supplies scholarship data to the recommendation system; it does
not rank or personalize results. Its schema is also available in `/docs`.

Validation: `python -m pytest tests/test_recommendation_scholarships.py -q`.
