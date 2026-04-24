from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Product
from app.schemas import SeasonalSearchQuery, CustomerContext
from sentence_transformers import SentenceTransformer
import numpy as np
from datetime import datetime

router = APIRouter(prefix="/customer", tags=["customer"])
model = SentenceTransformer("all-MiniLM-L6-v2")

def cosine_similarity(a, b):
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

def get_customer_season(location: str = None) -> str:
    """Determine current season based on location and date"""
    now = datetime.now()
    month = now.month
    
    # Northern Hemisphere seasons (default)
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

def calculate_seasonal_relevance(product_attributes: dict, season: str) -> float:
    """Calculate seasonal relevance score"""
    if not product_attributes:
        return 0.5  # Neutral score
    
    score = 0.5  # Base score
    
    # Check seasonality
    seasonality = product_attributes.get('seasonality', [])
    if season in seasonality:
        score += 0.4
    
    # Check weather conditions
    weather_conditions = product_attributes.get('weather_conditions', [])
    if season == 'summer' and any(cond in weather_conditions for cond in ['warm', 'sunny']):
        score += 0.1
    elif season == 'winter' and any(cond in weather_conditions for cond in ['cold', 'windy']):
        score += 0.1
    
    return min(score, 1.0)

@router.get("/products")
def get_seasonal_products(
    category: str = Query(None, description="Filter by category"),
    season: str = Query(None, description="Filter by season"),
    location: str = Query(None, description="Customer location"),
    limit: int = Query(20, description="Number of products to return"),
    min_price: float = Query(None, description="Minimum price"),
    max_price: float = Query(None, description="Maximum price"),
    db: Session = Depends(get_db)
):
    """
    Customer-facing endpoint for WooCommerce to get seasonal products
    """
    
    # Determine season if not provided
    if not season:
        season = get_customer_season(location)
    
    # Build base query
    query = db.query(Product).filter(Product.woo_product_id.isnot(None))
    
    # Apply filters
    if category:
        query = query.filter(Product.category.ilike(f"%{category}%"))
    
    if min_price is not None:
        query = query.filter(Product.price >= min_price)
    
    if max_price is not None:
        query = query.filter(Product.price <= max_price)
    
    # Get products
    products = query.all()
    
    # Score by seasonal relevance
    scored_products = []
    for product in products:
        seasonal_score = calculate_seasonal_relevance(
            product.attributes or {}, season
        )
        scored_products.append((seasonal_score, product))
    
    # Sort by seasonal relevance and limit
    scored_products.sort(key=lambda x: x[0], reverse=True)
    top_products = scored_products[:limit]
    
    # Format for WooCommerce
    result = {
        "season": season,
        "location": location,
        "total_products": len(products),
        "returned_products": len(top_products),
        "products": []
    }
    
    for score, product in top_products:
        result["products"].append({
            "id": product.woo_product_id,  # WooCommerce product ID
            "name": product.name,
            "description": product.description,
            "price": product.price,
            "category": product.category,
            "sku": product.sku,
            "attributes": product.attributes,
            "seasonal_relevance": round(score, 3),
            "image_url": None  # Could be added to schema
        })
    
    return result

@router.get("/products/search")
def search_products(
    q: str = Query(..., description="Search query"),
    location: str = Query(None, description="Customer location"),
    season: str = Query(None, description="Season filter"),
    limit: int = Query(10, description="Number of results"),
    db: Session = Depends(get_db)
):
    """
    Semantic search with seasonal filtering for WooCommerce
    """
    
    # Determine season
    if not season:
        season = get_customer_season(location)
    
    # Generate query embedding
    query_embedding = model.encode(q).tolist()
    
    # Get products with embeddings
    products = db.query(Product).filter(
        Product.embedding.isnot(None),
        Product.woo_product_id.isnot(None)
    ).all()
    
    if not products:
        return {"query": q, "season": season, "results": []}
    
    # Score products
    scored = []
    for product in products:
        semantic_score = cosine_similarity(query_embedding, product.embedding)
        seasonal_score = calculate_seasonal_relevance(
            product.attributes or {}, season
        )
        
        # Weighted combination
        final_score = (semantic_score * 0.7) + (seasonal_score * 0.3)
        scored.append((final_score, product))
    
    # Sort and limit
    scored.sort(key=lambda x: x[0], reverse=True)
    top_results = scored[:limit]
    
    return {
        "query": q,
        "season": season,
        "location": location,
        "results": [
            {
                "woo_product_id": product.woo_product_id,
                "name": product.name,
                "price": product.price,
                "category": product.category,
                "description": product.description[:200] + "..." if product.description else "",
                "relevance_score": round(score, 3)
            }
            for score, product in top_results
        ]
    }

