import os
from pathlib import Path

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM


PROJECT_ROOT = Path(__file__).resolve().parent
MODEL_NAME = "Qwen/Qwen2.5-0.5B-Instruct"
CACHE_DIR = str(Path(os.environ.get("BUYER_MODEL_CACHE", PROJECT_ROOT / "models")))


class LocalLLM:
    def __init__(self, adapter_path=None):

        self.tokenizer = AutoTokenizer.from_pretrained(
            MODEL_NAME,
            cache_dir=CACHE_DIR,
        )


        self.model = AutoModelForCausalLM.from_pretrained(
            MODEL_NAME,
            cache_dir=CACHE_DIR,
        ).to("cpu")

        if adapter_path is not None:
            from peft import PeftModel
            self.model = PeftModel.from_pretrained(self.model, str(adapter_path))
        self.model.eval()

    def generate_answer(self, prompt):
        messages = [
            {
                "role": "system",
                "content": (
                    "根据用户提供的资料回答。"
                    "资料不足时说明未知，不要编造。"
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]


        text = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )


        inputs = self.tokenizer(
            text,
            return_tensors="pt",
            add_special_tokens=False,
        )


        with torch.inference_mode():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=384,
                do_sample=False,
                pad_token_id=self.tokenizer.eos_token_id,
            )


        input_length = inputs["input_ids"].shape[1]
        new_tokens = outputs[0, input_length:]


        return self.tokenizer.decode(
            new_tokens,
            skip_special_tokens=True,
        )


if __name__ == "__main__":
    llm = LocalLLM()

    demo_prompt = """
资料：
[DEMO001] 粉色仿真玫瑰，装饰简洁，价格未知。
[DEMO002] 蓝色仿真百合，带闪亮装饰，价格未知。

问题：
我想找粉色、简约的仿真花。
推荐一款并标注编号，不要猜测价格。
"""

    print(llm.generate_answer(demo_prompt))
