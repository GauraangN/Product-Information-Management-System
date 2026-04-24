from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Product
from app.schemas import SeasonalSearchQuery, CustomerContext, SeasonalAttributes
from sentence_transformers import SentenceTransformer
import numpy as np
from datetime import datetime
from groq import Groq
import os
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/seasonal", tags=["seasonal"])
model = SentenceTransformer("all-MiniLM-L6-v2")
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def cosine_similarity(a, b):
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

def get_customer_season(location: str = None) -> str:
    """Determine current season based on location and date"""
    now = datetime.now()
    month = now.month
    
    # Northern Hemisphere seasons
    if location and any(country in location.lower() for country in ['australia', 'brazil', 'argentina']):
        # Southern Hemisphere
        if month in [12, 1, 2]:
            return "summer"
        elif month in [3, 4, 5]:
            return "autumn"
        elif month in [6, 7, 8]:
            return "winter"
        else:
            return "spring"
    else:
        # Northern Hemisphere
        if month in [12, 1, 2]:
            return "winter"
        elif month in [3, 4, 5]:
            return "spring"
        elif month in [6, 7, 8]:
            return "summer"
        else:
            return "autumn"

def calculate_seasonal_relevance(product_attributes: dict, context: CustomerContext) -> float:
    """Calculate how relevant a product is for current season/weather"""
    if not product_attributes:
        return 0.0
    
    score = 0.0
    current_season = context.season or get_customer_season(context.location)
    
    # Check seasonality
    seasonality = product_attributes.get('seasonality', [])
    if current_season in seasonality:
        score += 0.4
    
    # Check weather conditions
    weather_conditions = product_attributes.get('weather_conditions', [])
    if context.temperature:
        if context.temperature > 25 and 'warm' in weather_conditions:
            score += 0.3
        elif context.temperature < 15 and 'cold' in weather_conditions:
            score += 0.3
    
    # Check thickness
    thickness = product_attributes.get('thickness_rating', 5)
    if context.temperature and context.temperature > 25:
        if thickness <= 3:  # Lightweight
            score += 0.3
    elif context.temperature and context.temperature < 15:
        if thickness >= 7:  # Heavy
            score += 0.3
    
    return min(score, 1.0)

@router.post("/search")
def seasonal_search(payload: SeasonalSearchQuery, db: Session = Depends(get_db)):
    """Enhanced search with seasonal filtering"""
    
    # Get customer context
    context = payload.customer_context or CustomerContext()
    if not context.season:
        context.season = get_customer_season(context.location)
    
    # Generate query embedding
    query_embedding = model.encode(payload.query).tolist()
    
    # Get all products with embeddings
    products = db.query(Product).filter(Product.embedding != None).all()
    
    if not products:
        # Fallback to keyword search
        keyword = payload.query.lower()
        results = db.query(Product).filter(
            Product.name.ilike(f"%{keyword}%") |
            Product.description.ilike(f"%{keyword}%") |
            Product.category.ilike(f"%{keyword}%")
        ).limit(payload.top_k).all()
        
        return {
            "query": payload.query,
            "method": "keyword_fallback",
            "season": context.season,
            "results": [
                {
                    "id": p.id, 
                    "name": p.name, 
                    "category": p.category,
                    "description": p.description, 
                    "price": p.price,
                    "seasonal_relevance": 0.5
                }
                for p in results
            ]
        }
    
    # Score products by semantic similarity + seasonal relevance
    scored = []
    for product in products:
        semantic_score = cosine_similarity(query_embedding, product.embedding)
        seasonal_score = calculate_seasonal_relevance(product.attributes or {}, context)
        
        # Weighted combination (60% semantic, 40% seasonal)
        final_score = (semantic_score * 0.6) + (seasonal_score * 0.4)
        
        scored.append((final_score, product, seasonal_score))
    
    # Sort by final score and return top results
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:payload.top_k]
    
    return {
        "query": payload.query,
        "method": "seasonal_semantic",
        "season": context.season,
        "results": [
            {
                "id": p.id,
                "name": p.name,
                "category": p.category,
                "description": p.description,
                "price": p.price,
                "semantic_score": round(semantic_score, 4),
                "seasonal_score": round(seasonal_score, 4),
                "final_score": round(final_score, 4)
            }
            for final_score, p, seasonal_score in top
        ]
    }

@router.post("/classify/{product_id}")
def classify_product_seasonal(product_id: int, db: Session = Depends(get_db)):
    """Use AI to classify product seasonal attributes"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    prompt = f"""Analyze this product and classify its seasonal attributes. Return ONLY a valid JSON object.

Product Name: {product.name}
Category: {product.category or 'Unknown'}
Description: {product.description or ''}
Current Attributes: {product.attributes or {}}

Return this exact JSON structure:
{{
  "seasonality": ["summer", "spring", "autumn", "winter"],
  "temperature_range": "15-25°C",
  "weather_conditions": ["sunny", "mild", "cold"],
  "thickness_rating": 5,
  "layering_type": "light"
}}

Rules:
- seasonality: array of suitable seasons
- temperature_range: ideal temperature range in °C
- weather_conditions: suitable weather conditions
- thickness_rating: 1-10 scale (1=very light, 10=very heavy)
- layering_type: "light", "medium", or "heavy"
"""
    
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300
    )
    
    raw = response.choices[0].message.content.strip()
    
    try:
        import json
        seasonal_attrs = json.loads(raw)
    except json.JSONDecodeError:
        import re
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            seasonal_attrs = json.loads(match.group())
        else:
            raise HTTPException(status_code=500, detail=f"Could not parse seasonal attributes: {raw}")
    
    # Update product attributes with seasonal data
    if product.attributes:
        product.attributes.update(seasonal_attrs)
    else:
        product.attributes = seasonal_attrs
    
    db.commit()
    
    return {
        "product_id": product_id,
        "seasonal_attributes": seasonal_attrs
    }

@router.post("/classify-all")
def classify_all_products(db: Session = Depends(get_db)):
    """Classify all products without seasonal attributes"""
    products = db.query(Product).all()
    results = []
    
    for product in products:
        if not product.attributes or 'seasonality' not in product.attributes:
            try:
                # Call classification for each product
                result = classify_product_seasonal(product.id, db)
                results.append({
                    "product_id": product.id,
                    "name": product.name,
                    "status": "classified",
                    "seasonality": result["seasonal_attributes"].get("seasonality", [])
                })
            except Exception as e:
                results.append({
                    "product_id": product.id,
                    "name": product.name,
                    "status": "failed",
                    "error": str(e)
                })
        else:
            results.append({
                "product_id": product.id,
                "name": product.name,
                "status": "already_classified"
            })
    
    return {"total": len(products), "results": results}

@router.get("/context")
def get_seasonal_context(location: str = None, ip_address: str = None):
    """Get current seasonal context for a location"""
    season = get_customer_season(location)
    
    return {
        "location": location,
        "season": season,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "recommended_filters": {
            "summer": ["lightweight", "breathable", "cotton", "shorts", "t-shirts"],
            "winter": ["heavy", "warm", "wool", "sweaters", "jackets"],
            "spring": ["medium", "light", "layers", "cardigans"],
            "autumn": ["medium", "warm", "long sleeves", "hoodies"]
        }.get(season, [])
    }
