# Secure Order Processing API

**Arrowstack Backend Development Internship — Project 1 (Foundation)**

A REST API for products, customers, orders and inventory, built with
FastAPI + SQLAlchemy + PostgreSQL (SQLite supported out of the box for
zero-setup local development and testing).

---

## 1. Business Use Case

**Stakeholder:** the operations/e-commerce team at a small online retailer.

**Problem:** the team needs a reliable backend that lets customers place
orders against real-time stock levels, while giving staff visibility
into inventory, order status and a tamper-evident record of who changed
what and when.

**Decision enabled:** whether an order can be accepted (based on live
stock), and how staff should respond to low stock or order-status
questions from customers.

**Measurable benefit:** eliminates overselling (orders are only accepted
if stock actually covers them, inside a single database transaction),
and gives staff an audit trail for every sensitive action instead of
relying on tribal knowledge or spreadsheet edits.

## 2. Scope

**In scope:** product catalog, inventory tracking, customer accounts,
order placement with transactional stock deduction, order status
lifecycle, role-based authorization (admin vs. customer), structured
errors, audit logging, automated tests.

**Out of scope (see "Next Improvements"):** payment processing (the
`paid` status is set by an admin/staff action, not a real payment
gateway), email/notification delivery, and multi-warehouse inventory.

## 3. Architecture

```
app/
  main.py              FastAPI app, router registration, startup
  config.py            Settings (env-driven)
  database.py           SQLAlchemy engine/session
  models.py             ORM models (User, Product, Inventory, Order, OrderItem, AuditLog)
  schemas.py             Pydantic request/response schemas
  security.py            Password hashing + JWT
  dependencies.py         Auth dependencies (get_current_user, require_admin)
  audit.py                record_audit() helper
  error_handlers.py       Structured {error: {code, message}} responses
  logging_config.py       Console + rotating file logging
  routers/
    auth.py                POST /auth/register, POST /auth/login
    products.py             Product CRUD (public read, admin write)
    inventory.py             Inventory view + admin stock adjustment
    orders.py                 Order creation/listing/status transitions
    customers.py               GET /customers/me
tests/                    Pytest suite (31 tests, isolated SQLite per test)
```

**Data model:** `Product 1—1 Inventory`, `Order 1—N OrderItem —N Product`,
`User 1—N Order`. `AuditLog` references `User` but is otherwise
independent, so it survives even if related entities change.

## 4. Key Design Decisions

| Decision | Rationale |
|---|---|
| SQLite default, PostgreSQL via `DATABASE_URL` | Zero-setup local dev/testing; matches the recommended production stack without forcing a DB server for evaluation. |
| Soft-delete products (`is_active=False`) instead of hard delete | Existing orders must keep referencing valid products for historical accuracy. |
| Order creation is one DB transaction | Stock check + deduction + order/item creation either all succeed or all roll back — no partially-charged stock. |
| `SELECT ... FOR UPDATE` row locking on PostgreSQL/MySQL, skipped on SQLite | Prevents two concurrent orders from overselling the same unit on a real production database; SQLite has no row-level locking. |
| Explicit order status state machine (`pending → paid/cancelled`, `paid → fulfilled/cancelled`) | Prevents nonsensical transitions like `fulfilled → pending` via the API. |
| Cancelling an order restocks its items | Keeps inventory accurate; a cancelled order shouldn't permanently "lose" stock. |
| Structured `{error: {code, message}}` on every error path (validation, HTTP, unhandled) | One predictable shape for API consumers regardless of failure type. |
| JWT with role embedded in the token | Stateless authorization; `require_admin` dependency checks the role without an extra DB round-trip for role checks (the user row is still loaded to confirm the account is active). |
| Audit log written in the same transaction as the action it records | Guarantees the audit trail never drifts out of sync with the data. |

## 5. Setup

### Option A — Local, SQLite (fastest)

```bash
python3 -m venv venv
. venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env          # defaults already point at SQLite
uvicorn app.main:app --reload
```

API docs: http://127.0.0.1:8000/docs

### Option B — PostgreSQL via Docker Compose

```bash
docker compose up --build
```

