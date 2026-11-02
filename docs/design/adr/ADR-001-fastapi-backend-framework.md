# ADR-001: Selection of FastAPI and Asynchronous SQLAlchemy 2.0 for High-Throughput Cloud Backend

| Metadata | Details |
| :--- | :--- |
| **ADR ID** | ADR-001 |
| **Status** | Accepted |
| **Date** | 2025-10-15 |
| **Author** | Backend Architecture Lead |
| **Deciders** | Lead Architect, Full-Stack Lead, Database Specialist |

---

## Context
The SnapSync platform operates a distributed, multi-tenant fleet of automated photobooth kiosks. The backend service serves two drastically different traffic profiles:
1. High-frequency client polling from hundreds of edge kiosks inquiring about payment completion status every 2 seconds (`GET /api/v1/orders/{id}/payment-status`).
2. Low-latency, mission-critical webhook ingest from payment facilitators (`POST /api/v1/webhooks/payos`) which must complete within ≤ 150 ms (P99) under concurrent load spikes to prevent gateway timeout retries.
3. Strict I/O efficiency without bloated infrastructure costs.

Historically, synchronous Python web frameworks (such as Django or Flask) rely on worker-process thread pools (e.g. Gunicorn sync workers). Under high-concurrency polling and bursty webhook streams, thread pools quickly experience worker starvation, resulting in latency spikes, connection timeouts, and high RAM consumption.

## Decision
We adopt **FastAPI** running on the **Uvicorn** ASGI web server, coupled with **SQLAlchemy 2.0 (Async Engine)** and **asyncpg** as the PostgreSQL database driver.
- All routing endpoints and database operations are non-blocking coroutines (`async def`).
- Input validation and schema serialization are enforced via **Pydantic v2** compiled in Rust for maximum serialization throughput.
- Dependency injection (`fastapi.Depends`) manages database session lifecycles (`AsyncSession`), authentication, and tenant tenancy contexts cleanly across the request pipeline.

## Alternatives Considered
1. **Django + Django REST Framework (DRF):**
   - *Pros:* Batteries-included ORM, mature built-in admin portal, rich ecosystem.
   - *Cons:* Historically synchronous core. Django 4.x/5.x async ORM is still maturing and carries substantial overhead; thread-per-request model requires significantly more RAM per concurrent user; P95 latency is ~3–5× higher than FastAPI under concurrent I/O load.
2. **Node.js + Express / NestJS + Prisma:**
   - *Pros:* Native asynchronous event loop, fast JSON processing.
   - *Cons:* TypeScript backend diverges from the team's core Python data science and computer vision pipelines (frame rendering, OpenCV, future AI background removal); Prisma ORM connection management introduces connection pool latency in serverless/containerized environments.
3. **Go (Golang) + Gin / Fiber:**
   - *Pros:* Ultimate raw performance, minuscule memory footprint, statically typed binary.
   - *Cons:* Slower initial development velocity; lacks high-level ORM migration maturity comparable to SQLAlchemy + Alembic; higher complexity for rapid iterations of multi-tenant domain models.

## Consequences
- **Positive:**
  - Sustains > 1,500 requests per second per container instance with P95 latency < 50 ms.
  - Native Python `async`/`await` eliminates thread blocking during database round-trips and external PayOS API calls.
  - Automatic OpenAPI / Swagger UI documentation generation reduces frontend-backend integration friction.
  - Strict type hints with Pydantic v2 catch malformed payloads at the edge before hitting business logic.
- **Negative / Trade-offs:**
  - Developers must exercise vigilance to prevent blocking synchronous calls (e.g., standard `time.sleep()`, synchronous `requests`, or heavy synchronous CPU rendering) on the main asyncio event loop.
  - Async SQLAlchemy requires explicit eager loading (`selectinload`) to prevent `MissingGreenlet` exceptions during ORM relationship traversal.
