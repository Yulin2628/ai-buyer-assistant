import json
import random
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent


DATA_DIR = PROJECT_ROOT / "data"


PRODUCTS_PATH = DATA_DIR / "demo_products.json"


def create_demo_catalog():

    rng = random.Random(42)

    flower_types = [
        "玫瑰",
        "牡丹",
        "郁金香",
        "绣球",
        "雏菊",
    ]

    colors = [
        "浅粉色",
        "奶油色",
        "白色",
        "紫色",
    ]

    product_forms = [
        "单枝花",
        "花束",
        "花环",
    ]

    materials = [
        "布艺花瓣与塑料花茎",
        "塑料花瓣与塑料花茎",
    ]


    styles = [
        "简约",
        "田园",
        "复古",
    ]

    decorations = [
        "无额外装饰",
        "丝带",
        "闪亮装饰",
    ]

    products = []


    for flower in flower_types:
        for color in colors:
            for form in product_forms:
                for version in range(1, 3):
                    product_id = f"P{len(products) + 1:04d}"

                    material = rng.choice(materials)
                    style = rng.choice(styles)
                    decoration = rng.choice(decorations)

                    price = round(rng.uniform(3.0, 15.0), 2)


                    if form == "花环":
                        height_cm = None
                        diameter_cm = rng.choice([25, 30, 35, 40])
                        size_text = f"直径 {diameter_cm} cm"
                    else:
                        height_cm = rng.choice([25, 30, 35, 40, 45, 50])
                        diameter_cm = None
                        size_text = f"高度 {height_cm} cm"

                    product = {
                        "id": product_id,
                        "name": f"{color}{flower}{form}，款式 {version}",
                        "flower_type": flower,
                        "color": color,
                        "form": form,
                        "material": material,
                        "style": style,
                        "decoration": decoration,
                        "price": price,
                        "currency": "GBP",
                        "price_basis": "per_item",
                        "height_cm": height_cm,
                        "diameter_cm": diameter_cm,
                        "description": (
                            f"{color}仿真{flower}{form}，"
                            f"采用{material}，"
                            f"风格为{style}，"
                            f"装饰为{decoration}，"
                            f"{size_text}。"
                        ),

                        "image_path": None,
                        "source": "synthetic_demo",
                    }

                    products.append(product)

    return products


def load_or_create_products():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


    if not PRODUCTS_PATH.exists():
        products = create_demo_catalog()

        with PRODUCTS_PATH.open("w", encoding="utf-8") as file:
            json.dump(
                products,
                file,
                ensure_ascii=False,
                indent=2,
            )

        print("已创建模拟产品目录。")

    else:
        print("读取已有模拟产品目录。")

    with PRODUCTS_PATH.open("r", encoding="utf-8") as file:
        products = json.load(file)

    return products


def filter_products(products, requirements):
    results = []

    for product in products:
        if product["color"] != requirements["color"]:
            continue

        if product["form"] != requirements["form"]:
            continue

        if product["currency"] != requirements["currency"]:
            continue

        if product["price"] > requirements["max_price"]:
            continue

        height = product["height_cm"]


        if height is None:
            continue

        if height > requirements["max_height_cm"]:
            continue

        results.append(product)

    return results


def main():
    products = load_or_create_products()

    requirements = {
        "color": "浅粉色",
        "form": "花束",
        "currency": "GBP",
        "max_price": 10.00,
        "max_height_cm": 40,
    }

    results = filter_products(products, requirements)

    print(f"数据文件：{PRODUCTS_PATH}")
    print(f"产品总数：{len(products)}")
    print("注意：当前全部为模拟数据，价格为 GBP/件。")
    print()

    print("买手需求：")
    print("浅粉色花束，单价不超过 £10，高度不超过 40 cm。")
    print()

    print(f"符合条件的产品数量：{len(results)}")
    print()

    if not results:
        print("没有符合全部条件的产品。")
        return


    results.sort(key=lambda product: product["price"])

    for product in results:
        print(f"{product['id']} | {product['name']}")
        print(f"价格：£{product['price']:.2f}")
        print(f"描述：{product['description']}")
        print()


if __name__ == "__main__":
    main()
