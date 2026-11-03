# SnapSync — Cloud-Native Photobooth SaaS & Smart Kiosk Platform

> High-throughput, multi-tenant cloud backend and edge kiosk management platform powering automated self-service photo studios (Korean-style 4-cut photobooths). Built with **FastAPI**, **PostgreSQL 16 (Async SQLAlchemy 2.0)**, **VietQR / PayOS**, and **Docker**.

---

## Overview

Operating distributed, unattended photobooth fleets requires real-time cashless settlement, zero double-fulfillment guarantees under network jitter, multi-tenant franchise isolation, and privacy-preserving digital media delivery.

**SnapSync** provides a robust, production-ready backend that orchestrates:
- **Instant Cashless Payments:** Dynamic EMVCo-compliant VietQR generation for Napas 24/7 bank transfers via PayOS.
- **Strict Webhook Idempotency:** Dual-table append-only financial ledger with PostgreSQL row-level pessimistic locking (`SELECT ... FOR UPDATE`) and unique constraints to prevent double-crediting.
- **Multi-Tenant Franchise Architecture:** Shared database with tenant discriminator columns (`tenant_id`), composite B-tree indexing, and cryptographically signed stateless JWT Role-Based Access Control (RBAC).
- **Direct-to-Cloud Ephemeral Media:** Pre-signed S3 upload/download URLs offloading 100% of binary image/video streaming from the API server, with automated 72-hour lifecycle purging in compliance with Vietnam Decree 13/2023/ND-CP.

---

## Project Documentation Index

Comprehensive engineering specifications are located in the [`docs/`](docs/) directory:

| Document | Description | Path |
| :--- | :--- | :--- |
| **Software Design Document (SDD)** | C4 Architecture diagrams (Context, Container, Component, Deployment), Class specifications, Sequence diagrams, State machines, and Data/ERD design. | [`docs/DESIGN.md`](docs/DESIGN.md) |
| **Requirements Specification (SRS)** | Problem statement, functional requirements (FR-01 to FR-18), measurable NFRs, business rules, and acceptance criteria. | [`docs/SRS.md`](docs/SRS.md) |
| **Project Proposal & Plan** | Commercial vision, product positioning, risk management matrix, and work breakdown structure (WBS). | [`docs/PROJECT_PROPOSAL.md`](docs/PROJECT_PROPOSAL.md) |
| **Architecture Decision Records (ADRs)** | Formal records documenting key architectural choices (FastAPI async, dual ledger, multi-tenancy, pre-signed S3). | [`docs/design/adr/`](docs/design/adr/) |
| **C4 Context Model (Excalidraw)** | Editable vector scene for C4 System Context Model [`docs/diagrams/c4-context-model.excalidraw`](docs/diagrams/c4-context-model.excalidraw) |

---

## Tech Stack

