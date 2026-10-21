import json
from pathlib import Path

import torch
from peft import LoraConfig, TaskType, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer

from agent import make_decision_prompt


PROJECT_ROOT = Path(__file__).resolve().parent
TRAIN_PATH = PROJECT_ROOT / "data" / "agent_train.jsonl"
MODEL_NAME = "Qwen/Qwen2.5-0.5B-Instruct"
CACHE_DIR = str(PROJECT_ROOT / "models")
SAVE_DIR = PROJECT_ROOT / "models" / "agent_lora"


def prepare_example(example, tokenizer):
    question = example["question"]
    answer_text = json.dumps(
        example["answer"],
        ensure_ascii=False,
    )

    prompt = make_decision_prompt(question)

    messages = [
        {
            "role": "system",
            "content": (
                "根据用户提供的资料回答。"
                "资料不足时说明未知，不要编造。"
            ),
        },
        {"role": "user", "content": prompt},
    ]


    prefix_text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )


    full_text = tokenizer.apply_chat_template(
        messages + [
            {"role": "assistant", "content": answer_text}
        ],
        tokenize=False,
        add_generation_prompt=False,
    )

    prefix_ids = tokenizer(
        prefix_text,
        add_special_tokens=False,
    )["input_ids"]

    full_ids = tokenizer(
        full_text,
        add_special_tokens=False,
    )["input_ids"]


    if len(full_ids) > 768:
        raise ValueError(
            f"这条样本有 {len(full_ids)} 个 token，"
            "超过当前设置的 768。"
        )


    labels = (
        [-100] * len(prefix_ids)
        + full_ids[len(prefix_ids):]
    )

    assert len(labels) == len(full_ids)
    assert any(x != -100 for x in labels)

    return full_ids, labels



def main():
    if not torch.cuda.is_available():
        raise RuntimeError(
            "当前 PyTorch 没有识别到 NVIDIA 显卡。"
            "请先检查 CUDA 版 PyTorch 的安装。"
        )
    
    device = "cuda"
    
    gpu = torch.cuda.get_device_properties(0)
    print("显卡：", gpu.name, flush=True)
    print(
        f"显存：{gpu.total_memory / 1024**3:.1f} GB",
        flush=True,
    )
    
    
    tokenizer = AutoTokenizer.from_pretrained(
        MODEL_NAME,
        cache_dir=CACHE_DIR,
    )
    
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        cache_dir=CACHE_DIR,
        torch_dtype=torch.float16,
    ).to(device)
    
    
    model.config.use_cache = False
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()
    
    
    lora_config = LoraConfig(
        r=4,
        lora_alpha=8,
        target_modules=["q_proj", "v_proj"],
        lora_dropout=0.0,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
    )
    
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()
    
    
    with TRAIN_PATH.open("r", encoding="utf-8") as file:
        examples = [
            json.loads(line)
            for line in file
            if line.strip()
        ]
    
    optimizer = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad],
        lr=2e-4,
    )
    
    model.train()
    
    
    for index, example in enumerate(examples, start=1):
        input_ids, labels = prepare_example(example, tokenizer)
    
        input_tensor = torch.tensor(
            [input_ids],
            dtype=torch.long,
            device=device,
        )
    
        label_tensor = torch.tensor(
            [labels],
            dtype=torch.long,
            device=device,
        )
    
        optimizer.zero_grad()
    
        outputs = model(
            input_ids=input_tensor,
            labels=label_tensor,
        )
    
        loss = outputs.loss
        loss.backward()
    
        optimizer.step()
    
        print(
            f"进度 {index}/{len(examples)} | "
            f"loss={loss.item():.4f}",
            flush=True,
        )
    
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(SAVE_DIR)
    tokenizer.save_pretrained(SAVE_DIR)
    
    print("训练完成，LoRA 已保存到：", SAVE_DIR)


if __name__ == "__main__":
    main()
