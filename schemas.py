# schemas.py
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

# --- Forward Declarations for recursive relationships ---
# Necessary when a model refers to another model that is not yet defined
# or when there's a circular dependency.
class Account(BaseModel):
    pass
class Order(BaseModel):
    pass
class User(BaseModel):
    pass

# --- Schemas for User model ---
class UserBase(BaseModel):
    bale_user_id: int
    # phone removed from base as it might be optional/specific to creation/update

class UserCreate(UserBase):
    phone: Optional[str] = None # Explicitly optional for creation

class UserWithAccounts(UserBase): # New schema to include accounts
    id: int
    # phone: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    accounts: List[Account] = [] # List of Account schemas

    class Config:
        from_attributes = True

# Define User after Account and Order are potentially defined or will be forward declared
class User(UserBase):
    id: int
    # phone: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# --- Schemas for Account model ---
class AccountBase(BaseModel):
    is_blocked: bool = True
    phone: Optional[str] = None
    session_data: Optional[str] = None
    status: Optional[str] = None
    coins: int = 0
    invitations_count: int = 0
    vip_status: Optional[str] = None
    gender: Optional[str] = None
    birthdate: Optional[date] = None
    city: Optional[str] = None
    last_seen: Optional[datetime] = None

class AccountCreate(AccountBase):
    owner_id: int # Required for creation
    # phone is already in AccountBase

class AccountWithUserAndOrders(AccountBase): # New schema to include owner and orders
    id: int
    owner_id: int
    created_at: datetime
    updated_at: datetime
    owner: User # Nested User schema for the owner
    orders: List[Order] = [] # List of Order schemas

    class Config:
        from_attributes = True

# Define Account after User and Order are potentially defined or will be forward declared
class Account(AccountBase):
    id: int
    owner_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# --- Schemas for Order model ---
class OrderBase(BaseModel):
    order_type: str
    order_status: str = "pending"
    order_count: int = 1
    order_details: Dict[str, Any] = Field(default_factory=dict)
    # Assuming username, profile_picture_url, differentiation_factors are part of the order data
    username: Optional[str] = None
    profile_picture_url: Optional[str] = None
    differentiation_factors: Optional[str] = None

class OrderCreate(OrderBase):
    account_id: int # Required for creation

class OrderWithAccount(OrderBase): # New schema to include the associated account
    id: int
    account_id: int
    created_at: datetime
    updated_at: datetime
    account: Account # Nested Account schema for the order's account

    class Config:
        from_attributes = True

# Define Order after Account is potentially defined or will be forward declared
class Order(OrderBase):
    id: int
    account_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# --- Updated Forward Declarations and Final Models ---
# Re-defining them here to ensure they point to the most complete versions
# This is a common pattern to resolve recursive Pydantic models.

# User model potentially referencing Accounts
class User(UserBase):
    id: int
    # phone: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    accounts: List[Account] = [] # Reference to the Account schema

    class Config:
        from_attributes = True

# Account model potentially referencing User and Orders
class Account(AccountBase):
    id: int
    owner_id: int
    created_at: datetime
    updated_at: datetime
    owner: User # Reference to the User schema
    orders: List[Order] = [] # Reference to the Order schema

    class Config:
        from_attributes = True

# Order model potentially referencing Account
class Order(OrderBase):
    id: int
    account_id: int
    created_at: datetime
    updated_at: datetime
    account: Account # Reference to the Account schema

    class Config:
        from_attributes = True

# --- Example API Response Models ---
# These are models you might return from your API endpoints.

# To get a user with their accounts, but without deeply nested orders within accounts:
class UserWithAccountsSummary(UserBase):
    id: int
    # phone: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    accounts: List[AccountBase] # Only basic account info

    class Config:
        from_attributes = True

# To get an account with its owner and a summary of its orders:
class AccountWithUserAndOrderSummaries(AccountBase):
    id: int
    owner_id: int
    created_at: datetime
    updated_at: datetime
    owner: User # Full user info for the owner
    orders: List[OrderBase] # Only basic order info

    class Config:
        from_attributes = True

# To get an order with its associated account details:
class OrderWithAccountDetails(OrderBase):
    id: int
    account_id: int
    created_at: datetime
    updated_at: datetime
    account: Account # Full account info for the order's account

    class Config:
        from_attributes = True

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
