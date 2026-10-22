"""Strict, versioned procurement inputs; monetary values become integer pennies."""
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json


class InputError(ValueError):
    pass


ATTRIBUTES = {"color", "form", "material", "style"}
CURRENCIES = {"GBP", "USD", "EUR"}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def fields(value, required, optional=(), name="object"):
    if not isinstance(value, dict):
        raise InputError(f"{name} must be an object")
    missing = set(required) - value.keys()
    extra = value.keys() - set(required) - set(optional)
    if missing or extra:
        raise InputError(f"{name}: missing {sorted(missing)}, unsupported {sorted(extra)}")


def integer(value, name, minimum=0, maximum=1_000_000):
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise InputError(f"{name} must be an integer between {minimum} and {maximum}")
    return value


def text(value, name):
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise InputError(f"{name} must be a nonempty string of at most 200 characters")
    return value.strip()


def money(value, name="amount"):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise InputError(f"{name} must be a monetary amount")
    try:
        if len(str(value)) > 64:
            raise InputError(f"Invalid {name}")
        number = Decimal(str(value))
        if not number.is_finite() or not 0 <= number <= 1_000_000:
            raise InputError(f"{name} is outside the supported monetary range")
        pennies = number * 100
        if not number.is_finite() or not 0 <= number <= 1_000_000 or pennies != pennies.to_integral_value():
            raise InputError(f"{name} must be nonnegative, finite and exact to two decimal places")
        return int(pennies)
    except (InvalidOperation, ValueError, OverflowError) as error:
        raise InputError(f"Invalid {name}") from error


def iso_date(value, name):
    try:
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError()
        return date.fromisoformat(value)
    except ValueError as error:
        raise InputError(f"{name} must use YYYY-MM-DD") from error


def attributes(value):
    fields(value, (), ATTRIBUTES, "attributes")
    return {key: text(item, key) for key, item in value.items()}


def validate_brief(brief):
    fields(brief, ("schema_version", "currency", "budget", "deadline_days", "lines"),
           ("max_suppliers",), "brief")
    if brief["schema_version"] != 1 or isinstance(brief["schema_version"], bool):
        raise InputError("Unsupported brief schema_version")
    if not isinstance(brief["currency"], str) or brief["currency"] not in CURRENCIES:
        raise InputError("Use GBP, USD or EUR; no currency conversion is performed")
    money(brief["budget"], "budget")
    integer(brief["deadline_days"], "deadline_days", 1, 365)
    if "max_suppliers" in brief:
        integer(brief["max_suppliers"], "max_suppliers", 1, 100)
    if not isinstance(brief["lines"], list) or not 1 <= len(brief["lines"]) <= 12:
        raise InputError("brief.lines must contain 1-12 requirements")
    seen = set()
    for line in brief["lines"]:
        fields(line, ("id", "quantity", "attributes"), ("max_surplus_units", "max_height_cm"), "line")
        line_id = text(line["id"], "line.id")
        if line_id != line["id"] or line_id in seen:
            raise InputError("Line IDs must be unique and have no surrounding whitespace")
        seen.add(line_id)
        integer(line["quantity"], "quantity", 1, 100_000)
        integer(line.get("max_surplus_units", 0), "max_surplus_units", 0, 100_000)
        attributes(line["attributes"])
        if "max_height_cm" in line:
            integer(line["max_height_cm"], "max_height_cm", 1, 10_000)
    return brief


def validate_quotes(snapshot):
    fields(snapshot, ("schema_version", "source", "suppliers", "offers"), name="quote snapshot")
    if snapshot["schema_version"] != 1 or isinstance(snapshot["schema_version"], bool):
        raise InputError("Unsupported quote schema_version")
    text(snapshot["source"], "source")
    if not isinstance(snapshot["suppliers"], list) or not 1 <= len(snapshot["suppliers"]) <= 100:
        raise InputError("Use 1-100 suppliers")
    suppliers = set()
    for supplier in snapshot["suppliers"]:
        fields(supplier, ("id", "currency", "shipping"), name="supplier")
        sid = text(supplier["id"], "supplier.id")
        if sid != supplier["id"] or sid in suppliers:
            raise InputError("Supplier IDs must be unique and have no surrounding whitespace")
        suppliers.add(sid)
        if not isinstance(supplier["currency"], str) or supplier["currency"] not in CURRENCIES:
            raise InputError("Unsupported supplier currency")
        money(supplier["shipping"], "shipping")
    if not isinstance(snapshot["offers"], list) or not 1 <= len(snapshot["offers"]) <= 500:
        raise InputError("Use 1-500 offers")
    seen = set()
    for offer in snapshot["offers"]:
        fields(offer, ("id", "supplier_id", "product_id", "attributes", "currency", "pack_price",
                       "pack_size", "min_packs", "stock_packs", "lead_days", "quoted_on", "valid_until"),
               ("height_cm", "description"), "offer")
        oid = text(offer["id"], "offer.id")
        text(offer["supplier_id"], "supplier_id")
        if oid != offer["id"] or oid in seen or offer["supplier_id"] not in suppliers:
            raise InputError("Offer IDs must be unique and suppliers must exist")
        seen.add(oid)
        text(offer["product_id"], "product_id")
        attributes(offer["attributes"])
        if not isinstance(offer["currency"], str) or offer["currency"] not in CURRENCIES:
            raise InputError("Unsupported offer currency")
        money(offer["pack_price"], "pack_price")
        integer(offer["pack_size"], "pack_size", 1, 10_000)
        integer(offer["min_packs"], "min_packs", 1, 10_000)
        if offer["stock_packs"] is not None:
            integer(offer["stock_packs"], "stock_packs", 0, 100_000)
        if offer["lead_days"] is not None:
            integer(offer["lead_days"], "lead_days", 1, 365)
        if offer.get("height_cm") is not None:
            integer(offer["height_cm"], "height_cm", 1, 10_000)
        if offer["quoted_on"] is not None:
            iso_date(offer["quoted_on"], "quoted_on")
        if offer["valid_until"] is not None:
            iso_date(offer["valid_until"], "valid_until")
    return snapshot


def exclusion_reasons(offer, supplier, line, brief, as_of):
    reasons = []
    if offer["currency"] != brief["currency"] or supplier["currency"] != brief["currency"]:
        reasons.append("currency_mismatch")
    if offer["stock_packs"] is None:
        reasons.append("unknown_stock")
    elif offer["stock_packs"] < offer["min_packs"]:
        reasons.append("stock_below_minimum_order")
    if offer["lead_days"] is None:
        reasons.append("unknown_lead_time")
    elif offer["lead_days"] > brief["deadline_days"]:
        reasons.append("late_delivery")
    today = iso_date(as_of, "as_of")
    if offer["quoted_on"] is None or offer["valid_until"] is None:
        reasons.append("unknown_quote_validity")
    else:
        start = iso_date(offer["quoted_on"], "quoted_on")
        end = iso_date(offer["valid_until"], "valid_until")
        if not start <= today <= end:
            reasons.append("quote_not_current")
    for key, expected in line["attributes"].items():
        actual = offer["attributes"].get(key)
        if actual is None:
            reasons.append(f"unknown_{key}")
        elif actual.casefold().strip() != expected.casefold().strip():
            reasons.append(f"mismatched_{key}")
    if "max_height_cm" in line:
        if offer.get("height_cm") is None:
            reasons.append("unknown_height")
        elif offer["height_cm"] > line["max_height_cm"]:
            reasons.append("height_exceeded")
    return reasons
