from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.database import Base, engine
from app.routers import products, ai, search, sync

logger = logging.getLogger(__name__)
ROOT_DIR = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        logger.warning("Database unavailable; tables not created: %s", e)
    yield


app = FastAPI(
    title="AI-Powered PIM System",
    description="Smart Product Information Management with local AI",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(products.router)
app.include_router(ai.router)
app.include_router(search.router)
app.include_router(sync.router)


@app.get("/health")
def health():
    return {"status": "ok", "message": "PIM system running"}


@app.get("/")
def serve_index():
    index_path = ROOT_DIR / "index.html"
    if not index_path.is_file():
        raise HTTPException(status_code=404, detail="index.html not found in project root")
    return FileResponse(index_path)
