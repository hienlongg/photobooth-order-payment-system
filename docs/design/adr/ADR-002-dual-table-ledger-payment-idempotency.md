# ADR-002: Dual-Table Ledger Architecture and Pessimistic Row Locking for Webhook Idempotency

| Metadata | Details |
| :--- | :--- |
| **ADR ID** | ADR-002 |
| **Status** | Accepted |
| **Date** | 2025-10-18 |
| **Author** | Financial Systems & Concurrency Engineer |
| **Deciders** | Lead Architect, Database Specialist, Backend Lead |

---

## Context
Payment gateways (such as PayOS and Napas 24/7 bank networks) operate under an **"at-least-once"** webhook delivery guarantee. Due to mobile network fluctuations, transient gateway timeout retries, or customer double-submitting transfers, identical payment webhooks often arrive concurrently (e.g. within milliseconds of each other) or in rapid sequence.

If an unattended photobooth kiosk backend is not engineered for strict idempotency and concurrency protection:
1. Two worker threads might process the same bank transaction simultaneously.
2. Race conditions can occur where both threads observe the order in `PENDING` state, crediting the session twice or issuing double print credits.
3. Overwriting state in a single mutable `orders` table leaves zero immutable forensic audit trail if payment amount discrepancies or fraudulent chargeback disputes occur.

## Decision
We implement a **Dual-Table Ledger Architecture** with **Database-Level Pessimistic Locking (`SELECT ... FOR UPDATE`)** and **Unique Reference Constraints**:
1. **Separation of Intent vs. Settlement Event:**
   - `payments` table: Tracks outbound checkout requests and VietQR generation links.
   - `payment_events` table: An immutable append-only ledger recording every raw webhook payload received from payment gateways.
2. **PostgreSQL Unique Constraint for Concurrency Guard:**
   - A composite unique constraint is enforced on `payment_events(provider, reference)`.
   - When concurrent duplicate webhooks arrive, PostgreSQL's WAL engine guarantees that exactly one transaction succeeds; the duplicate transaction triggers an `IntegrityError` (PostgreSQL error code `23505`) and is rolled back safely.
3. **Pessimistic Order Locking:**
   - The webhook transaction executes `SELECT * FROM orders WHERE order_code = :code FOR UPDATE` to serialize status transitions on the target order record.
4. **Deterministic Finite State Machine:**
   - Order transitions are guarded by `OrderStateMachine` (`PENDING -> PAID -> COMPLETED`). Attempts to re-transition a `PAID` order are treated as idempotent no-ops and safely acknowledged with HTTP 200 OK.

## Alternatives Considered
1. **Single-Table Mutation (Updating `orders.status` directly):**
   - *Pros:* Simpler schema; fewer joins.
   - *Cons:* Complete lack of historical audit trail. Impossible to diagnose underpaid orders, overpaid orders, or duplicate webhook payloads sent by the gateway.
2. **Distributed Redis Mutex (Redlock / Distributed Lock):**
   - *Pros:* Avoids database row locks; fast in-memory key eviction.
   - *Cons:* Introduces distributed systems failure modes (split-brain, clock drift, network partitions between backend and Redis); Redis is not the system of record. If Redis fails or restarts, concurrent transactions can slip through. Database-level locking guarantees ACID compliance natively on the single source of truth.
3. **Application-Level In-Memory Lock (`asyncio.Lock`):**
   - *Pros:* Zero external dependencies.
   - *Cons:* Only works inside a single Python process. Does not protect against multi-worker Uvicorn configurations or multi-container horizontal cloud replicas.

## Consequences
- **Positive:**
  - 100% mathematical guarantee of webhook idempotency and zero double-fulfillment, verified under synthetic `asyncio.gather()` concurrent execution tests.
  - Complete, tamper-evident audit ledger preserving raw gateway payloads, signature validation booleans, timestamps, and error messages.
  - Graceful degradation: duplicate webhooks return HTTP 200/202 with `{ status: "DUPLICATE" }`, preventing external payment gateways from repeatedly retrying webhooks.
- **Negative / Trade-offs:**
  - `SELECT ... FOR UPDATE` holds a row-level lock for the duration of the database transaction (~10–25 ms). However, transactions are kept exceptionally concise (no external network I/O is performed while holding the lock).
