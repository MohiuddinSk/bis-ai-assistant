# BIS Saarthi API V1 Contract

## Purpose

This document records the additive v1 API boundary implemented for the BIS Saarthi prototype. It preserves the existing API during a compatibility period; it does not represent production readiness or BIS approval.

## Implemented route mappings

| Legacy route | Implemented v1 route | Contract |
| --- | --- | --- |
| `GET /health` | `GET /api/v1/health` | `HealthResponse` |
| `POST /api/retrieve` | `POST /api/v1/retrieve` | `RetrieveRequest` → `RetrieveResponse` |
| `POST /api/chat` | `POST /api/v1/chat` | `ChatRequest` → `ChatResponse` |
| `POST /api/compliance/guide` | `POST /api/v1/compliance/guide` | `ComplianceProfile` → `ComplianceGuideResponse` |
| `GET /api/documents/{source_filename}` | `GET /api/v1/documents/{source_filename}` | Registered source PDF or safe `404` |

Legacy routes remain supported for backward compatibility. Each legacy/v1 pair shares its handler and existing request/response schemas, preserving established status codes, sanitized error bodies, and `Retry-After` behavior. The existing frontend continues to use legacy routes during the compatibility period.

## Request correlation

Every handled response returns `X-Request-ID`. An inbound value is preserved only when it is 8–64 characters and contains only ASCII letters, digits, period (`.`), underscore (`_`), or hyphen (`-`). Missing or invalid values are replaced by a lowercase UUID4 string.

`X-Request-ID` is available to approved browser clients through CORS request-header allowance and response-header exposure. Request IDs are not added to JSON response bodies, so current body schemas remain unchanged. Existing error sanitization and rate-limit `Retry-After` headers remain unchanged.

## Documentation and compatibility

FastAPI continues to publish OpenAPI through its existing documentation endpoints, including `/openapi.json`, `/docs`, and `/redoc`. Legacy and v1 operations have distinct stable operation IDs in the schema.

## Not implemented

The following routes are intentionally not implemented:

- `POST /api/v1/standards/explain`
- `GET /api/v1/sources/{source_id}`
- `GET /api/v1/documents/{document_id}`

Standard explanation currently uses `POST /api/chat` or `POST /api/v1/chat`. Document retrieval currently uses a registered `source_filename`; no document-ID contract has been introduced.
