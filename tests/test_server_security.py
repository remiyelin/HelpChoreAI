"""Server security durable tests: static allowlist vs raw-socket traversal, POST 400s,
PUBLIC_MODE read-only enforcement. Local server on a free port; no network, no paid calls."""
import json, socket, sys, threading
from http.server import ThreadingHTTPServer
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import meta_api
import server


@pytest.fixture(scope="module")
def port():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.H)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield httpd.server_address[1]
    httpd.shutdown()


def raw(port, request: bytes) -> tuple[int, str]:
    with socket.create_connection(("127.0.0.1", port), timeout=10) as s:
        s.sendall(request)
        out = b""
        while True:
            chunk = s.recv(65536)
            if not chunk: break
            out += chunk
    head, _, body = out.partition(b"\r\n\r\n")
    return int(head.split()[1]), body.decode("utf-8", "replace")


def get(port, path):
    return raw(port, f"GET {path} HTTP/1.0\r\nHost: local\r\n\r\n".encode())


def post(port, path, payload: bytes):
    return raw(port, b"POST " + path.encode() + b" HTTP/1.0\r\nHost: local\r\nContent-Type: application/json\r\nContent-Length: "
               + str(len(payload)).encode() + b"\r\n\r\n" + payload)


@pytest.mark.parametrize("path", ["/../.env", "/../src/env.py", "/../../../proc/self/environ",
                                  "/..%2f.env", "/web/../.env", "/server.py", "/.env"])
def test_traversal_paths_404(port, path):
    code, body = get(port, path)
    assert code == 404 and "not found" in body


def test_allowlisted_static_ok(port):
    code, _ = get(port, "/app.js")
    assert code == 200
    code, _ = get(port, "/")
    assert code == 200


def test_malformed_post_is_400_not_dropped(port):
    code, body = post(port, "/api/review", b"{not json")
    assert code == 400 and "malformed" in body
    code, body = post(port, "/api/review", json.dumps({"patient": "P1"}).encode())
    assert code == 400 and "missing field" in body


@pytest.fixture()
def public(port, monkeypatch):
    monkeypatch.setenv("PUBLIC_MODE", "1")
    yield port
    monkeypatch.delenv("PUBLIC_MODE", raising=False)


def test_public_mode_write_endpoints_403(public):
    for path in ("/api/transcribe", "/api/review", "/api/signoff"):
        code, body = post(public, path, json.dumps({"audio_b64": "AAAA"}).encode())
        assert code == 403 and "PUBLIC_MODE" in body, path
    code, _ = get(public, "/app.js")
    assert code == 200
    code, body = get(public, "/api/meta")
    assert code == 200 and "CACHED DEMO" in body


def test_public_mode_cache_only_models(monkeypatch, tmp_path):
    monkeypatch.setenv("PUBLIC_MODE", "1")
    monkeypatch.setattr(meta_api, "CACHE", tmp_path)
    miss = meta_api.chat_cached("https://example.invalid/v1", "k", "m", [{"role": "user", "content": "unique-public-probe"}])
    assert miss["status"] == "CACHE_ONLY"
    msgs = [{"role": "user", "content": "seeded"}]
    (tmp_path / f"{meta_api._key('m', msgs)}.json").write_text(json.dumps({"status": "OK", "text": "cached"}))
    hit = meta_api.chat_cached("https://example.invalid/v1", "k", "m", msgs)
    assert hit["status"] == "OK" and hit["_cache"] == "hit" and hit["text"] == "cached"
