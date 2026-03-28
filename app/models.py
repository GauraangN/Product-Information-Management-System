from sqlalchemy import Column, Integer, String, Text, Float, DateTime, JSON
from sqlalchemy.sql import func
from app.database import Base

class Product(Base):
    __tablename__ = "products"

    id             = Column(Integer, primary_key=True, index=True)
    name           = Column(String(255), nullable=False)
    sku            = Column(String(100), unique=True, index=True)
    description    = Column(Text)
    raw_input      = Column(Text)
    attributes     = Column(JSON)
    price          = Column(Float)
    category       = Column(String(100))
    woo_product_id = Column(Integer)
    synced_at      = Column(DateTime)
    created_at     = Column(DateTime, server_default=func.now())
    updated_at     = Column(DateTime, onupdate=func.now())
    embedding      = Column(JSON)   # stores embedding as plain float list