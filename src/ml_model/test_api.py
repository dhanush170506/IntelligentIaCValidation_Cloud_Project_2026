"""Minimal test for the ML assurance HTTP API (POST /validate).

Run from the project root:
    python -m pytest src/ml_model/test_api.py -v
"""
from __future__ import annotations

import re

from fastapi.testclient import TestClient

from src.ml_model.api import app

client = TestClient(app)

TERRAFORM_EXAMPLE = """
resource "aws_s3_bucket" "example" {
  bucket = "my-test-bucket"
}

resource "aws_s3_bucket_public_access_block" "example" {
  bucket = aws_s3_bucket.example.id
  block_public_acls = true
}
"""

OBJECT_REPR_PATTERN = re.compile(r"<[A-Za-z_][\w.]* object at 0x[0-9a-fA-F]+>")


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "ml-assurance"


def test_validate_terraform():
    response = client.post(
        "/validate",
        json={
            "upload_id": "test-upload-1",
            "filename": "main.tf",
            "file_type": "terraform",
            "content": TERRAFORM_EXAMPLE,
        },
    )
    assert response.status_code == 200
    body = response.json()

    # Backend contract fields
    assert "status" in body
    assert "security_score" in body
    assert "drift_score" in body
    assert "confidence" in body
    assert isinstance(body["findings"], list)
    assert isinstance(body["recommendations"], list)

    # Rich ML output
    assert "assurance_report" in body

    # No Python object-address strings anywhere in the serialized JSON
    raw = response.text
    assert not OBJECT_REPR_PATTERN.search(raw), "object repr leaked into response"


def test_validate_unsupported_extension():
    response = client.post(
        "/validate",
        json={
            "upload_id": "test-upload-2",
            "filename": "notes.txt",
            "content": "hello",
        },
    )
    assert response.status_code == 400


def test_validate_missing_content():
    response = client.post(
        "/validate",
        json={
            "upload_id": "test-upload-3",
            "filename": "main.tf",
            "content": "",
        },
    )
    # Pydantic rejects empty/whitespace content with 422
    assert response.status_code == 422
