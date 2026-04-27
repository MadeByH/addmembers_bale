# schemas.py
class StartLoginRequest(BaseModel):
    phone: str


class StartLoginResponse(BaseModel):
    ok: bool
    transaction_hash: str
    message: str


class ConfirmCodeRequest(BaseModel):
    phone: str
    code: str


class ProfileSchema(BaseModel):
    gender: Optional[str] = None
    birthdate: Optional[datetime] = None
    city: Optional[str] = None


class Account(BaseModel):
    id: int
    phone: str
    coins: int
    invitations_count: int

    class Config:
        from_attributes = True


class OrderCreate(BaseModel):
    join_link: str
    order_count: int
    reward_coins: int
    order_type: OrderType
    differentiation_factors: Optional[dict] = None


# --- Note on Relationships in Pydantic Schemas ---
# Pydantic schemas typically represent the data structure for API requests/responses.
# They usually do NOT directly include SQLAlchemy relationship objects (like 'owner', 'joined_accounts', 'participated_orders').
# When you fetch an Order or Account from the database and want to return it via API,
# you would typically:
# 1. Fetch the SQLAlchemy object.
# 2. Use Pydantic's `from_attributes=True` to parse the SQLAlchemy object into a Pydantic schema.
# 3. If you need related data (like the owner's details or the list of joined accounts),
#    you would fetch those separately in your API endpoint and include them as nested schemas
#    or separate fields in your API response model, NOT directly as SQLAlchemy relationship objects.
#    Example:
#    class OrderWithAccountDetails(Order):
#        account: Account # Nested Pydantic schema for the account that created the order
#
#    class OrderWithParticipants(Order):
#        participants: List[Account] # List of Pydantic schemas for accounts joined
