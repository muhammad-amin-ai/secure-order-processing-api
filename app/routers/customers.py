import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.dependencies import get_current_user

router = APIRouter(prefix="/customers", tags=["customers"])
logger = logging.getLogger("order_api.customers")


@router.get("/me", response_model=schemas.UserOut)
def read_my_profile(current_user: models.User = Depends(get_current_user)):
    return current_user
