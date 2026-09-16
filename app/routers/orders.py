import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app import models, schemas
from app.audit import record_audit
from app.database import get_db
from app.dependencies import get_current_user, require_admin

router = APIRouter(prefix="/orders", tags=["orders"])
logger = logging.getLogger("order_api.orders")


def _order_query(db: Session):
    return db.query(models.Order).options(
        joinedload(models.Order.items).joinedload(models.OrderItem.product)
    )


@router.post("", response_model=schemas.OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: schemas.OrderCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Creates an order for the current user. The whole operation -- stock
    validation, stock deduction and order/order-item creation -- happens
    in a single DB transaction: if anything fails (missing product,
    inactive product, insufficient stock) the transaction is rolled back
    and no partial state is left behind.

    Concurrency note: this uses SELECT ... FOR UPDATE on dialects that
    support row locking (e.g. PostgreSQL, the recommended production
    database) to prevent two concurrent orders from overselling the same
    unit of stock. SQLite (used for local/dev/test runs) does not support
    row-level locking, so under SQLite concurrent requests are only
    protected by the database's own writer serialization.
    """
    if not payload.items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "EMPTY_ORDER", "message": "An order must contain at least one item"},
        )

    # Merge duplicate product_id entries so "2x A, then 3x A" == "5x A".
    merged: dict[str, int] = {}
    for item in payload.items:
        merged[item.product_id] = merged.get(item.product_id, 0) + item.quantity

    order = models.Order(customer_id=current_user.id, status=models.OrderStatus.PENDING)
    db.add(order)
    db.flush()

    total = 0
    supports_row_lock = db.bind.dialect.name in ("postgresql", "mysql")

    for product_id, quantity in merged.items():
        product = db.query(models.Product).filter(models.Product.id == product_id).first()
        if not product or not product.is_active:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "PRODUCT_NOT_FOUND", "message": f"No active product with id {product_id}"},
            )

        inv_query = db.query(models.Inventory).filter(models.Inventory.product_id == product_id)
        if supports_row_lock:
            inv_query = inv_query.with_for_update()
        inventory = inv_query.first()

        if not inventory or inventory.quantity_on_hand < quantity:
            db.rollback()
            available = inventory.quantity_on_hand if inventory else 0
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INSUFFICIENT_STOCK",
                    "message": (
                        f"Product '{product.name}' has only {available} unit(s) available, "
                        f"but {quantity} were requested"
                    ),
                },
            )

        inventory.quantity_on_hand -= quantity
        line_total = product.price * quantity
        total += line_total

        order_item = models.OrderItem(
            order_id=order.id,
            product_id=product.id,
            quantity=quantity,
            unit_price=product.price,
        )
        db.add(order_item)

    order.total_amount = total
    record_audit(
        db, user_id=current_user.id, action="order.create", entity_type="Order",
        entity_id=order.id, details={"total_amount": str(total), "item_count": len(merged)},
    )
    db.commit()

    order = _order_query(db).filter(models.Order.id == order.id).first()
    logger.info("Order created: %s by user=%s total=%s", order.id, current_user.id, total)
    return order


@router.get("", response_model=List[schemas.OrderOut])
def list_orders(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Customers see only their own orders; admins see every order."""
    query = _order_query(db)
    if current_user.role != models.UserRole.ADMIN:
        query = query.filter(models.Order.customer_id == current_user.id)
    return query.order_by(models.Order.created_at.desc()).all()


@router.get("/{order_id}", response_model=schemas.OrderOut)
def get_order(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    order = _order_query(db).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ORDER_NOT_FOUND", "message": f"No order with id {order_id}"},
        )
    if current_user.role != models.UserRole.ADMIN and order.customer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "You do not have access to this order"},
        )
    return order


# Only these status transitions are allowed, to keep the order lifecycle sane.
_ALLOWED_TRANSITIONS = {
    models.OrderStatus.PENDING: {models.OrderStatus.PAID, models.OrderStatus.CANCELLED},
    models.OrderStatus.PAID: {models.OrderStatus.FULFILLED, models.OrderStatus.CANCELLED},
    models.OrderStatus.CANCELLED: set(),
    models.OrderStatus.FULFILLED: set(),
}


@router.patch("/{order_id}/status", response_model=schemas.OrderOut)
def update_order_status(
    order_id: str,
    payload: schemas.OrderStatusUpdate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ORDER_NOT_FOUND", "message": f"No order with id {order_id}"},
        )

    if payload.status not in _ALLOWED_TRANSITIONS.get(order.status, set()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_TRANSITION",
                "message": f"Cannot move order from '{order.status.value}' to '{payload.status.value}'",
            },
        )

    # If an order is cancelled before fulfillment, restock the items.
    if payload.status == models.OrderStatus.CANCELLED:
        for item in order.items:
            inv = db.query(models.Inventory).filter(models.Inventory.product_id == item.product_id).first()
            if inv:
                inv.quantity_on_hand += item.quantity

    previous_status = order.status
    order.status = payload.status
    record_audit(
        db, user_id=admin.id, action="order.status_change", entity_type="Order",
        entity_id=order.id, details={"from": previous_status.value, "to": payload.status.value},
    )
    db.commit()

    order = _order_query(db).filter(models.Order.id == order_id).first()
    logger.info("Order %s status changed %s -> %s by admin=%s", order_id, previous_status.value, payload.status.value, admin.id)
    return order
