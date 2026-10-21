import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"


def detail(question, product_id):
    return {
        "question": question,
        "answer": {
            "action": "get_product_details",
            "arguments": {"product_id": product_id},
        },
    }


def search(question, requirement):
    return {
        "question": question,
        "answer": {
            "action": "search_products",
            "arguments": {"requirement": requirement},
        },
    }


def clarify(question):
    return {
        "question": question,
        "answer": {
            "action": "clarify",
            "message": "请提供你要查询的产品编号。",
        },
    }


def save_jsonl(path, examples):
    with path.open("w", encoding="utf-8") as file:
        for example in examples:
            file.write(
                json.dumps(example, ensure_ascii=False) + "\n"
            )


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


    train_examples = [
        detail("查一下 B111111111 的颜色。", "B111111111"),
        detail("B222222222 是什么材质？", "B222222222"),
        detail("请给我 B333333333 的详细资料。", "B333333333"),
        detail("查询编号 B444444444 的价格信息。", "B444444444"),

        search("找几款白色仿真玫瑰。", "白色仿真玫瑰"),
        search("我想要简约风格的花束。", "简约风格的花束"),
        search("推荐适合婚礼装饰的花环。", "适合婚礼装饰的花环"),
        search("有没有高度较低的粉色假花？", "高度较低的粉色假花"),

        clarify("那件产品是什么颜色？"),
        clarify("帮我看看这款花束的材质。"),
        clarify("这个产品的价格是多少？"),
        clarify("查询刚才说的那款花。"),
    ]


    eval_examples = [
        detail("能查一下 B555555555 的材质吗？", "B555555555"),
        detail("编号 B666666666 的产品叫什么？", "B666666666"),

        search("想找紫色的仿真花环。", "紫色的仿真花环"),
        search("帮忙挑几款适合客厅的花束。", "适合客厅的花束"),

        clarify("请查那一款的颜色。"),
        clarify("它卖多少钱？"),
    ]

    train_path = DATA_DIR / "agent_train.jsonl"
    eval_path = DATA_DIR / "agent_eval.jsonl"

    save_jsonl(train_path, train_examples)
    save_jsonl(eval_path, eval_examples)

    print(f"训练题：{len(train_examples)} 条 → {train_path}")
    print(f"评估题：{len(eval_examples)} 条 → {eval_path}")


if __name__ == "__main__":
    main()
