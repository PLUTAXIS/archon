from fastapi import FastAPI

app = FastAPI(
    title="ARCHON API",
    description="Deterministic spreadsheet audit engine",
    version="0.1.0",
)

@app.get("/")
def root():
    return {
        "status": "ok",
        "service": "archon-api",
    }

@app.get("/health")
def health():
    return {
        "status": "healthy",
    }
