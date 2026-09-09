# Profile document upload validation

The backend policy lives in `DOCUMENT_RULES` in `app/services/documents.py`.
The extension-to-MIME mapping checks compatible pairs, not just independent
extension and MIME allowlists. Limits use 1 MB = 1,048,576 bytes.

| Request document type | Extensions | Maximum bytes |
| --- | --- | --- |
| `cv` | PDF, DOCX | 5,242,880 |
| `transcript` | PDF | 10,485,760 |
| `graduation_certificate` | PDF, JPG, JPEG, PNG | 10,485,760 |
| `passport` | PDF, JPG, JPEG, PNG | 5,242,880 |
| `recommendation_letter` | PDF, DOCX | 5,242,880 per file |
| `english_test` | PDF, JPG, JPEG, PNG | 5,242,880 |

MIME types are `application/pdf`, `image/jpeg`, `image/png`, and
`application/vnd.openxmlformats-officedocument.wordprocessingml.document`.
The existing additional `motivation_letter` type retains its PDF policy and
`S3_MAX_FILE_BYTES` limit. The six types above have explicit limits independent
of that legacy setting. The existing recommendation count setting
`S3_MAX_RECOMMENDATION_LETTERS` is preserved; the stored list key remains
`recommendation_letters`.

## Request and confirmation flow

All document routes require the existing Bearer authentication dependency:

- `POST /profile/documents/upload-url`
- `POST /profile/documents/confirm`
- `GET /profile/documents`
- `GET /profile/documents/{document_id}/download-url`
- `DELETE /profile/documents/{document_id}`

The request schema is unchanged:

```json
{
  "document_type": "cv",
  "file_name": "resume.docx",
  "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "file_size": 123456
}
```

Pydantic validates the document enum and required metadata. The service validates
the sanitized filename, case-insensitive extension, compatible MIME and positive
size before creating a session, generating a key or signing a URL. Invalid input
returns the existing `{"detail": ...}` 400/422 response shape.

The server creates `users/{authenticated_user_id}/documents/{type}/{uuid}.{ext}`.
The original filename is sanitized for display; it does not select the storage
path. Upload using the returned PUT URL and `headers`, including the signed
`Content-Type`. Signing failures return a generic 503 and remove the unusable
upload session.

Confirmation accepts only `{"upload_id": "..."}` as meaningful input. Extra
fields do not override the owner, type or object key. The service locks the
session for update on PostgreSQL, checks ownership, pending status and expiry,
then uses S3 HEAD on the stored key. Missing/foreign sessions return 404;
consumed sessions return 409. Missing objects and invalid/expired sessions return
400. Storage lookup failures return a generic 503 and allow a retry.

Actual HEAD size and Content-Type must satisfy the current document policy and
match the expected session metadata exactly (after MIME normalization). This
also rejects older pending sessions that no longer meet the policy. Rejected
objects are deleted where possible and the session becomes FAILED. Cleanup
failure logs a warning and still rejects the document without exposing storage
details in the response.

Valid confirmation persists the document through the existing SQL UPDATE of the
JSON column and marks the session confirmed in the same transaction. A valid
single-slot replacement deletes the old object only after persistence succeeds.
Invalid replacements retain the previous document. Recommendation letters
continue to append and can be deleted individually.

## Limits of this validation

HEAD verifies stored metadata, not the actual file format. MIME can be forged;
this does not prove that a PDF, image or DOCX contains valid or safe content.
The existing storage adapter does not read file contents. Future work should
inspect signatures (including DOCX ZIP/Office structure) using bounded reads
or streaming and gate acceptance through quarantine/content scanning.

Presigned PUT URLs remain reusable until expiry. This change does not make S3
objects immutable after confirmation or prevent objects being re-uploaded after
cleanup. Version-pinned storage or a separate accepted-object location and a
lifecycle cleanup process would address that separately. Cleanup failures and
abandoned uploads also require an operational retry/lifecycle policy.

Unit tests use SQLite and fake S3 objects; they do not contact AWS or verify
PostgreSQL row locking under concurrent requests.

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_document_uploads.py tests/test_avatar_upload.py -q
```
