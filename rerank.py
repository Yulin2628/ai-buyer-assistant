import os
from pathlib import Path

import torch
from sentence_transformers import CrossEncoder

from retrieve import ProductRetriever, build_product_text


PROJECT_ROOT = Path(__file__).resolve().parent


class ProductReranker:
    def __init__(self):
        print("正在加载重排序模型……", flush=True)

        self.model = CrossEncoder(
            "BAAI/bge-reranker-base",
            device="cpu",
            max_length=512,
            activation_fn=torch.nn.Identity(),
            cache_folder=str(Path(os.environ.get("BUYER_MODEL_CACHE", PROJECT_ROOT / "models"))),
        )


    def rerank(self, question, candidates, final_k=5):
        if final_k < 1:
            raise ValueError("final_k 必须大于或等于 1。")

        if not candidates:
            return []

        pairs = []

        for candidate in candidates:
            product_text = build_product_text(
                candidate["product"]
            )

            pairs.append([
                question,
                product_text,
            ])

        scores = self.model.predict(
            pairs,
            batch_size=2,
            show_progress_bar=True,
        )

        ranked_results = []

        for candidate, score in zip(candidates, scores):
            ranked_results.append({
                "product": candidate["product"],
                "retrieval_score": candidate["retrieval_score"],
                "rerank_score": float(score),
            })

        ranked_results.sort(
            key=lambda result: result["rerank_score"],
            reverse=True,
        )

        return ranked_results[:final_k]


def show_results(results):
    for rank, result in enumerate(results, start=1):
        product = result["product"]

        print(f"\n第 {rank} 名")
        print(f"编号：{product.get('parent_asin')}")
        print(f"标题：{product.get('title')}")
        print(f"召回分数：{result['retrieval_score']:.4f}")

        if "rerank_score" in result:
            print(f"重排序分数：{result['rerank_score']:.4f}")


def check_pink_color(product):
    details = product.get("details")

    if not isinstance(details, dict):
        return "unknown", "产品详情缺失"

    color_value = None


    for key, value in details.items():
        if str(key).strip().lower() == "color":
            color_value = value
            break

    if color_value is None:
        return "unknown", "没有颜色字段"

    color = str(color_value).strip().lower()


    pink_values = {
        "pink",
        "pink1",
        "light pink",
        "pale pink",
        "blush pink",
    }

    other_values = {
        "white",
        "blue",
        "red",
        "g-red",
        "purple",
        "yellow",
        "green",
        "black",
        "orange",
        "cream",
    }

    if color in pink_values:
        return "match", f"粉色系列：{color_value}"

    if color in other_values:
        return "mismatch", f"其他颜色：{color_value}"

    return "unknown", f"尚未识别的颜色写法：{color_value}"


def filter_pink_candidates(candidates):
    matched = []
    unknown = []
    rejected = []

    for candidate in candidates:
        status, reason = check_pink_color(
            candidate["product"]
        )

        checked = {
            **candidate,
            "color_check": status,
            "color_reason": reason,
        }

        if status == "match":
            matched.append(checked)
        elif status == "mismatch":
            rejected.append(checked)
        else:
            unknown.append(checked)

    return matched, unknown, rejected
def main():
    question = "浅粉色、简约、适合春季家居装饰的仿真花"

    retriever = ProductRetriever()


    candidates = retriever.retrieve(
        question,
        top_k=20,
    )

    print("\n===== 仅用向量检索：前 5 名 =====")
    show_results(candidates[:5])

    reranker = ProductReranker()


    results = reranker.rerank(
        question,
        candidates,
        final_k=5,
    )

    print("\n===== 加入重排序：前 5 名 =====")
    show_results(results)
    print("\n===== 检查前 5 名的颜色资料 =====")

    for result in results:
        product = result["product"]

        print(f"\n编号：{product.get('parent_asin')}")
        print(f"标题：{product.get('title')}")
        print(f"产品详情：{product.get('details')}")


if __name__ == "__main__":
    main()
