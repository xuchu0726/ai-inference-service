from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from app.multimodal.service import router

app = FastAPI(
    title="BAGEL Multimodal Inference Service",
    version="0.1.0",
)

Instrumentator().instrument(app).expose(app)
app.include_router(router)
