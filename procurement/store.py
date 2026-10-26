"""Local transactional review workflow; approval never places an order."""
from datetime import datetime, timezone
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import uuid

from procurement.schema import InputError, canonical, digest, integer, text
from procurement.verify import verify_plan


class ConflictError(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


class PlanStore:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS plans (
                    id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE,
                    input_sha256 TEXT NOT NULL, body_json TEXT NOT NULL, body_sha256 TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('draft','approved','rejected')),
                    version INTEGER NOT NULL, created_at TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def unpack(row):
        body = json.loads(row["body_json"])
        if digest(body) != row["body_sha256"]:
            raise ConflictError("Stored plan body failed its integrity check")
        return {"id": row["id"], "status": row["status"], "version": row["version"],
                "body_sha256": row["body_sha256"], "created_at": row["created_at"],
                "body": body}

    def get(self, plan_id):
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
            if row is None:
                raise KeyError("Plan not found")
            return self.unpack(row)

    def existing(self, key, inputs):
        text(key, "idempotency key")
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM plans WHERE idempotency_key=?", (key,)).fetchone()
            if row is None:
                return None
            if row["input_sha256"] != digest(inputs):
                raise ConflictError("Idempotency key was already used for different inputs")
            return self.unpack(row)

    def create(self, key, brief, snapshot, plan, as_of):
        if plan.get("status") != "optimal":
            raise InputError("Only independently verified optimal plans enter the review workflow")
        verify_plan(brief, snapshot, plan, as_of)
        inputs = {"brief": brief, "quotes": snapshot, "as_of": as_of}
        text(key, "idempotency key")
        body = {**inputs, "plan": plan}
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            prior = connection.execute("SELECT * FROM plans WHERE idempotency_key=?", (key,)).fetchone()
            if prior:
                if prior["input_sha256"] != digest(inputs):
                    raise ConflictError("Idempotency key was already used for different inputs")
                return self.unpack(prior)
            plan_id, stamp = uuid.uuid4().hex, now()
            connection.execute("INSERT INTO plans VALUES (?,?,?,?,?,'draft',1,?)",
                               (plan_id, key, digest(inputs), canonical(body), digest(body), stamp))
        return self.get(plan_id)

    def review(self, plan_id, action, expected_version, current_quotes, as_of):
        if action not in ("approve", "reject"):
            raise InputError("Review action must be approve or reject")
        integer(expected_version, "expected_version", 1)
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
            if row is None:
                raise KeyError("Plan not found")
            record = self.unpack(row)
            if row["version"] != expected_version or row["status"] != "draft":
                raise ConflictError("Stale version or plan has already been reviewed")
            if action == "approve":
                body = record["body"]
                if digest(current_quotes) != digest(body["quotes"]):
                    raise ConflictError("Quote snapshot changed; create a new plan before approval")
                try:
                    verify_plan(body["brief"], current_quotes, body["plan"], as_of)
                except InputError as error:
                    raise ConflictError(f"Plan is no longer eligible for approval: {error}") from error
            status, version = ("approved" if action == "approve" else "rejected"), expected_version + 1
            connection.execute("UPDATE plans SET status=?,version=? WHERE id=? AND version=?",
                               (status, version, plan_id, expected_version))
        return self.get(plan_id)
