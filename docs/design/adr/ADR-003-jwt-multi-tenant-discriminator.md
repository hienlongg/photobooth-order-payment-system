# ADR-003: Shared Database Multi-Tenancy via Tenant Discriminator and JWT Claims

| Metadata | Details |
| :--- | :--- |
| **ADR ID** | ADR-003 |
| **Status** | Accepted |
| **Date** | 2025-10-21 |
| **Author** | Security & Cloud Architect |
| **Deciders** | Lead Architect, Security Engineer, Product Manager |

---

## Context
The SnapSync platform is a B2B SaaS system serving independent photobooth franchise operators (tenants). Each tenant manages their own fleet of kiosks, pricing packages, revenue records, and staff users. Strict data isolation is legally and commercially required: Tenant A must never view, mutate, or access machines, orders, or financial transactions belonging to Tenant B.

We evaluated three multi-tenant architectural patterns:
1. Database-per-tenant (separate PostgreSQL server or database per customer).
2. Schema-per-tenant (separate PostgreSQL schema per customer inside a single database).
3. Shared database with tenant discriminator column (`tenant_id`) enforced at the application/ORM layer.

## Decision
We adopt **Shared Database with Tenant Discriminator Column (`tenant_id`)** combined with **Cryptographically Signed Stateless JWT Authentication and Role-Based Access Control (RBAC)**:
1. Every domain table (`users`, `machines`, `packages`, `orders`, `payments`, `payment_events`) includes a mandatory `tenant_id UUID NOT NULL` foreign key referencing `tenants(id)` with `ON DELETE CASCADE`.
2. Composite indexes are placed on `(tenant_id, created_at)`, `(tenant_id, status)`, and `(tenant_id, is_active)` across all operational tables to guarantee high-performance tenant-filtered queries.
3. Upon login, the backend issues an HMAC-SHA256 signed JSON Web Token (JWT) containing the user's `sub` (User UUID), `tenant_id`, and `role` (`admin`, `operator`, `customer`).
4. FastAPI dependency injection (`require_role` and `get_current_user` in `app/api/deps.py`) inspects the token on every authenticated request, extracts the `tenant_id`, and automatically scopes database queries (`WHERE model.tenant_id == current_user.tenant_id`). Cross-tenant access attempts return HTTP 404/403.
5. In addition, globally unique machine codes are scoped per tenant via PostgreSQL unique constraint `UniqueConstraint("tenant_id", "machine_code", name="uq_tenant_machine_code")`.

## Alternatives Considered
1. **Database-per-Tenant:**
   - *Pros:* Ultimate physical isolation; individual database backup/restore.
   - *Cons:* Prohibitive operational and hosting costs for dozens of small franchise kiosks; complex connection pool management (exhausting connection limits); high overhead for schema migrations across hundreds of tenant databases.
2. **Schema-per-Tenant:**
   - *Pros:* Logical isolation within a single database.
   - *Cons:* Alembic migration management becomes cumbersome; PostgreSQL metadata tables bloat with thousands of tables; dynamic schema switching (`SET search_path`) introduces connection pooling hazards with `asyncpg` pooled connections.
3. **PostgreSQL Row-Level Security (RLS) alone:**
   - *Pros:* Database-enforced isolation via session variables (`SET LOCAL app.current_tenant_id`).
   - *Cons:* In an async pooled architecture, executing `SET LOCAL` on every connection acquisition adds network overhead; misconfigured connection recycling can accidentally leak session state. Therefore, application-level ORM scoping is primary, with RLS available as an optional secondary layer.

## Consequences
- **Positive:**
  - Highly cost-effective infrastructure; single PostgreSQL instance easily supports hundreds of tenants with minimal idle memory consumption.
  - Simplified database migrations: Alembic runs a single migration suite affecting all tenants simultaneously.
  - Stateless JWTs allow seamless horizontal scaling of backend API containers behind a load balancer without sticky sessions.
- **Negative / Trade-offs:**
  - Developers must ensure every new database query explicitly filters by `current_user.tenant_id`. Standardized dependency injection in FastAPI routers mitigates human error.