@router.get("/products/{woo_product_id}")
def get_product_details(woo_product_id: int, db: Session = Depends(get_db)):
    """
    Get detailed product information for WooCommerce product page
    """
    
    product = db.query(Product).filter(
        Product.woo_product_id == woo_product_id
    ).first()
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    return {
        "woo_product_id": product.woo_product_id,
        "name": product.name,
        "description": product.description,
        "price": product.price,
        "category": product.category,
        "sku": product.sku,
        "attributes": product.attributes,
        "seasonal_info": {
            "seasonality": product.attributes.get('seasonality', []) if product.attributes else [],
            "temperature_range": product.attributes.get('temperature_range', '') if product.attributes else '',
            "weather_conditions": product.attributes.get('weather_conditions', []) if product.attributes else [],
            "thickness_rating": product.attributes.get('thickness_rating', 5) if product.attributes else 5
        }
    }

@router.get("/categories")
def get_seasonal_categories(
    season: str = Query(None, description="Filter categories by season"),
    location: str = Query(None, description="Customer location"),
    db: Session = Depends(get_db)
):
    """
    Get categories with seasonal relevance for WooCommerce navigation
    """
    
    if not season:
        season = get_customer_season(location)
    
    # Get all unique categories
    categories = db.query(Product.category).filter(
        Product.category.isnot(None),
        Product.woo_product_id.isnot(None)
    ).distinct().all()
    
    # Score categories by seasonal relevance
    scored_categories = []
    for (category_name,) in categories:
        # Get products in this category
        category_products = db.query(Product).filter(
            Product.category == category_name,
            Product.attributes.isnot(None)
        ).all()
        
        if category_products:
            # Calculate average seasonal relevance
            total_score = sum(
                calculate_seasonal_relevance(p.attributes or {}, season)
                for p in category_products
            )
            avg_score = total_score / len(category_products)
            
            scored_categories.append((avg_score, category_name[0], len(category_products)))
    
    # Sort by seasonal relevance
    scored_categories.sort(key=lambda x: x[0], reverse=True)
    
    return {
        "season": season,
        "categories": [
            {
                "name": name,
                "product_count": count,
                "seasonal_relevance": round(score, 3)
            }
            for score, name, count in scored_categories
        ]
    }

@router.get("/seasonal-context")
def get_seasonal_context(location: str = Query(None)):
    """
    Get current seasonal context for customer
    """
    
    season = get_customer_season(location)
    
    seasonal_recommendations = {
        "summer": {
            "featured_categories": ["t-shirts", "shorts", "swimwear", "sandals"],
            "attributes": ["lightweight", "breathable", "cotton", "linen"],
            "colors": ["white", "light blue", "pastel"]
        },
        "winter": {
            "featured_categories": ["sweaters", "jackets", "boots", "thermal"],
            "attributes": ["warm", "insulated", "wool", "fleece"],
            "colors": ["dark", "burgundy", "forest green"]
        },
        "spring": {
            "featured_categories": ["light jackets", "cardigans", "sneakers"],
            "attributes": ["lightweight", "layering", "versatile"],
            "colors": ["pastel", "light colors"]
        },
        "autumn": {
            "featured_categories": ["hoodies", "long sleeves", "boots"],
            "attributes": ["medium weight", "layering", "warm"],
            "colors": ["earth tones", "orange", "brown"]
        }
    }
    
    return {
        "season": season,
        "location": location,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "recommendations": seasonal_recommendations.get(season, {})
    }