This starts PostgreSQL and the API together, with `DATABASE_URL` already
pointed at the containerized database.

## 6. Running the Tests

```bash
pip install -r requirements-dev.txt
pytest -v
```

31 tests covering: registration/login and validation, role-based
authorization on every protected route, product CRUD, inventory
adjustment (including the "can't go negative" guard), and the order
flow — successful creation with stock deduction, duplicate line-item
merging, insufficient-stock rollback (asserting stock is *unchanged*
and no order is persisted), ownership checks, and the full status
transition state machine including auto-restock on cancellation.

## 7. API Overview

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/register` | none | Create a customer account |
| POST | `/auth/login` | none | Get a JWT (`OAuth2PasswordRequestForm`: `username`=email, `password`) |
| GET | `/customers/me` | any user | Current user's profile |
| GET | `/products` | none | List active products (paginated) |
| GET | `/products/{id}` | none | Get one product |
| POST | `/products` | admin | Create product (+ initial inventory) |
| PUT | `/products/{id}` | admin | Update product fields |
| DELETE | `/products/{id}` | admin | Deactivate (soft delete) a product |
| GET | `/inventory/{product_id}` | any user | View stock level |
| PATCH | `/inventory/{product_id}` | admin | Adjust stock by a signed delta with a reason |
| POST | `/orders` | any user | Place an order (transactional stock deduction) |
| GET | `/orders` | any user | List own orders (admin sees all) |
| GET | `/orders/{id}` | owner or admin | Get one order |
| PATCH | `/orders/{id}/status` | admin | Move order through its status lifecycle |
| GET | `/health` | none | Liveness check |

Interactive docs (Swagger UI) are auto-generated at `/docs`, and the raw
OpenAPI schema at `/openapi.json`.

## 8. Quick Manual Walkthrough

```bash
# Register + log in
curl -X POST localhost:8000/auth/register -H "Content-Type: application/json" \
  -d '{"email":"jane@example.com","password":"Password123"}'
TOKEN=$(curl -s -X POST localhost:8000/auth/login \
  -d "username=jane@example.com&password=Password123" | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# An admin (promote a user's role directly in the DB for the first admin,
# then use their token below) creates a product:
curl -X POST localhost:8000/products -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sku":"WIDGET-1","name":"Widget","price":"19.99","initial_quantity":50}'

# Customer places an order:
curl -X POST localhost:8000/orders -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"items":[{"product_id":"<product_id>","quantity":2}]}'
```

> There is intentionally no public "become admin" endpoint. For local
> testing, promote a user by setting `role='admin'` on their row
> directly (see `tests/conftest.py::admin_auth_headers` for the same
> pattern used in the test suite).

## 9. Known Limitations

- No real payment gateway integration — `paid` is an admin-set status.
- No pagination on `/orders` or `/inventory` history (fine at project
  scale; would need it before production volume).
- No refresh tokens — access tokens simply expire after 60 minutes and
  the user must log in again.
- Row-level locking for stock deduction only applies on PostgreSQL/MySQL;
  under SQLite (dev/test only) concurrent-order races are not locked at
  the row level, though SQLite's own writer serialization still prevents
  data corruption.
- No email verification on registration.

## 10. Next Improvements (Extension Ideas)

- Replace `Base.metadata.create_all()` with Alembic migrations for
  reproducible schema evolution.
- Add a `/metrics` endpoint (e.g. Prometheus) for order throughput,
  error rates, and low-stock alerts — ties into the Week 2 project's
  notification service.
- Add refresh tokens + token revocation.
- Add rate limiting on `/auth/login` to slow down credential stuffing.
- Multi-warehouse inventory (`Inventory` per warehouse instead of per
  product).

## 11. Evidence / Reproducibility Checklist

- [x] Requirements & design documented above (sections 1–4)
- [x] Version-controlled, organized source tree
- [x] 31 automated tests, all passing (`pytest -v`)
- [x] Structured error responses verified by tests
- [x] Audit log covers registration, product create/update/deactivate,
      inventory adjustment, order creation, and order status changes
- [x] README doubles as the handoff document a mentor can follow
      end-to-end without undocumented steps
