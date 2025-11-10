"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

# Example schemas (replace with your own):

class User(BaseModel):
    """
    Users collection schema
    Collection name: "user" (lowercase of class name)
    """
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    address: str = Field(..., description="Address")
    age: Optional[int] = Field(None, ge=0, le=120, description="Age in years")
    is_active: bool = Field(True, description="Whether user is active")

class Product(BaseModel):
    """
    Products collection schema
    Collection name: "product" (lowercase of class name)
    """
    title: str = Field(..., description="Product title")
    description: Optional[str] = Field(None, description="Product description")
    price: float = Field(..., ge=0, description="Price in dollars")
    category: str = Field(..., description="Product category")
    in_stock: bool = Field(True, description="Whether product is in stock")

# App-specific schemas
class Analysis(BaseModel):
    """
    YouTube content analyzer results
    Collection name: "analysis"
    """
    topic: str = Field(..., description="Video topic or idea")
    keywords: List[str] = Field(default_factory=list, description="List of keywords")
    niche: Optional[str] = Field(None, description="Content niche")
    audience: Optional[str] = Field(None, description="Target audience description")
    format: str = Field(..., description="Angle/format, e.g., tutorial, listicle, case-study")
    platform: str = Field(..., description="youtube or shorts")
    region: Optional[str] = Field(None, description="Region or timezone string like GMT+7")

    # Generated fields
    seo_title: str
    hook: str
    angle: str
    cta: str
    description: str
    hashtags: List[str]
    post_time: str

    # Scoring
    score: int
    criteria: Dict[str, Any]
