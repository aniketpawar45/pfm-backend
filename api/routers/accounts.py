from fastapi import APIRouter, Depends
from api.core.security import get_current_user_id, get_raw_jwt
from api.models.schemas import AccountCreate, AccountResponse
from api.services.financial_service import FinancialService

router = APIRouter(prefix="/accounts", tags=["accounts"])

@router.post("/", response_model=AccountResponse)
def create_account(data: AccountCreate, user_id: str = Depends(get_current_user_id), token: str = Depends(get_raw_jwt)):
    return FinancialService.create_account(user_id, token, data)
