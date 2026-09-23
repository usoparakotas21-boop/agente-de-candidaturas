from fastapi import FastAPI
from .queue_routes import router as queue_router

app = FastAPI()
app.include_router(queue_router)

@app.get("/")
def root():
    return {"status": "ok"}