import argparse
import json
from pathlib import Path
from evaluation import evaluate, load_examples

ROOT = Path(__file__).resolve().parent


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evaluate base or LoRA tool decisions without running tools.")
    parser.add_argument("--adapter", type=Path, help="Saved LoRA directory; omit for the base model")
    parser.add_argument("--data", type=Path, default=ROOT / "data" / "agent_eval.jsonl")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    from local_llm import LocalLLM
    report = evaluate(LocalLLM(adapter_path=args.adapter), load_examples(args.data))
    report["adapter"] = str(args.adapter) if args.adapter else None
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
