"""Loopback-only prototype API. Approved drafts are never sent to suppliers."""
import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import sqlite3

from procurement.application import Planner
from procurement.schema import InputError, canonical, fields, text
from procurement.store import ConflictError


def make_server(planner, port=0):
    if planner.store is None:
        raise InputError("The HTTP review workflow requires a database")
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, code, value):
            payload = canonical(value).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            try:
                if self.path == "/health":
                    self.respond(200, {"status": "ok", "schema_version": 1, "orders_executed": False})
                elif self.path.startswith("/plans/") and len(self.path.split("/")) == 3:
                    self.respond(200, planner.store.get(self.path.split("/")[2]))
                else:
                    self.respond(404, {"error": "Not found"})
            except KeyError:
                self.respond(404, {"error": "Plan not found"})
            except ConflictError as error:
                self.respond(409, {"error": str(error)})

        def do_POST(self):
            try:
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise InputError("Content-Type must be application/json")
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError as error:
                    raise InputError("Invalid Content-Length") from error
                if not 1 <= length <= 65536:
                    self.respond(413, {"error": "JSON body must be 1-65536 bytes"})
                    return
                self.connection.settimeout(5)
                def nonfinite(value):
                    raise InputError(f"Non-finite number: {value}")
                data = json.loads(self.rfile.read(length), parse_constant=nonfinite)
                if self.path == "/plans":
                    fields(data, ("brief",), name="request")
                    key = text(self.headers.get("Idempotency-Key"), "Idempotency-Key")
                    response = planner.plan(data["brief"], idempotency_key=key)
                    code = 200 if response.get("replayed") else 201 if "record" in response else 422
                    self.respond(code, response)
                elif self.path.startswith("/plans/") and self.path.endswith("/review") and len(self.path.split("/")) == 4:
                    fields(data, ("action", "expected_version"), name="review")
                    self.respond(200, planner.review(self.path.split("/")[2], data["action"],
                                                      data["expected_version"]))
                else:
                    self.respond(404, {"error": "Not found"})
            except (InputError, json.JSONDecodeError, UnicodeDecodeError) as error:
                self.respond(400, {"error": str(error)})
            except ConflictError as error:
                self.respond(409, {"error": str(error)})
            except KeyError:
                self.respond(404, {"error": "Plan not found"})
            except (sqlite3.OperationalError, TimeoutError):
                self.respond(503, {"error": "Storage or request temporarily unavailable"})
    return HTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--quotes", type=Path, default=Path("data/procurement/quotes.json"))
    parser.add_argument("--database", type=Path, default=Path("local/plans.sqlite"))
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = make_server(Planner(args.quotes, args.database), args.port)
    print(f"Local planning API: http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
