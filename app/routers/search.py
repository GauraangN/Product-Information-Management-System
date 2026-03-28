from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Product
from app.schemas import SearchQuery
from sentence_transformers import SentenceTransformer
import numpy as np

router = APIRouter(prefix="/search", tags=["search"])

# Load model once at startup
model = SentenceTransformer("all-MiniLM-L6-v2")

def cosine_similarity(a, b):
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

@router.post("/")
def natural_language_search(payload: SearchQuery, db: Session = Depends(get_db)):
    # Embed the search query
    query_embedding = model.encode(payload.query).tolist()

    # Get all products that have embeddings
    products = db.query(Product).filter(Product.embedding != None).all()

    if not products:
        # Fallback: return keyword match if no embeddings exist yet
        keyword = payload.query.lower()
        results = db.query(Product).filter(
            Product.name.ilike(f"%{keyword}%") |
            Product.description.ilike(f"%{keyword}%") |
            Product.category.ilike(f"%{keyword}%")
        ).limit(payload.top_k).all()
        return {
            "query": payload.query,
            "method": "keyword_fallback",
            "results": [
                {"id": p.id, "name": p.name, "category": p.category,
                 "description": p.description, "price": p.price}
                for p in results
            ]
        }

    # Score all products by cosine similarity
    scored = []
    for product in products:
        score = cosine_similarity(query_embedding, product.embedding)
        scored.append((score, product))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:payload.top_k]

    return {
        "query": payload.query,
        "method": "semantic",
        "results": [
            {
                "id": p.id,
                "name": p.name,
                "category": p.category,
                "description": p.description,
                "price": p.price,
                "score": round(score, 4)
            }
            for score, p in top
        ]
    }

@router.post("/embed/{product_id}")
def embed_product(product_id: int, db: Session = Depends(get_db)):
    """Generate and store embedding for a product"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Build text to embed from product fields
    text = f"{product.name} {product.category or ''} {product.description or ''} {str(product.attributes or '')}"
    embedding = model.encode(text).tolist()

    product.embedding = embedding
    db.commit()

    return {"product_id": product_id, "message": "Embedding stored successfully"}

@router.post("/embed-all")
def embed_all_products(db: Session = Depends(get_db)):
    """Embed all products that don't have embeddings yet"""
    products = db.query(Product).filter(Product.embedding == None).all()
    count = 0
    for product in products:
        text = f"{product.name} {product.category or ''} {product.description or ''} {str(product.attributes or '')}"
        product.embedding = model.encode(text).tolist()
        count += 1
    db.commit()
    return {"message": f"Embedded {count} products"}