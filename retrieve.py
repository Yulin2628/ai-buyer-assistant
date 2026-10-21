import os
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer


PROJECT_ROOT = Path(__file__).resolve().parent

PRODUCTS_PATH = (
    PROJECT_ROOT / "data" / "public_products_raw.jsonl"
)

MODEL_NAME = (
    "sentence-transformers/"
    "paraphrase-multilingual-MiniLM-L12-v2"
)


from catalog import to_text, build_product_text, load_products


class ProductRetriever:
    def __init__(self, products=None):
        self.products = products if products is not None else load_products()

        print(f"已读取 {len(self.products)} 个产品。")
        print("正在加载 Embedding 模型……", flush=True)


        self.model = SentenceTransformer(
            MODEL_NAME,
            device="cpu",
            cache_folder=str(Path(os.environ.get("BUYER_MODEL_CACHE", PROJECT_ROOT / "models"))),
        )

        product_texts = [
            build_product_text(product)
            for product in self.products
        ]

        print("正在把产品资料转换成向量……")

        self.product_vectors = self.model.encode(
            product_texts,
            batch_size=16,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=True,
        )

        print(f"产品向量矩阵形状：{self.product_vectors.shape}")

    def retrieve(self, question, top_k=5):
        if not question.strip():
            raise ValueError("检索需求不能为空。")

        if top_k < 1:
            raise ValueError("top_k 必须大于或等于 1。")


        question_vector = self.model.encode(
            question,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )


        scores = self.product_vectors @ question_vector


        ranked_indices = np.argsort(-scores)[:top_k]

        results = []

        for index in ranked_indices:
            results.append({
                "product": self.products[int(index)],
                "retrieval_score": float(scores[index]),
            })

        return results


def main():
    retriever = ProductRetriever()

    question = "浅粉色、简约、适合春季家居装饰的仿真花"

    results = retriever.retrieve(question, top_k=5)

    print(f"\n买手需求：{question}")
    print("\n最相关的候选产品：")

    for rank, result in enumerate(results, start=1):
        product = result["product"]

        print()
        print(f"第 {rank} 名")
        print(f"产品编号：{product.get('parent_asin')}")
        print(f"标题：{product.get('title')}")
        print(f"相似度：{result['retrieval_score']:.4f}")

        price = product.get("price")

        if price is None:
            print("原始价格：未知")
        else:
            print(f"原始价格字段（USD）：{price}")


if __name__ == "__main__":
    main()
