# Offer Management

Offer Management converts ATS candidates in the **Selected** stage into controlled employment offers. It remains independent from preboarding.

## Workflow

1. HR creates an offer with a future joining date, validity period, employment terms, and a compensation structure whose components equal annual CTC.
2. The offer is submitted through HR Executive, HR Manager, and Business Unit Head approval in sequence.
3. An approved offer is rendered as a PDF and stored in the Document Vault before release.
4. The candidate can accept, decline with a reason, or request clarification. HR may withdraw an eligible offer.
5. Expired released offers are marked automatically. Every edit creates an immutable version and every workflow action is added to the timeline and audit log.

Offer IDs follow `OFF-000001`. Mandatory components are Basic Salary, HRA, and Special Allowance.

## Routes

- `GET /api/v1/offers/dashboard`
- `GET|POST /api/v1/offers`
- `GET|PUT /api/v1/offers/{id}`
- `POST /api/v1/offers/{id}/submit`
- `POST /api/v1/offers/{id}/approval/{approve|reject|send_back}`
- `POST /api/v1/offers/{id}/pdf`
- `POST /api/v1/offers/{id}/release`
- `POST /api/v1/offers/{id}/{accept|decline|clarification|withdraw}`
- `GET|POST /api/v1/offers/templates`

The web application exposes `/offers`, `/offers/dashboard`, `/offers/new`, `/offers/templates`, and `/offers/{id}`.
