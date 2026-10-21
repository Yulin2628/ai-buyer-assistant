import json
from agent import make_decision_prompt, parse_decision, validate_decision


def evaluate(llm, examples):
    if not examples:
        raise ValueError("Evaluation set is empty.")
    rows = []
    for example in examples:
        question, expected = example["question"], example["answer"]
        raw = llm.generate_answer(make_decision_prompt(question))
        try:
            predicted = parse_decision(raw)
            validate_decision(predicted, question)
            action_ok = predicted.get("action") == expected["action"]
            argument_ok = action_ok and (
                expected["action"] == "clarify" or
                predicted.get("arguments") == expected.get("arguments")
            )
            valid = True
        except ValueError:
            valid = action_ok = argument_ok = False
        rows.append({"question": question, "expected": expected, "raw_output": raw,
                     "valid_decision": valid, "action_correct": action_ok,
                     "exact_arguments_correct": argument_ok})
    return {"count": len(rows),
            "valid_decision_rate": sum(r["valid_decision"] for r in rows) / len(rows),
            "action_accuracy": sum(r["action_correct"] for r in rows) / len(rows),
            "exact_arguments_accuracy": sum(r["exact_arguments_correct"] for r in rows) / len(rows),
            "cases": rows}


def load_examples(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
