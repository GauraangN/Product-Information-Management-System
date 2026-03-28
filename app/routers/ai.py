from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session
from groq import Groq
from app.database import get_db
from app.models import Product
import os, json, base64
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/ai", tags=["ai"])
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ── Description generation ──────────────────────────────────────────────────

@router.post("/generate-description/{product_id}")
def generate_description(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    prompt = f"""Write a compelling, professional e-commerce product description for:
Product Name: {product.name}
Category: {product.category or 'General'}
Attributes: {json.dumps(product.attributes or {})}
Raw Info: {product.raw_input or ''}

Write 2-3 sentences. Be specific, persuasive, and highlight key features."""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300
    )

    description = response.choices[0].message.content.strip()
    product.description = description
    db.commit()
    db.refresh(product)

    return {"product_id": product_id, "description": description}


# ── Attribute extraction from raw text ─────────────────────────────────────

@router.post("/extract-attributes/{product_id}")
def extract_attributes(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if not product.raw_input:
        raise HTTPException(status_code=400, detail="No raw input text found for this product")

    prompt = f"""Extract structured product attributes from this text and return ONLY a valid JSON object.
No explanation, no markdown, just the JSON.

Text: {product.raw_input}

Example output format:
{{"color": "red", "weight": "2kg", "material": "cotton", "size": "XL"}}"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300
    )

    raw = response.choices[0].message.content.strip()

    try:
        attributes = json.loads(raw)
    except json.JSONDecodeError:
        # fallback: try to extract JSON from response
        import re
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            attributes = json.loads(match.group())
        else:
            raise HTTPException(status_code=500, detail=f"Could not parse attributes: {raw}")

    product.attributes = attributes
    db.commit()
    db.refresh(product)

    return {"product_id": product_id, "attributes": attributes}


# ── Attribute extraction from image ────────────────────────────────────────

@router.post("/extract-from-image/{product_id}")
async def extract_from_image(
    product_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    image_data = await file.read()
    base64_image = base64.b64encode(image_data).decode("utf-8")
    mime_type = file.content_type or "image/jpeg"

    response = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{base64_image}"
                    }
                },
                {
                    "type": "text",
                    "text": """Look at this product image and extract attributes.
Return ONLY a valid JSON object with attributes like color, shape, material, size, style etc.
No explanation, just JSON. Example: {"color": "blue", "material": "plastic", "shape": "cylindrical"}"""
                }
            ]
        }],
        max_tokens=300
    )

    raw = response.choices[0].message.content.strip()

    try:
        attributes = json.loads(raw)
    except json.JSONDecodeError:
        import re
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        attributes = json.loads(match.group()) if match else {"raw_response": raw}

    if product.attributes:
        product.attributes.update(attributes)
    else:
        product.attributes = attributes

    db.commit()
    db.refresh(product)

    return {"product_id": product_id, "attributes_from_image": attributes}