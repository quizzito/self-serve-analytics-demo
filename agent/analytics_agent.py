"""
Analytics agent using NVIDIA Build's free OpenAI-compatible endpoint.
Requires: pip install openai duckdb
          export NVIDIA_API_KEY=...
Run: python3 agent/analytics_agent.py "What was our net revenue over the trailing 30 days?"
"""
import json
import os
import sys
import time

import duckdb
import openai
from openai import OpenAI

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DB_PATH = os.path.join(ROOT, "warehouse", "warehouse.duckdb")
SKILL_PATH = os.path.join(ROOT, "skills", "ecommerce-analytics", "SKILL.md")
REFS_DIR = os.path.join(ROOT, "skills", "ecommerce-analytics", "references")
METRICS_PATH = os.path.join(ROOT, "warehouse", "semantic_layer", "metrics.yml")

MODEL = "mistralai/mistral-nemotron"

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=os.environ["NVIDIA_API_KEY"],
    timeout=30.0,
)


def call_with_retry(**kwargs):
    last_err = None
    for attempt in range(4):
        try:
            return client.chat.completions.create(**kwargs)
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


def load_skill_context() -> str:
    parts = [open(SKILL_PATH).read(), open(METRICS_PATH).read()]
    for fname in sorted(os.listdir(REFS_DIR)):
        parts.append(open(os.path.join(REFS_DIR, fname)).read())
    return "\n\n---\n\n".join(parts)


def run_sql(sql: str) -> str:
    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        rows = con.execute(sql).fetchall()
        cols = [d[0] for d in con.description]
        return json.dumps({"columns": cols, "rows": rows}, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})
    finally:
        con.close()


def get_freshness() -> str:
    """Compute max(order_date) deterministically in code, once, rather than
    trusting the model to query and correctly report it. The model has
    repeatedly fabricated plausible-looking dates instead of doing this
    itself, even when explicitly instructed not to -- so this fact is now
    injected as ground truth instead of left to model behavior."""
    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        result = con.execute("select max(order_date) from fct_orders_net").fetchone()
        return str(result[0])
    finally:
        con.close()


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_sql",
            "description": (
                "Execute a read-only SQL query against the e-commerce "
                "warehouse. This is DuckDB SQL, NOT SQLite/MySQL/Postgres. "
                "For date arithmetic use DuckDB's interval syntax, e.g. "
                "`order_date > (select max(order_date) from fct_orders_net) "
                "- interval 30 day`. Do NOT use date('now', ...) or "
                "DATEADD() -- those are wrong dialects and will error. "
                "Only query views in the marts layer (fct_*, dim_*)."
            ),
            "parameters": {
                "type": "object",
                "properties": {"sql": {"type": "string"}},
                "required": ["sql"],
            },
        },
    }
]


def answer_question(question: str) -> str:
    freshness = get_freshness()

    system_prompt = (
        "You are an e-commerce analytics agent. Follow these skill "
        "instructions exactly, including the mandatory provenance footer "
        "format at the end of every answer. You MUST use the run_sql tool "
        "to get real numbers before answering -- never write out a query "
        "as text without executing it. If a query errors, fix the SQL and "
        "call run_sql again -- do not give up and describe the fix as text "
        "instead of actually running it.\n\n"
        f"KNOWN FACT (do not query for this, do not guess a different value): "
        f"the data's freshness -- max(order_date) in fct_orders_net -- is "
        f"exactly {freshness}. Use this EXACT value for the 'Freshness' "
        f"field in every provenance footer. When computing any 'trailing N "
        f"days' window, that means from {freshness} minus N days through "
        f"{freshness}, and your footer's 'Window' field should reflect "
        f"that same end date.\n\n" + load_skill_context()
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]

    got_successful_result = False

    for turn in range(6):
        # Keep forcing a tool call until we've actually gotten one real,
        # non-error result back -- otherwise the model sometimes bails
        # into writing prose/SQL-as-text when it hits a query error,
        # instead of correcting the query and calling the tool again.
        tool_choice = "auto" if got_successful_result else "required"
        resp = call_with_retry(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice=tool_choice,
        )
        choice = resp.choices[0]

        if not choice.message.tool_calls:
            return choice.message.content or ""

        messages.append({
            "role": "assistant",
            "content": choice.message.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in choice.message.tool_calls
            ],
        })
        for tool_call in choice.message.tool_calls:
            args = json.loads(tool_call.function.arguments)
            result = run_sql(args["sql"])
            if '"error"' not in result:
                got_successful_result = True
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                }
            )

    return "Agent did not converge within the tool-use turn limit."


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "What was our net revenue over the trailing 30 days?"
    print(answer_question(q))