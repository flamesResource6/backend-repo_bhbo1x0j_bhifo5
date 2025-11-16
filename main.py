import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from bson import ObjectId
from datetime import datetime
from database import db, create_document, get_documents
from schemas import User, Item, Offer, Rating
import hashlib

app = FastAPI(title="Campus Marketplace API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Helpers

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def obj_id(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")


# Auth models
class SignupPayload(BaseModel):
    name: str
    email: EmailStr
    password: str
    campus: Optional[str] = None

class LoginPayload(BaseModel):
    email: EmailStr
    password: str

class AuthResponse(BaseModel):
    user_id: str
    name: str
    email: EmailStr
    campus: Optional[str] = None


@app.get("/")
def root():
    return {"message": "Campus Marketplace Backend Running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response


# Auth routes
@app.post("/auth/signup", response_model=AuthResponse)
def signup(payload: SignupPayload):
    # Check if user exists
    existing = db["user"].find_one({"email": payload.email}) if db else None
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        campus=payload.campus,
    )
    user_id = create_document("user", user)
    return AuthResponse(user_id=user_id, name=user.name, email=user.email, campus=user.campus)


@app.post("/auth/login", response_model=AuthResponse)
def login(payload: LoginPayload):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    u = db["user"].find_one({"email": payload.email})
    if not u or u.get("password_hash") != hash_password(payload.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return AuthResponse(user_id=str(u["_id"]), name=u.get("name"), email=u.get("email"), campus=u.get("campus"))


# Profiles
class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    campus: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None

@app.get("/users/{user_id}")
def get_profile(user_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    u = db["user"].find_one({"_id": obj_id(user_id)})
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    u["_id"] = str(u["_id"]) 
    u.pop("password_hash", None)
    return u

@app.patch("/users/{user_id}")
def update_profile(user_id: str, payload: ProfileUpdate):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    update = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update:
        return {"updated": False}
    update["updated_at"] = datetime.utcnow()
    res = db["user"].update_one({"_id": obj_id(user_id)}, {"$set": update})
    return {"updated": res.modified_count == 1}


# Items
class ItemCreate(BaseModel):
    title: str
    description: Optional[str] = None
    category: str
    condition: str
    price: float
    images: Optional[List[str]] = []
    seller_id: str
    campus: Optional[str] = None
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None

@app.post("/items")
def create_item(payload: ItemCreate):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    item = Item(**payload.model_dump())
    item_id = create_document("item", item)
    return {"item_id": item_id}


class ItemQuery(BaseModel):
    q: Optional[str] = None
    campus: Optional[str] = None
    category: Optional[str] = None
    max_distance_km: Optional[float] = None
    seller_id: Optional[str] = None

@app.post("/items/search")
def search_items(filters: ItemQuery):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    query = {"is_active": True}
    if filters.category:
        query["category"] = filters.category
    if filters.campus:
        query["campus"] = filters.campus
    if filters.seller_id:
        query["seller_id"] = filters.seller_id
    # Basic text search
    if filters.q:
        query["$or"] = [
            {"title": {"$regex": filters.q, "$options": "i"}},
            {"description": {"$regex": filters.q, "$options": "i"}},
        ]
    items = list(db["item"].find(query).sort("created_at", -1).limit(100))
    for it in items:
        it["_id"] = str(it["_id"]) 
    return items


# Offers/Negotiation
class OfferCreate(BaseModel):
    item_id: str
    buyer_id: str
    offered_price: float
    message: Optional[str] = None

@app.post("/offers")
def create_offer(payload: OfferCreate):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    # fetch item to know seller
    item = db["item"].find_one({"_id": obj_id(payload.item_id)})
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    offer = Offer(
        item_id=payload.item_id,
        buyer_id=payload.buyer_id,
        seller_id=str(item["seller_id"]) if isinstance(item.get("seller_id"), ObjectId) else item.get("seller_id"),
        offered_price=payload.offered_price,
        message=payload.message,
        status="pending"
    )
    offer_id = create_document("offer", offer)
    return {"offer_id": offer_id}

class OfferAction(BaseModel):
    action: str  # accept | decline | withdraw

@app.post("/offers/{offer_id}/action")
def update_offer(offer_id: str, payload: OfferAction):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    valid = {"accept": "accepted", "decline": "declined", "withdraw": "withdrawn"}
    if payload.action not in valid:
        raise HTTPException(status_code=400, detail="Invalid action")
    res = db["offer"].update_one({"_id": obj_id(offer_id)}, {"$set": {"status": valid[payload.action], "updated_at": datetime.utcnow()}})
    return {"updated": res.modified_count == 1}

@app.get("/offers/for-user/{user_id}")
def list_offers_for_user(user_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    offers = list(db["offer"].find({"$or": [{"seller_id": user_id}, {"buyer_id": user_id}]}).sort("created_at", -1))
    for o in offers:
        o["_id"] = str(o["_id"]) 
    return offers


# Ratings
class RatingCreate(BaseModel):
    rater_id: str
    ratee_id: str
    item_id: str
    stars: int
    comment: Optional[str] = None

@app.post("/ratings")
def create_rating(payload: RatingCreate):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    rating = Rating(**payload.model_dump())
    rating_id = create_document("rating", rating)
    # update ratee aggregates
    agg = list(db["rating"].aggregate([
        {"$match": {"ratee_id": payload.ratee_id}},
        {"$group": {"_id": "$ratee_id", "avg": {"$avg": "$stars"}, "count": {"$sum": 1}}}
    ]))
    if agg:
        avg = agg[0]["avg"]
        count = agg[0]["count"]
        db["user"].update_one({"_id": obj_id(payload.ratee_id)}, {"$set": {"rating_avg": avg, "rating_count": count}})
    return {"rating_id": rating_id}


# Nearby sellers/buyers - simple campus or naive geo filter
@app.get("/nearby/users")
def nearby_users(campus: Optional[str] = None, lat: Optional[float] = None, lng: Optional[float] = None):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    query = {"is_active": True}
    if campus:
        query["campus"] = campus
    users = list(db["user"].find(query).limit(100))
    for u in users:
        u["_id"] = str(u["_id"]) 
        u.pop("password_hash", None)
    return users


@app.get("/nearby/items")
def nearby_items(campus: Optional[str] = None, category: Optional[str] = None):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    query = {"is_active": True}
    if campus:
        query["campus"] = campus
    if category:
        query["category"] = category
    items = list(db["item"].find(query).sort("created_at", -1).limit(100))
    for it in items:
        it["_id"] = str(it["_id"]) 
    return items


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
