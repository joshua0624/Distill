import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.feed import router as feed_router
from backend.api.items import router as items_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = FastAPI(title="Distill", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:4173",  # Vite preview
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(feed_router, prefix="/api")
app.include_router(items_router, prefix="/api/items")


@app.get("/health")
def health():
    return {"status": "ok"}
