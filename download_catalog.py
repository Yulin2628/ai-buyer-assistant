import gzip
import json
from pathlib import Path
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"


OUTPUT_PATH = DATA_DIR / "public_products_raw.jsonl"


DATA_URL = (
    "https://mcauleylab.ucsd.edu/public_datasets/data/"
    "amazon_2023/raw/meta_categories/"
    "meta_Home_and_Kitchen.jsonl.gz"
)


TARGET_PRODUCTS = 300


MAX_SCAN = 30000


def is_relevant_product(product):
    title = (product.get("title") or "").lower()

    keywords = [
        "artificial flower",
        "silk flower",
        "fake flower",
        "faux flower",
        "artificial plant",
        "faux plant",
        "artificial rose",
        "artificial tulip",
        "artificial peon",
        "wreath",
    ]

    return any(keyword in title for keyword in keywords)


def load_saved_ids():
    saved_ids = set()

    if OUTPUT_PATH.exists():
        with OUTPUT_PATH.open("r", encoding="utf-8") as file:
            for line in file:
                if line.strip():
                    product = json.loads(line)
                    saved_ids.add(product["parent_asin"])

    return saved_ids


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    saved_ids = load_saved_ids()

    print(f"已有产品：{len(saved_ids)}")
    print(f"目标产品数：{TARGET_PRODUCTS}")
    print(f"最多扫描：{MAX_SCAN} 条记录")
    print("正在连接公开数据源……", flush=True)

    if len(saved_ids) >= TARGET_PRODUCTS:
        print("已有数据达到本轮目标，无需再次下载。")
        return

    request = Request(
        DATA_URL,
        headers={"User-Agent": "buyer-selection-research/0.1"},
    )

    scanned = 0
    added = 0

    try:

        with urlopen(request, timeout=60) as response:
            print("连接成功，开始读取……", flush=True)

            with gzip.GzipFile(fileobj=response) as stream:

                with OUTPUT_PATH.open("a", encoding="utf-8") as output:
                    for raw_line in stream:
                        scanned += 1
                        product = json.loads(raw_line)

                        product_id = product.get("parent_asin")

                        if (
                            product_id
                            and product_id not in saved_ids
                            and is_relevant_product(product)
                        ):

                            output.write(
                                json.dumps(product, ensure_ascii=False)
                                + "\n"
                            )
                            output.flush()

                            saved_ids.add(product_id)
                            added += 1

                            if added <= 5:
                                print(
                                    f"找到：{product.get('title')}",
                                    flush=True,
                                )

                        if scanned % 1000 == 0:
                            print(
                                f"已扫描 {scanned} 条，"
                                f"已保存 {len(saved_ids)} 个产品",
                                flush=True,
                            )

                        if len(saved_ids) >= TARGET_PRODUCTS:
                            break

                        if scanned >= MAX_SCAN:
                            break

    except (OSError, EOFError) as error:
        print(f"\n网络或压缩数据读取失败：{error}")
        print("已经保存的产品会保留。")
        print("再次运行会从源文件开头扫描，并跳过已有产品。")
        return

    print()
    print(f"本次扫描：{scanned} 条")
    print(f"本次新增：{added} 个产品")
    print(f"累计保存：{len(saved_ids)} 个产品")
    print(f"文件位置：{OUTPUT_PATH}")

    if len(saved_ids) < TARGET_PRODUCTS:
        print("本轮未达到目标，先检查已有数据，再决定扩大扫描范围。")


if __name__ == "__main__":
    main()
