import os
import io
import pytest
from fastapi.testclient import TestClient
from api import app

client = TestClient(app)

SAMPLE_LOG = """INFO Start process\nERROR Something bad happened\nWARN Minor issue\nINFO Done\n""".encode("utf-8")


def test_upload_and_health():
    files = {"files": ("sample.log", io.BytesIO(SAMPLE_LOG), "text/plain")}
    r = client.post("/upload", files=files)
    assert r.status_code == 200
    data = r.json()
    assert "errors" in data and len(data["errors"]) >= 1
    health = client.get("/health").json()
    assert health["vector_initialized"] is True
    assert health["retriever_ready"] is True


def test_context_and_optional_resolve():
    # Assume at least one error exists from prior test
    errs = client.get("/errors").json()["errors"]
    assert errs, "No errors after upload"
    first_id = errs[0]["id"]
    ctx = client.get(f"/context?id={first_id}")
    assert ctx.status_code == 200
    # Only run resolve if key present
    if os.getenv("OPENAI_API_KEY"):
        res = client.post("/resolve", json={"id": first_id})
        assert res.status_code == 200
        body = res.json()
        assert "answer" in body and body["answer"]["text"]
    else:
        pytest.skip("OPENAI_API_KEY not set; skipping resolve")
