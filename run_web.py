#!/usr/bin/env python3
"""Serve the submitted, prebuilt RoadOps UI on this computer only (stdlib)."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import webbrowser


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent / "web"
    if not (root / "index.html").is_file():
        parser.error("Run the copy at the root of the extracted RoadOps package.")
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), partial(SimpleHTTPRequestHandler, directory=str(root)))
    except OSError as exc:
        parser.exit(1, f"Cannot start server: {exc}\nTry another port: python run_web.py --port 8766\n")
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"RoadOps: {url}\nStop: Ctrl+C", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
