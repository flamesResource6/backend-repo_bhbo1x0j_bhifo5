"""
Database Schemas for Campus Marketplace

Each Pydantic model represents a MongoDB collection (collection name is the
lowercased class name).
"""
from typing import Optional, List
from pydantic import BaseModel, Field, EmailStr

class User(BaseModel):
    name: str = Field(..., description="Full name")
    email: EmailStr = Field(..., description="Email address")
    password_hash: str = Field(..., description="Hashed password")
    campus: Optional[str] = Field(None, description="Campus/College name")
    avatar_url: Optional[str] = Field(None, description="Profile image URL")
    bio: Optional[str] = Field(None, description="Short bio")
    location_lat: Optional[float] = Field(None, ge=-90, le=90)
    location_lng: Optional[float] = Field(None, ge=-180, le=180)
    rating_avg: float = Field(0.0, ge=0, le=5)
    rating_count: int = Field(0, ge=0)
    is_active: bool = Field(True)

class Item(BaseModel):
    title: str
    description: Optional[str] = None
    category: str = Field(..., description="Category like books, electronics, medical instruments, etc.")
    condition: str = Field(..., description="Condition e.g., New, Like New, Good, Fair")
    price: float = Field(..., ge=0)
    images: List[str] = Field(default_factory=list)
    seller_id: str = Field(..., description="Owner user id (stringified ObjectId)")
    campus: Optional[str] = None
    location_lat: Optional[float] = Field(None, ge=-90, le=90)
    location_lng: Optional[float] = Field(None, ge=-180, le=180)
    is_active: bool = Field(True)

class Offer(BaseModel):
    item_id: str
    buyer_id: str
    seller_id: str
    offered_price: float = Field(..., ge=0)
    message: Optional[str] = None
    status: str = Field("pending", description="pending|accepted|declined|withdrawn")

class Rating(BaseModel):
    rater_id: str
    ratee_id: str
    item_id: str
    stars: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None
