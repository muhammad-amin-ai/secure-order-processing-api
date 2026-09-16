# Work Log — Secure Order Processing API

## Week 1 — Research, Requirements, Design
- Identified stakeholder (operations/e-commerce team) and primary
  decision enabled by the system (accept/reject an order based on live
  stock).
- Wrote requirements: RESTful endpoints, auth/authorization, input
  validation, structured errors, audit logging, automated tests.
- Chose stack: Python / FastAPI / PostgreSQL (SQLite for local dev and
  tests) / JWT auth, per the recommended technology stack.
- Designed the data model: User, Product, Inventory (1–1 with Product),
  Order, OrderItem, AuditLog.
- Set up the project skeleton (`app/` package, routers, config,
  database session handling).

## Week 2 — Core Implementation
- Implemented auth (register/login, password hashing, JWT issuance).
- Implemented product CRUD with admin-only writes and public reads.
- Implemented inventory view + admin stock adjustment with a
  can't-go-negative guard.
- Implemented order creation: single-transaction stock validation +
  deduction + order/item persistence, with duplicate line-item merging.
- Added the audit logging helper and wired it into every state-changing
  route.

## Week 3 — Testing, Validation, Refinement
- Wrote the automated test suite (31 tests): auth, products, inventory,
  orders — including the insufficient-stock rollback case (asserts
  stock is untouched and no order persists on failure).
- Fixed a bug found by the test suite: `record_audit()` failed to
  JSON-encode `Decimal` values (product price) when logging a product
  update. Fixed by adding a `default=` encoder to `json.dumps`.
- Added the order status state machine (`pending → paid/cancelled`,
  `paid → fulfilled/cancelled`) with restock-on-cancel behavior.
- Ran a manual smoke test against the live `uvicorn` server: `/health`
  and the full route list resolve correctly.

## Week 4 — Finalization, Documentation, Packaging
- Wrote README.md covering business use case, architecture, setup
  (SQLite and Docker/PostgreSQL paths), API overview, manual walkthrough,
  known limitations, and next-improvement ideas.
- Added Dockerfile + docker-compose.yml for a PostgreSQL-backed run.
- Added `.env.example`, `.gitignore`, pinned `requirements.txt`.
- Final full test run: 31/31 passing.
