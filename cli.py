"""A tiny command-line client for the FastAPI server.

Run it with:

    uv run cli.py                 # against the default http://localhost:8000
    uv run cli.py --url http://localhost:8000

The server must already be running in another terminal — that's the whole point.
This script is a *separate process* that talks to the server over HTTP, exactly
like a real client would, instead of importing the app in-process. Start the
server first with either:

    docker compose up --build     # the container path
    uv run uvicorn app.main:app --reload   # the local path

What it does, in order:
  1. checks /health so we fail fast with a friendly message if nothing's there,
  2. calls /banner, which makes the server log ASCII art to *its* logs
     (watch the `docker compose` / uvicorn window to see it appear),
  3. walks the items API end to end — create, list, get, delete — printing each
     step so you can see the request/response cycle.

It's deliberately dependency-light: just `httpx` (a runtime dependency) and the
standard library. Heavily commented because this repo is a teaching boilerplate.
"""

import argparse
import sys

import httpx

# A local banner printed to *this* terminal, so the CLI is fun on its own. This
# is separate from the server-side art that /banner logs — see the difference by
# watching both windows at once.
LOCAL_BANNER = r"""
   ___ _    ___   ___ _ _         _
  / __| |  |_ _| / __| (_)___ _ _| |_
 | (__| |__ | | | (__| | / -_) ' \  _|
  \___|____|___| \___|_|_\___|_||_\__|

  talking to the FastAPI server over HTTP
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Tiny HTTP client for the FastAPI server.")
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Base URL of the running server (default: %(default)s).",
    )
    args = parser.parse_args()
    base_url = args.url.rstrip("/")

    print(LOCAL_BANNER)
    print(f"[*] target server: {base_url}\n")

    # One client for the whole session: it reuses the connection and applies the
    # base_url + timeout to every request below.
    with httpx.Client(base_url=base_url, timeout=5.0) as client:
        # 1) Liveness check. If this fails the server almost certainly isn't up,
        #    so we print a hint instead of a raw stack trace.
        try:
            health = client.get("/health")
            health.raise_for_status()
        except httpx.ConnectError:
            print(f"[!] could not reach {base_url} — is the server running?")
            print("    start it with:  docker compose up --build")
            print("              or:    uv run uvicorn app.main:app --reload")
            return 1
        print(f"[+] /health        -> {health.json()}")

        # 2) Ask the server to log its ASCII banner. The interesting output shows
        #    up in the SERVER's logs, not here — here we just confirm the call.
        ack = client.get("/banner")
        ack.raise_for_status()
        print(f"[+] /banner        -> {ack.json()}  (check the server logs for art!)")

        # 3) Exercise the items CRUD router the same way a real client would.
        print("\n--- items API walkthrough ---")

        created = client.post("/items", json={"name": "Widget", "price": 9.99})
        created.raise_for_status()
        item = created.json()
        item_id = item["id"]
        print(f"[+] POST   /items          -> created #{item_id}: {item}")

        listed = client.get("/items")
        listed.raise_for_status()
        print(f"[+] GET    /items          -> {len(listed.json())} item(s)")

        fetched = client.get(f"/items/{item_id}")
        fetched.raise_for_status()
        print(f"[+] GET    /items/{item_id}       -> {fetched.json()}")

        deleted = client.delete(f"/items/{item_id}")
        deleted.raise_for_status()
        print(f"[+] DELETE /items/{item_id}       -> {deleted.status_code} No Content")

        # Confirm it's really gone — the server should now answer 404.
        gone = client.get(f"/items/{item_id}")
        print(f"[+] GET    /items/{item_id}       -> {gone.status_code} (expected 404)")

    print("\n[done] all requests completed.")
    return 0


if __name__ == "__main__":
    # Propagate the exit code so shells/CI can tell success from failure.
    sys.exit(main())
