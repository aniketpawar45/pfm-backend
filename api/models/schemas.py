from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from decimal import Decimal
from enum import Enum

class AccountType(str, Enum):
    CHECKING = "checking"
    SAVINGS = "savings"
    CREDIT = "credit"
    CASH = "cash"
    INVESTMENT = "investment"

class TransactionType(str, Enum):
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"

class AccountCreate(BaseModel):
    name: str = Field(..., min_length=1)
    type: AccountType
    balance: Decimal = Field(default=Decimal("0.0"))

class AccountResponse(BaseModel):
    id: str
    name: str
    type: AccountType
    balance: Decimal

class TransactionCreate(BaseModel):
    account_id: str
    amount: Decimal = Field(..., gt=0)
    type: TransactionType
    transaction_date: datetime = Field(default_factory=datetime.utcnow)
    description: Optional[str] = None

class TransactionResponse(BaseModel):
    id: str
    account_id: str
    amount: Decimal
    type: TransactionType
    description: Optional[str]

class BulkDeleteRequest(BaseModel):
    ids: List[str]
