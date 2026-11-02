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
│   ├── design/adr/             # Architecture Decision Records
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
    │   └── order.py            # Photobooth order aggregate root
    ├── schemas/                # Pydantic request/response schemas
    │   ├── auth.py             # Login & TokenPayload schemas
    │   ├── machine.py          # Machine response & pagination schemas
    │   └── order.py            # Order request & response schemas
    └── api/
        ├── deps.py             # get_current_user & require_role dependencies
        └── v1/
            ├── api.py          # Unified API router mounting
            ├── auth.py         # POST /api/v1/auth/login
            ├── machines.py     # GET  /api/v1/machines
            └── orders.py       # POST /api/v1/orders, GET /api/v1/orders/{id}
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

## License

This project is developed as part of the Software Engineering Practice Track. All rights reserved.
