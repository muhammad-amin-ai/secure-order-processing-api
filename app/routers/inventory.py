import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.audit import record_audit
from app.database import get_db
from app.dependencies import get_current_user, require_admin

router = APIRouter(prefix="/inventory", tags=["inventory"])
logger = logging.getLogger("order_api.inventory")


def _get_inventory_or_404(db: Session, product_id: str) -> models.Inventory:
    inv = db.query(models.Inventory).filter(models.Inventory.product_id == product_id).first()
    if not inv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "INVENTORY_NOT_FOUND", "message": f"No inventory record for product {product_id}"},
        )
    return inv


@router.get("/{product_id}", response_model=schemas.InventoryOut)
def get_inventory(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _get_inventory_or_404(db, product_id)


@router.patch("/{product_id}", response_model=schemas.InventoryOut)
def adjust_inventory(
    product_id: str,
    payload: schemas.InventoryAdjust,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    inv = _get_inventory_or_404(db, product_id)

    new_quantity = inv.quantity_on_hand + payload.delta
    if new_quantity < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INSUFFICIENT_STOCK",
                "message": (
                    f"Adjustment of {payload.delta} would bring stock below zero "
                    f"(current: {inv.quantity_on_hand})"
                ),
            },
        )

    inv.quantity_on_hand = new_quantity
    record_audit(
        db, user_id=admin.id, action="inventory.adjust", entity_type="Inventory",
        entity_id=inv.id, details={"delta": payload.delta, "reason": payload.reason, "new_quantity": new_quantity},
    )
    db.commit()
    db.refresh(inv)
    logger.info(
        "Inventory adjusted for product=%s delta=%s new_qty=%s by admin=%s",
        product_id, payload.delta, new_quantity, admin.id,
    )
    return inv
