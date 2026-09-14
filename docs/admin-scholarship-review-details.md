# Scholarship review details

`GET /admin/scholarships/{scholarship_id}/review-details`

Requires the existing application Bearer access token and an authenticated user with stored role `admin`. Returns 401 for missing/invalid authentication, 403 for other roles, 404 when the scholarship does not exist, and 422 for an invalid integer ID.

## Overview

Provides all required scholarship details for the dedicated scholarship review screen, including:
- **Header info**: Title, organization, country, status badge, scraping source and timestamp, source link.
- **Sidebar metadata**: Funding type, application deadline, majors, direct application link, source link.
- **Content blocks**:
  - **Overview (نظرة عامة)**: Full description HTML from `description_html` / `description`.
  - **Eligibility criteria (شروط الأهلية)**: Structured list from `eligibility_criteria`.
  - **Required documents (المستندات المطلوبة)**: Pill badges list from `required_documents`.

```json
{
  "id": 1,
  "title": "منحة معهد العالم العربي للدراسات العليا",
  "slug": "arab-world-institute-scholarship",
  "organization_name": "معهد العالم العربي",
  "country": "فرنسا",
  "study_level": "دراسات عليا",
  "funding_type": "رسوم + منحة شهرية 800 يورو",
  "deadline": "2026-11-20",
  "no_deadline": false,
  "majors": [
    "العلوم الإنسانية",
    "الفنون",
    "العمارة",
    "التراث",
    "الدراسات العربية"
  ],
  "eligibility_criteria": [
    "درجة جامعية في مجال ذي صلة",
    "إتقان الفرنسية أو الإنجليزية",
    "مشروع بحثي واضح"
  ],
  "required_documents": [
    "توصيتان",
    "مشروع بحث",
    "خطاب تحفيز",
    "كشف علامات",
    "سيرة ذاتية"
  ],
  "description": "<p>منح دراسية كاملة لمتابعة دراسات عليا في معهد العالم العربي بباريس، متخصصة في مجالات العلوم الإنسانية والتراث والدراسات العربية.</p>",
  "description_html": "<p>منح دراسية كاملة لمتابعة دراسات عليا في معهد العالم العربي بباريس، متخصصة في مجالات العلوم الإنسانية والتراث والدراسات العربية.</p>",
  "additional_details": null,
  "source": "for9a",
  "source_id": "for9a-ima-1",
  "source_url": "https://www.imarabe.org",
  "apply_link": "https://www.imarabe.org",
  "apply_email": null,
  "apply_phone": null,
  "image_url": "https://example.com/cover.jpg",
  "pdf_url": null,
  "attachments": [],
  "is_extension": false,
  "status": "pending",
  "scraped_at": "2026-08-10T10:00:00Z",
  "reviewed_at": null,
  "reviewed_by": null,
  "rejection_reason": null,
  "admin_id": null,
  "rejected_at": null,
  "updated_at": null
}
```

## Schema & Migration

Migration `20260914_01_add_scholarship_eligibility_criteria.py` adds `eligibility_criteria` (JSON, nullable) to the `scholarships` table.

The response model `ScholarshipReviewDetailsResponse` maps all stored fields with `from_attributes=True` and automatically aliases `description_html` to `description` for backward compatibility.

## Verification

```powershell
.\venv\Scripts\python.exe -m unittest tests/test_admin_scholarship_review_details.py
.\venv\Scripts\python.exe -m unittest tests/test_admin_approve_scholarship.py tests/test_admin_reject_scholarship.py tests/test_admin_migration_history.py
```
