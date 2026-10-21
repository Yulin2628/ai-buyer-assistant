"""Catalogue loading shared by the offline and neural search paths."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PUBLIC_PATH = ROOT / "data" / "public_products_raw.jsonl"
DEMO_PATH = ROOT / "data" / "demo_products.json"


def to_text(value):
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(f"{key}: {to_text(item)}" for key, item in value.items())
    if isinstance(value, list):
        return " ".join(to_text(item) for item in value)
    return str(value).strip()


def build_product_text(product):
    return "\n".join(filter(None, (to_text(product.get(key)) for key in
                      ("title", "features", "description", "details"))))


def load_products(path=None):
    path = Path(path) if path else PUBLIC_PATH
    if not path.is_file():
        raise FileNotFoundError(f"Catalogue not found: {path}. Run download_catalog.py or use --demo.")
    if path.suffix == ".json":
        products = json.loads(path.read_text(encoding="utf-8"))
    else:
        products = []
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                try:
                    products.append(json.loads(line))
                except json.JSONDecodeError as error:
                    raise ValueError(f"Invalid JSON at {path}:{number}") from error
    if not isinstance(products, list) or not products:
        raise ValueError("Catalogue must contain a non-empty list of products.")
    normalized = []
    seen = set()
    for product in products:
        if not isinstance(product, dict):
            raise ValueError("Each product must be an object.")
        product = dict(product)
        product_id = product.get("parent_asin") or product.get("id")
        if not isinstance(product_id, str) or not product_id.strip():
            raise ValueError("Each product needs an id or parent_asin.")
        if product_id in seen:
            raise ValueError(f"Duplicate product ID: {product_id}")
        seen.add(product_id)
        product["parent_asin"] = product_id
        product["title"] = product.get("title") or product.get("name") or product_id
        if not isinstance(product.get("details"), dict):
            product["details"] = {}
        if product.get("source") == "synthetic_demo":
            product["details"].update({key: product.get(key) for key in
                                       ("color", "form", "material", "style", "height_cm", "diameter_cm")})
        normalized.append(product)
    return normalized