- **Language / Runtime:** Python 3.12 (managed via [`uv`](https://github.com/astral-sh/uv))
- **Web Framework:** [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/) (ASGI)
- **Database & Driver:** PostgreSQL 16 + [`asyncpg`](https://github.com/MagicStack/asyncpg)
- **ORM / Migrations:** [SQLAlchemy 2.0 (Async Engine)](https://docs.sqlalchemy.org/en/20/)
- **Validation & Serialization:** [Pydantic v2](https://docs.pydantic.dev/)
- **Security & Auth:** [PyJWT](https://pyjwt.readthedocs.io/) (HMAC-SHA256) + Passlib (bcrypt)
- **Containerization:** Docker Compose
- **Payment & Storage Protocols:** Napas 24/7 VietQR, PayOS HMAC-SHA256, AWS S3 API

---

## Project Structure

```text
photobooth-backend/
├── docker-compose.yml          # PostgreSQL 16 container definition
├── pyproject.toml              # Dependencies & uv project configuration
├── uv.lock                     # Deterministic dependency lockfile
├── seed.py                     # Initial database seeding script
├── README.md                   # Project portal & quickstart
├── docs/                       # Engineering documentation
│   ├── DESIGN.md               # Software Design Document (C4, OOD, Data)
│   ├── SRS.md                  # Software Requirements Specification
│   ├── PROJECT_PROPOSAL.md     # Proposal & Milestone Plan
│   ├── diagrams/               # Architecture vector diagrams
│   │   └── c4-context-model.excalidraw # Editable C4 Context Excalidraw scene
│   ├── design/adr/             # Architecture Decision Records
│   └── guide/                  # Day 1 & Day 2 implementation guides
└── app/
    ├── main.py                 # FastAPI application factory & lifespan
    ├── core/
    │   ├── config.py           # Pydantic Settings & environment variables
    │   └── security.py         # Passlib bcrypt hashing & JWT tokens
    ├── db/
    │   ├── base.py             # Declarative Base & TimestampMixin
    │   └── session.py          # AsyncEngine, sessionmaker & get_db dependency
    ├── models/                 # SQLAlchemy 2.0 domain entities
    │   ├── tenant.py           # Franchise tenant boundary
    │   ├── user.py             # User accounts & RBAC roles
    │   ├── machine.py          # Kiosk fleet hardware & status
    │   ├── package.py          # Photo products & pricing
    │   ├── order.py            # Photobooth order aggregate root
    │   └── payment.py          # Payment intents & PaymentEvent audit ledger
    ├── schemas/                # Pydantic request/response schemas
    │   ├── auth.py             # Login & TokenPayload schemas
    │   ├── machine.py          # Machine response & pagination schemas
    │   ├── order.py            # Order request & response schemas
    │   └── payment.py          # Payment & Webhook schemas
    ├── services/               # Core business services
    │   └── payment/            # Payment provider abstraction & state machine
    │       ├── base.py         # Abstract PaymentProvider interface
    │       ├── payos.py        # FakePayOSProvider (VietQR / HMAC-SHA256)
    │       ├── state_machine.py # OrderStateMachine & transition rules
    │       └── service.py      # PaymentService orchestrator & deduplication
    └── api/
        ├── deps.py             # get_current_user & require_role dependencies
        └── v1/
            ├── api.py          # Unified API router mounting
            ├── auth.py         # POST /api/v1/auth/login
            ├── machines.py     # GET  /api/v1/machines
            ├── orders.py       # POST /api/v1/orders, GET /api/v1/orders/{id}, POST /payments, GET /payment-status
            └── webhooks.py     # POST /api/v1/webhooks/fake
```

---

## Getting Started

### 1. Prerequisites
Ensure you have the following installed:
- [Docker](https://www.docker.com/) & Docker Compose
- [`uv`](https://docs.astral.sh/uv/) (Fast Python package manager)

### 2. Environment Configuration
Copy the sample environment file:
```bash
cp .env.example .env
```

### 3. Start PostgreSQL Database
Launch the local PostgreSQL 16 container:
```bash
docker compose up -d
```
Verify the container is healthy:
```bash
docker compose ps
```

### 4. Install Dependencies
Sync project virtual environment using `uv`:
```bash
uv sync
```

### 5. Seed Database
Populate sample franchise tenant, admin/operator users, active machines, and photo packages:
```bash
uv run python seed.py
```

Default credentials provisioned by `seed.py`:
| Role | Username | Password |
| :--- | :--- | :--- |
| **Admin** | `admin_user` | `AdminPass123!` |
| **Operator** | `operator_user` | `OperatorPass123!` |

### 6. Run the Development Server
Start FastAPI with hot-reloading:
```bash
uv run uvicorn app.main:app --reload --port 8000
```

The interactive API documentation is accessible at:
- **Swagger UI:** [http://localhost:8000/api/v1/docs](http://localhost:8000/api/v1/docs)
- **ReDoc:** [http://localhost:8000/api/v1/redoc](http://localhost:8000/api/v1/redoc)
- **Health Check:** [http://localhost:8000/health](http://localhost:8000/health)

---

## Payment System & VietQR Integration (Day 2)

SnapSync includes a race-condition immune payment backend designed for automated photobooth kiosks in Vietnam:

### 1. Payment Endpoints
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/v1/orders/{id}/payments` | Creates a payment request, generating a Napas 24/7 VietQR code and PayOS checkout URL. |
| `POST` | `/api/v1/webhooks/fake` | Receives gateway webhooks with constant-time HMAC-SHA256 signature verification and dual-layer deduplication. |
| `GET` | `/api/v1/orders/{id}/payment-status` | Polled by photobooth kiosks to detect payment confirmation and unlock the camera. |

### 2. Handled Critical Scenarios
- **Valid Payment:** Order transitions `PENDING` → `PAID`, sets `paid_at`, records `PROCESSED` event.
- **Replay Protection (Duplicate Webhook):** Identical webhooks return `DUPLICATE` without double-transitioning the order.
- **Tampered / Invalid Signature:** Rejected immediately with **HTTP 400 Bad Request**.
- **Wrong Amount:** Flagged for manual operator review (`FLAGGED_FOR_REVIEW`).
- **Expired Order Paid:** Transitions to `LATE_PAYMENT`.
- **Unknown Order Code:** Recorded as an `UNMATCHED` payment event (`order_id = null`) without 500 error. A description that matches zero or several orders is also `UNMATCHED` (never guessed).
- **Provider Reports Failure (`code != "00"`):** Recorded as a `FAILED` event; the order is **not** paid.
- **Second Payment (different reference) on a Paid/Held Order:** Order in `PAID`, `COMPLETED`, `LATE_PAYMENT` or `FLAGGED_FOR_REVIEW` is left untouched and the transfer is recorded as `DUPLICATE_PAYMENT` so the double charge can be reviewed/refunded.
- **Payment on a Closed Order** (`CANCELLED`, `COMPLETED`, or a wrong amount on `EXPIRED`): Transition is not allowed, so the event is recorded as `REJECTED` for manual review. Returns 200 (no 500, no gateway retry storm).
- **Malformed Amount** (`"12.5"`, `null`, negative, missing): Rejected with **HTTP 400**.
- **Concurrency Challenge:** Two identical webhooks - or two *different-reference* webhooks for the same order - fired simultaneously via `asyncio.gather()` are serialized via PostgreSQL row locks (`SELECT ... FOR UPDATE` + `populate_existing`) and unique constraints. Exactly **one** transition occurs; the loser is `DUPLICATE` / `DUPLICATE_PAYMENT`.

### 3. Payment Sandbox Realities (payOS vs. VNPAY vs. MoMo)
- **payOS:** Operates directly on production APIs with personal CCCD and linked bank accounts (no dummy staging portal). SnapSync provides `FakePayOSProvider` to enable 100% offline development and automated CI testing without spending real money.
- **VNPAY / MoMo Multi-Gateway Support:** Built on the `PaymentProvider(ABC)` interface, allowing seamless extension to VNPAY Sandbox (`sandbox.vnpayment.vn` with test card NCB `9704198526191432198`) or MoMo Sandbox (`test-payment.momo.vn`) with zero database schema changes. See [`docs/guide/DAY_2_GUIDE.md`](docs/guide/DAY_2_GUIDE.md#16-payment-gateway-sandbox-reality--multi-provider-architecture-payos-vs-vnpay-vs-momo) for full architectural details.

---

## Automated Test Suite

Run the full pytest suite (40 unit & integration tests):
```bash
uv run pytest -v
```

> **Tests use a separate database.** The suite drops and recreates every table, so it
> never runs against your dev DB. It uses `TEST_DATABASE_URL`, or `<POSTGRES_DB>_test`
> (e.g. `photobooth_db_test`, created automatically) when unset. `conftest.py` refuses to
> run if the database name does not end in `_test`.

Expected output:
```text
tests/test_payment_api.py::test_scenario_valid_payment PASSED
tests/test_payment_api.py::test_scenario_same_webhook_twice PASSED
tests/test_payment_api.py::test_scenario_invalid_signature PASSED
tests/test_payment_api.py::test_scenario_wrong_amount PASSED
tests/test_payment_api.py::test_scenario_expired_order_paid PASSED
tests/test_payment_api.py::test_scenario_unknown_order_code PASSED
tests/test_payment_api.py::test_concurrency_challenge_identical_webhooks PASSED
tests/test_payment_api.py::test_concurrency_challenge_different_references PASSED
tests/test_payment_api.py::test_failed_provider_code_does_not_pay PASSED
tests/test_payment_api.py::test_payment_on_closed_order_is_recorded[CANCELLED] PASSED
tests/test_payment_api.py::test_payment_on_closed_order_is_recorded[COMPLETED] PASSED
tests/test_payment_api.py::test_wrong_amount_on_expired_order_is_recorded PASSED
tests/test_payment_api.py::test_second_payment_is_flagged[PAID] PASSED
tests/test_payment_api.py::test_second_payment_is_flagged[LATE_PAYMENT] PASSED
tests/test_payment_api.py::test_second_payment_is_flagged[FLAGGED_FOR_REVIEW] PASSED
tests/test_payment_api.py::test_description_match_finds_order PASSED
tests/test_payment_api.py::test_wildcard_description_does_not_match_or_500[%] PASSED
tests/test_payment_api.py::test_wildcard_description_does_not_match_or_500[_] PASSED
tests/test_payment_api.py::test_wildcard_description_does_not_match_or_500[%%%] PASSED
tests/test_payment_api.py::test_legacy_order_numeric_code_is_persisted PASSED
tests/test_payment_api.py::test_operator_can_complete_pending_order PASSED
tests/test_payment_api.py::test_bad_amount_rejected[12.5_0] PASSED
tests/test_payment_api.py::test_bad_amount_rejected[None] PASSED
tests/test_payment_api.py::test_bad_amount_rejected[abc] PASSED
tests/test_payment_api.py::test_bad_amount_rejected[-5] PASSED
tests/test_payment_api.py::test_bad_amount_rejected[True] PASSED
tests/test_payment_api.py::test_bad_amount_rejected[12.5_1] PASSED
tests/test_payment_api.py::test_missing_amount_rejected PASSED
tests/test_payment_api.py::test_status_filter_wildcards_not_expanded PASSED
tests/test_payment_provider.py::test_payment_request_generation PASSED
tests/test_payment_provider.py::test_canonicalize_data PASSED
tests/test_payment_provider.py::test_hmac_signature_verification_success PASSED
tests/test_payment_provider.py::test_hmac_signature_tampered_payload_rejected PASSED
tests/test_payment_provider.py::test_hmac_signature_invalid_signature_string PASSED
tests/test_state_machine.py::test_valid_transitions PASSED
tests/test_state_machine.py::test_invalid_terminal_transition PASSED
tests/test_state_machine.py::test_idempotent_transition PASSED
tests/test_state_machine.py::test_flagged_for_review_transition PASSED
tests/test_state_machine.py::test_late_payment_transition PASSED
tests/test_state_machine.py::test_case_insensitive_handling PASSED

============================= 40 passed in 34.17s =============================
```

## License

This project is developed as part of the Software Engineering Practice Track. All rights reserved.
