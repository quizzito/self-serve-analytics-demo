"""
Prints a clean table of expected vs actual answers from an eval results
file, since the raw .jsonl and the console PASS/FAIL log don't show this
side by side.

Run: python3 evals/summarize_results.py                 # most recent run
     python3 evals/summarize_results.py path/to/file.jsonl
"""
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(HERE, "results")


def extract_final_answer(agent_answer: str):
    match = re.search(r"FINAL_ANSWER:\s*(\S+)", agent_answer)
    return match.group(1).strip() if match else "(none given)"


def main():
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        files = sorted(glob.glob(os.path.join(RESULTS_DIR, "*.jsonl")))
        if not files:
            print("No result files found in evals/results/. Run evals/run_evals.py first.")
            return
        path = files[-1]

    print(f"Reading: {path}\n")

    rows = []
    with open(path) as f:
        for line in f:
            rows.append(json.loads(line))

    # Column widths
    id_w = max(len(r["eval_id"]) for r in rows) + 2
    exp_w = max(len(str(r["expected_answer"])) for r in rows) + 2
    act_w = max(len(extract_final_answer(r["agent_answer"])) for r in rows) + 2

    header = f"{'ID':<{id_w}}{'EXPECTED':<{exp_w}}{'ACTUAL':<{act_w}}{'RESULT':<8}METHOD"
    print(header)
    print("-" * len(header))

    for r in rows:
        actual = extract_final_answer(r["agent_answer"])
        result = "PASS" if r["correct"] else "FAIL"
        print(f"{r['eval_id']:<{id_w}}{str(r['expected_answer']):<{exp_w}}{actual:<{act_w}}{result:<8}{r.get('grading_method', '?')}")

    n_correct = sum(r["correct"] for r in rows)
    print(f"\n{n_correct}/{len(rows)} correct ({100*n_correct/len(rows):.0f}%)")


if __name__ == "__main__":
    main()