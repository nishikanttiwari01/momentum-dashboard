# Contracts & Code Generation

- **OpenAPI-first**: define/update `/contracts/openapi.yaml`.
- Generate **Pydantic models** for API IO under `backend/app/schemas/generated/`.
- Generate **TypeScript types + client** under `frontend/src/lib/api/`.
- CI should fail if generated artifacts are out-of-date versus spec.
- Enforce consistent **run_id**, `as_of` timestamps, and ETag/If-None-Match on GETs where applicable.