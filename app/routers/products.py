import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.audit import record_audit
from app.database import get_db
from app.dependencies import get_current_user, require_admin

router = APIRouter(prefix="/products", tags=["products"])
logger = logging.getLogger("order_api.products")


@router.get("", response_model=List[schemas.ProductOut])
def list_products(
    active_only: bool = Query(default=True),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(models.Product)
    if active_only:
        query = query.filter(models.Product.is_active.is_(True))
    return query.offset((page - 1) * page_size).limit(page_size).all()


@router.get("/{product_id}", response_model=schemas.ProductOut)
def get_product(product_id: str, db: Session = Depends(get_db)):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PRODUCT_NOT_FOUND", "message": f"No product with id {product_id}"},
        )
    return product


@router.post("", response_model=schemas.ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: schemas.ProductCreate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    existing = db.query(models.Product).filter(models.Product.sku == payload.sku).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "SKU_TAKEN", "message": f"SKU '{payload.sku}' already exists"},
        )

    product = models.Product(
        sku=payload.sku,
        name=payload.name,
        description=payload.description,
        price=payload.price,
    )
    db.add(product)
    db.flush()

    inventory = models.Inventory(
        product_id=product.id,
        quantity_on_hand=payload.initial_quantity,
        reorder_threshold=payload.reorder_threshold,
    )
    db.add(inventory)

    record_audit(
        db, user_id=admin.id, action="product.create", entity_type="Product",
        entity_id=product.id, details={"sku": product.sku, "initial_quantity": payload.initial_quantity},
    )
    db.commit()
    db.refresh(product)
    logger.info("Product created: %s (%s) by admin=%s", product.id, product.sku, admin.id)
    return product


@router.put("/{product_id}", response_model=schemas.ProductOut)
def update_product(
    product_id: str,
    payload: schemas.ProductUpdate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PRODUCT_NOT_FOUND", "message": f"No product with id {product_id}"},
        )

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(product, field, value)

    record_audit(
        db, user_id=admin.id, action="product.update", entity_type="Product",
        entity_id=product.id, details=changes,
    )
    db.commit()
    db.refresh(product)
    logger.info("Product updated: %s by admin=%s fields=%s", product.id, admin.id, list(changes))
    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_product(
    product_id: str,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    """Soft delete: products are deactivated, not hard-deleted, to preserve
    order history integrity (existing orders still reference this product)."""
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PRODUCT_NOT_FOUND", "message": f"No product with id {product_id}"},
        )
    product.is_active = False
    record_audit(db, user_id=admin.id, action="product.deactivate", entity_type="Product", entity_id=product.id)
    db.commit()
    logger.info("Product deactivated: %s by admin=%s", product.id, admin.id)
    return None
