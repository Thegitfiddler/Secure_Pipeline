"""
Secure Pipeline — FastAPI Application
A minimal REST API demonstrating security-focused CI/CD practices.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os

app = FastAPI(
    title="Secure Pipeline Demo",
    description="A minimal API demonstrating security-focused CI/CD with GitHub Actions and AWS ECR.",
    version="1.0.0",
)


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str


class EchoRequest(BaseModel):
    message: str


class EchoResponse(BaseModel):
    echo: str


@app.get("/", response_model=HealthResponse)
def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        environment=os.getenv("APP_ENV", "production"),
    )


@app.post("/echo", response_model=EchoResponse)
def echo(request: EchoRequest):
    """Echo the provided message back to the caller."""
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    return EchoResponse(echo=request.message)