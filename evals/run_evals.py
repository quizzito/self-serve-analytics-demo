"""
Runs the pinned offline eval set against the agent and logs results.

Requires: pip install openai
          export NVIDIA_API_KEY=...

Run: python3 evals/run_evals.py
Writes: evals/results/<timestamp>.jsonl

Grading strategy:
  - Numeric expected answers: parsed straight out of the agent's mandatory
    "FINAL_ANSWER: <value>" line and compared in plain Python against
    expected_answer +/- tolerance_pct. No LLM call, no ambiguity.
  - If FINAL_ANSWER is missing entirely: automatic fail. This is the fix
    for the false-pass bug where an answer with no real number in it got
    graded "correct" because the LLM grader saw SQL that looked plausible.
  - Non-numeric expected answers (dates, "CLARIFY_OR_DEFAULT_NET"): fall
    back to a single LLM grading call, since these need judgment, not just
    arithmetic. This also cuts LLM grader calls roughly in half versus
    grading everything with an LLM, which helps with rate limits too.
"""
import datetime
import json
import os
import re
import sys
import time

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
SECONDS_BETWEEN_EVALS = 5


def grader_call_with_retry(**kwargs):
    last_err = None
    for attempt in range(5):
        try:
            return grader_client.chat.completions.create(**kwargs)
        except openai.RateLimitError as e:
            last_err = e
            wait = 15 * (attempt + 1)
            print(f"  (rate limited, waiting {wait}s before retrying grader call)")
            time.sleep(wait)
        except (openai.APITimeoutError, openai.APIConnectionError) as e:
            last_err = e
            wait = 2 ** attempt
            print(f"  (timeout/connection stall, retrying in {wait}s: {e})")
            time.sleep(wait)
        except Exception as e:
            last_err = e
            if "DEGRADED" in str(e) or "500" in str(e):
                wait = 2 ** attempt
                print(f"  (transient error, retrying in {wait}s: {e})")
                time.sleep(wait)
                continue
            raise
    raise last_err


def extract_final_answer(agent_answer: str):
    """Pull the value out of the mandatory 'FINAL_ANSWER: <value>' line.
    Returns None if the agent never committed to one -- which is itself
    an automatic fail, not something worth an LLM call to adjudicate."""
    match = re.search(r"FINAL_ANSWER:\s*(\S+)", agent_answer)
    return match.group(1).strip() if match else None


def numeric_grade(final_value: str, expected: float, tolerance_pct: float) -> dict:
    try:
        agent_num = float(re.sub(r"[^\d.\-]", "", final_value))
    except (ValueError, TypeError):
        return {
            "correct": False,
            "reasoning": f"FINAL_ANSWER value '{final_value}' is not parseable as a number.",
            "method": "automatic",
        }
    expected_num = float(expected)
    if expected_num == 0:
        correct = agent_num == 0
    else:
        pct_diff = abs(agent_num - expected_num) / abs(expected_num) * 100
        correct = pct_diff <= tolerance_pct
    return {
        "correct": correct,
        "reasoning": f"Programmatic check: agent={agent_num}, expected={expected_num}, tolerance={tolerance_pct}%.",
        "method": "automatic",
    }


def llm_grade(question: str, expected: str, agent_answer: str, snapshot_date: str) -> dict:
    prompt = f"""Grade this analytics agent response.

Question: {question}
Expected answer or expected behavior: {expected}
Known correct data snapshot date: {snapshot_date}
Agent's full response:
---
{agent_answer}
---

The agent's FINAL_ANSWER line has already been checked for presence. Judge
whether the value and surrounding answer are substantively correct given
the expected answer or expected behavior described above.

Reply with ONLY a JSON object (no markdown fences, no explanation before or after):
{{"correct": true, "reasoning": "one sentence"}}
"""
    resp = grader_call_with_retry(
        model=GRADER_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.choices[0].message.content or ""
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        parsed = json.loads(text)
        parsed["method"] = "llm"
        return parsed
    except json.JSONDecodeError:
        return {"correct": False, "reasoning": f"unparseable grader output: {text[:200]}", "method": "llm"}


def grade(ev: dict, agent_answer: str, snapshot_date: str) -> dict:
    final_value = extract_final_answer(agent_answer)

    if final_value is None:
        return {
            "correct": False,
            "reasoning": "No FINAL_ANSWER line found -- agent did not commit to a concrete answer.",
            "method": "automatic",
        }

    expected = ev["expected_answer"]
    if isinstance(expected, (int, float)):
        return numeric_grade(final_value, expected, ev.get("tolerance_pct", 0))

    # Non-numeric expected answer (dates, special sentinel values like
    # "CLARIFY_OR_DEFAULT_NET") -- needs judgment, use the LLM.
    return llm_grade(ev["question"], str(expected), agent_answer, snapshot_date)


def run():
    with open(EVAL_SET_PATH) as f:
        eval_set = json.load(f)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    out_path = os.path.join(RESULTS_DIR, f"{ts}.jsonl")

    rows = []
    for i, ev in enumerate(eval_set["evals"]):
        print(f"\nrunning: {ev['id']} - {ev['question']}")
        try:
            agent_answer = answer_question(ev["question"])
        except Exception as e:
            agent_answer = f"AGENT ERROR: {e}"

        grading = grade(ev, agent_answer, eval_set["snapshot_date"])
        row = {
            "timestamp": ts,
            "eval_id": ev["id"],
            "category": ev["category"],
            "question": ev["question"],
            "expected_answer": ev["expected_answer"],
            "agent_answer": agent_answer,
            "correct": grading.get("correct", False),
            "grading_method": grading.get("method", "unknown"),
            "grader_reasoning": grading.get("reasoning", ""),
        }
        rows.append(row)
        status = "PASS" if row["correct"] else "FAIL"
        print(f"[{status}] {ev['id']} (graded {row['grading_method']})")
        if not row["correct"]:
            print(f"         expected={ev['expected_answer']!r} reasoning={row['grader_reasoning']}")

        if i < len(eval_set["evals"]) - 1:
            time.sleep(SECONDS_BETWEEN_EVALS)

    with open(out_path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    n_correct = sum(r["correct"] for r in rows)
    n_auto = sum(r["grading_method"] == "automatic" for r in rows)
    print(f"\n{n_correct}/{len(rows)} correct ({100*n_correct/len(rows):.0f}%)")
    print(f"{n_auto}/{len(rows)} graded programmatically (no LLM call)")
    print(f"results written to {out_path}")


if __name__ == "__main__":
    run()