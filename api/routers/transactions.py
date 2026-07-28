from fastapi import APIRouter, Depends
from api.core.security import get_current_user_id, get_raw_jwt
from api.models.schemas import TransactionCreate, TransactionResponse
from api.services.financial_service import FinancialService

router = APIRouter(prefix="/transactions", tags=["transactions"])

@router.post("/", response_model=TransactionResponse)
def create_transaction(data: TransactionCreate, user_id: str = Depends(get_current_user_id), token: str = Depends(get_raw_jwt)):
    return FinancialService.create_transaction(user_id, token, data)
