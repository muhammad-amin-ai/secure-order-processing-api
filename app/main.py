"""
Secure Order Processing API
============================
A REST API for products, customers, orders and inventory with
authentication/authorization, input validation, transactional order
processing and audit logging.

Run locally:
    uvicorn app.main:app --reload

See README.md for full setup, usage and testing instructions.
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.error_handlers import register_error_handlers
from app.logging_config import configure_logging
from app.routers import auth, products, inventory, orders, customers

configure_logging()
logger = logging.getLogger("order_api")

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description=(
        "REST API for products, customers, orders and inventory with "
        "validation, authorization, transactions and audit logs."
    ),
)

# In a real deployment, restrict this to known frontend origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)

app.include_router(auth.router)
app.include_router(products.router)
app.include_router(inventory.router)
app.include_router(orders.router)
app.include_router(customers.router)


@app.on_event("startup")
def on_startup():
    # For this project, tables are created directly from the ORM models.
    # In a production setting this would be replaced by Alembic migrations
    # (see README "Next Improvements").
    Base.metadata.create_all(bind=engine)
    logger.info("%s started (env=%s, db=%s)", settings.app_name, settings.environment, engine.url)


@app.get("/health", tags=["meta"])
def health_check():
    return {"status": "ok"}
