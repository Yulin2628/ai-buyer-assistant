"""Use the same validated planning service from the CLI and HTTP API."""
from datetime import datetime, timezone
import json
from pathlib import Path

from procurement.schema import InputError, validate_brief, validate_quotes, iso_date
from procurement.solver import frontier, solve
from procurement.store import PlanStore


def load_json(path):
    def invalid(value):
        raise InputError(f"Non-finite JSON number: {value}")
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=invalid)


def today():
    return datetime.now(timezone.utc).date().isoformat()


class Planner:
    def __init__(self, quotes_path, database_path=None):
        self.quotes_path = Path(quotes_path)
        self.store = PlanStore(database_path) if database_path is not None else None

    def plan(self, brief, as_of=None, idempotency_key=None):
        as_of = as_of or today()
        iso_date(as_of, "as_of")
        validate_brief(brief)
        snapshot = validate_quotes(load_json(self.quotes_path))
        if idempotency_key is not None:
            if self.store is None:
                raise InputError("Persistence requires a database")
            prior = self.store.existing(idempotency_key, {"brief": brief, "quotes": snapshot, "as_of": as_of})
            if prior:
                return {"plan": prior["body"]["plan"], "record": prior, "replayed": True}
        plan = solve(brief, snapshot, as_of)
        response = {"plan": plan}
        if idempotency_key is not None and plan["status"] == "optimal":
            response.update(record=self.store.create(idempotency_key, brief, snapshot, plan, as_of), replayed=False)
        return response

    def alternatives(self, brief, as_of=None):
        return frontier(brief, load_json(self.quotes_path), as_of or today())

    def review(self, plan_id, action, version, as_of=None):
        if self.store is None:
            raise InputError("Persistence requires a database")
        return self.store.review(plan_id, action, version, load_json(self.quotes_path), as_of or today())
