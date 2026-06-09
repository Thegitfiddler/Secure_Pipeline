"""Unit tests for the Secure Pipeline API."""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert "environment" in data


def test_echo_valid():
    response = client.post("/echo", json={"message": "hello world"})
    assert response.status_code == 200
    assert response.json()["echo"] == "hello world"


def test_echo_empty_message():
    response = client.post("/echo", json={"message": "   "})
    assert response.status_code == 400


def test_echo_missing_field():
    response = client.post("/echo", json={})
    assert response.status_code == 422