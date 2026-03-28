from datetime import datetime

import httpx
import os
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Product

load_dotenv()

router = APIRouter(prefix="/sync", tags=["sync"])

WC_BASE_URL = (os.getenv("WC_BASE_URL") or "").rstrip("/")
WC_CONSUMER_KEY = os.getenv("WC_CONSUMER_KEY") or ""
WC_CONSUMER_SECRET = os.getenv("WC_CONSUMER_SECRET") or ""


def _require_wc_config():
    if not WC_BASE_URL or not WC_CONSUMER_KEY or not WC_CONSUMER_SECRET:
        raise HTTPException(
            status_code=503,
            detail="WooCommerce is not configured. Set WC_BASE_URL, WC_CONSUMER_KEY, and WC_CONSUMER_SECRET in .env",
        )


def _woo_payload(product: Product) -> dict:
    price = product.price
    price_str = f"{float(price):.2f}" if price is not None else "0.00"
    return {
        "name": product.name,
        "description": product.description or "",
        "sku": product.sku,
        "regular_price": price_str,
        "categories": [{"name": product.category}] if product.category else [],
        "attributes": [
            {
                "name": str(k),
                "options": [str(i) for i in (v if isinstance(v, list) else [v])],
                "visible": True,
            }
            for k, v in (product.attributes or {}).items()
        ],
    }


async def _push_product(client: httpx.AsyncClient, product: Product) -> tuple[int, dict]:
    """Create or update in WooCommerce. Returns (status_code, response_json_or_none)."""
    payload = _woo_payload(product)
    auth = (WC_CONSUMER_KEY, WC_CONSUMER_SECRET)
    base = f"{WC_BASE_URL}/wp-json/wc/v3/products"

    if product.woo_product_id:
        r = await client.put(
            f"{base}/{product.woo_product_id}",
            json=payload,
            auth=auth,
            timeout=30.0,
        )
    else:
        r = await client.post(base, json=payload, auth=auth, timeout=30.0)

    try:
        body = r.json() if r.content else {}
    except Exception:
        body = {"raw": r.text[:500] if r.text else ""}
    return r.status_code, body


# --- Static path segments MUST be registered before /{product_id} (int) ---


@router.post("/all")
async def sync_all_unsynced(db: Session = Depends(get_db)):
    """Sync products that are not yet linked to WooCommerce (no woo_product_id)."""
    _require_wc_config()
    products = (
        db.query(Product).filter(Product.woo_product_id.is_(None)).all()
    )
    if not products:
        return {"message": "No unsynced products", "total": 0, "results": []}

    results = []
    async with httpx.AsyncClient(verify=False) as client:
        for product in products:
            try:
                status, body = await _push_product(client, product)
                if status in (200, 201):
                    woo_id = body.get("id")
                    if woo_id:
                        product.woo_product_id = int(woo_id)
                        product.synced_at = datetime.utcnow()
                    results.append(
                        {
                            "product_id": product.id,
                            "woo_product_id": woo_id,
                            "status": "synced",
                        }
                    )
                else:
                    err = body.get("message") or body.get("code") or body
                    results.append(
                        {
                            "product_id": product.id,
                            "status": "failed",
                            "status_code": status,
                            "error": err,
                        }
                    )
            except Exception as e:
                results.append(
                    {"product_id": product.id, "status": "error", "error": str(e)}
                )

    db.commit()
    return {"total": len(products), "results": results}


@router.post("/bulk")
async def sync_all_products(db: Session = Depends(get_db)):
    """Push every product (creates new or updates existing by woo_product_id)."""
    _require_wc_config()
    products = db.query(Product).all()
    if not products:
        return {"message": "No products found", "total": 0, "results": []}

    results = []
    async with httpx.AsyncClient(verify=False) as client:
        for product in products:
            try:
                status, body = await _push_product(client, product)
                if status in (200, 201):
                    woo_id = body.get("id")
                    if woo_id:
                        product.woo_product_id = int(woo_id)
                        product.synced_at = datetime.utcnow()
                    results.append(
                        {
                            "product_id": product.id,
                            "woo_product_id": woo_id,
                            "status": "synced",
                        }
                    )
                else:
                    err = body.get("message") or body.get("code") or body
                    results.append(
                        {
                            "product_id": product.id,
                            "status": "failed",
                            "status_code": status,
                            "error": err,
                        }
                    )
            except Exception as e:
                results.append(
                    {"product_id": product.id, "status": "error", "error": str(e)}
                )

    db.commit()
    return {"total": len(products), "results": results}


@router.post("/{product_id}")
async def sync_product_to_woo(product_id: int, db: Session = Depends(get_db)):
    _require_wc_config()
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    try:
        async with httpx.AsyncClient(verify=False) as client:
            status, body = await _push_product(client, product)

        if status in (200, 201):
            woo_id = body.get("id")
            if woo_id:
                product.woo_product_id = int(woo_id)
                product.synced_at = datetime.utcnow()
                db.commit()
            return {
                "status": "synced",
                "woo_product_id": woo_id,
                "product_id": product.id,
            }

        err = body.get("message") or body.get("code") or body
        return {
            "status": "failed",
            "status_code": status,
            "error": err,
            "detail": body,
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}
