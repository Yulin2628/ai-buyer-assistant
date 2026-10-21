"""Command-line entry point. The demo requires only the Python standard library."""

import argparse
import json
import sys
from pathlib import Path
from service import BuyerService


def parser():
    result = argparse.ArgumentParser(description="Search a catalogue of artificial flowers.")
    result.add_argument("--demo", action="store_true", help="Use the included synthetic catalogue")
    result.add_argument("--catalog", type=Path, help="JSON/JSONL catalogue path")
    result.add_argument("--backend", choices=("lexical", "neural"), default="lexical")
    result.add_argument("--rerank", action="store_true", help="Load the cross-encoder reranker")
    commands = result.add_subparsers(dest="command", required=True)
    search = commands.add_parser("search")
    search.add_argument("query")
    search.add_argument("--top-k", type=int, default=3)
    for name in ("color", "form", "currency"):
        search.add_argument(f"--{name}")
    search.add_argument("--max-price", type=float)
    search.add_argument("--max-height-cm", type=float)
    commands.add_parser("details").add_argument("product_id")
    chat = commands.add_parser("chat", help="Local LLM with validated catalogue tools")
    chat.add_argument("--adapter", type=Path)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        service = BuyerService(args.catalog, args.demo, args.backend, args.rerank)
        if args.command == "search":
            filters = {key: getattr(args, key) for key in
                       ("color", "form", "currency", "max_price", "max_height_cm")}
            output = service.search(args.query, args.top_k, **filters)
        elif args.command == "details":
            output = service.details(args.product_id)
        else:
            from agent import run_chat
            from local_llm import LocalLLM
            run_chat(LocalLLM(adapter_path=args.adapter), service)
            return 0
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, ImportError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
