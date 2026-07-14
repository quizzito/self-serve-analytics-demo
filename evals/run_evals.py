"""
Runs the pinned offline eval set against the agent and logs results.

Requires: pip install openai
          export NVIDIA_API_KEY=...

Run: python3 evals/run_evals.py
Writes: evals/results/<timestamp>.jsonl
"""
import datetime
import json
import os
import sys

import openai
from openai import OpenAI

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "agent"))
from analytics_agent import answer_question  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL_SET_PATH = os.path.join(HERE, "eval_set.json")
RESULTS_DIR = os.path.join(HERE, "results")

grader_client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=os.environ["NVIDIA_API_KEY"],
    timeout=30.0,
)
GRADER_MODEL = "mistralai/mistral-nemotron"


def grade(question: str, expected: str, agent_answer: str, snapshot_date: str) -> dict:
    prompt = f"""Grade this analytics agent response STRICTLY.

Question: {question}
Expected answer: {expected}
Known correct data snapshot date: {snapshot_date}
Agent's full response:
---
{agent_answer}
---

Grading rules (apply ALL of these):
1. If the agent did not state a concrete final number/value matching the
   expected answer -- e.g. it only described a plan, wrote SQL it didn't
   execute, or apologized for an error without recovering -- mark correct=false,
   even if the SQL shown looks like it would have worked.
2. If the response includes a "Freshness" or date-window field in its
   provenance footer, that date MUST match {snapshot_date} (for freshness)
   or be a window ending on/near {snapshot_date} (for date windows). If the
   footer shows a fabricated/incorrect date, set has_provenance_footer=true
   but also note the mismatch in reasoning, and mark correct=false.
3. Numeric answers should match within reasonable rounding tolerance.

Reply with ONLY a JSON object (no markdown fences, no explanation before or after):
{{"correct": true, "has_provenance_footer": true, "reasoning": "one sentence"}}
"""
    resp = grader_client.chat.completions.create(
        model=GRADER_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.choices[0].message.content or ""
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"correct": False, "has_provenance_footer": False, "reasoning": f"unparseable grader output: {text[:200]}"}


def run():
    with open(EVAL_SET_PATH) as f:
        eval_set = json.load(f)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    out_path = os.path.join(RESULTS_DIR, f"{ts}.jsonl")

    rows = []
    for ev in eval_set["evals"]:
        print(f"\nrunning: {ev['id']} - {ev['question']}")
        try:
            agent_answer = answer_question(ev["question"])
        except Exception as e:
            agent_answer = f"AGENT ERROR: {e}"

        grading = grade(ev["question"], str(ev["expected_answer"]), agent_answer, eval_set["snapshot_date"])
        row = {
            "timestamp": ts,
            "eval_id": ev["id"],
            "category": ev["category"],
            "question": ev["question"],
            "expected_answer": ev["expected_answer"],
            "agent_answer": agent_answer,
            "correct": grading.get("correct", False),
            "has_provenance_footer": grading.get("has_provenance_footer", False),
            "grader_reasoning": grading.get("reasoning", ""),
        }
        rows.append(row)
        status = "PASS" if row["correct"] else "FAIL"
        print(f"[{status}] {ev['id']}")
        if not row["correct"]:
            print(f"         expected={ev['expected_answer']!r} reasoning={row['grader_reasoning']}")

    with open(out_path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    n_correct = sum(r["correct"] for r in rows)
    n_footer = sum(r["has_provenance_footer"] for r in rows)
    print(f"\n{n_correct}/{len(rows)} correct ({100*n_correct/len(rows):.0f}%)")
    print(f"{n_footer}/{len(rows)} included provenance footer")
    print(f"results written to {out_path}")


if __name__ == "__main__":
    run()