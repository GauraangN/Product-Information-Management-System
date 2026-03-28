from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime

class ProductCreate(BaseModel):
    name: str
    sku: str
    raw_input: Optional[str] = None
    price: Optional[float] = None
    category: Optional[str] = None

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    attributes: Optional[dict[str, Any]] = None
    price: Optional[float] = None
    category: Optional[str] = None

class ProductOut(BaseModel):
    id: int
    name: str
    sku: str
    description: Optional[str]
    attributes: Optional[dict[str, Any]]
    price: Optional[float]
    category: Optional[str]
    woo_product_id: Optional[int]
    created_at: Optional[datetime]

    class Config:
        from_attributes = True

class SearchQuery(BaseModel):
    query: str
    top_k: int = 5