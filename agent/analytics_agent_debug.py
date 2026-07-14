"""
Same as analytics_agent.py but with debug printing so you can see, turn by
turn, whether the model is actually calling run_sql or just narrating text.
"""
import json
import os
import sys
import time

import duckdb
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
)


def call_with_retry(**kwargs):
    """NVIDIA's free tier occasionally returns a transient 'DEGRADED
    function cannot be invoked' error on an otherwise-valid request. Retry
    a few times with a short backoff before giving up."""
    last_err = None
    for attempt in range(4):
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as e:
            last_err = e
            if "DEGRADED" in str(e) or "500" in str(e):
                wait = 2 ** attempt
                print(f"  (transient error, retrying in {wait}s: {e})")
                time.sleep(wait)
                continue
            raise  # not a transient error, don't retry
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
    system_prompt = (
        "You are an e-commerce analytics agent. Follow these skill "
        "instructions exactly, including the mandatory provenance footer "
        "format at the end of every answer. You MUST use the run_sql tool "
        "to get real numbers before answering -- never write out a query "
        "as text without executing it.\n\n" + load_skill_context()
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]

    for turn in range(6):
        print(f"\n--- turn {turn} ---")
        # Force a tool call on the first turn -- smaller models sometimes
        # drift into writing prose/code instead of actually invoking the
        # function, even when nothing else is wrong with the request.
        tool_choice = "required" if turn == 0 else "auto"
        resp = call_with_retry(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice=tool_choice,
        )
        choice = resp.choices[0]
        print("finish_reason:", choice.finish_reason)
        print("content:", repr(choice.message.content)[:300])
        print("tool_calls:", choice.message.tool_calls)

        if not choice.message.tool_calls:
            return choice.message.content or ""

        # Build a minimal assistant message -- NVIDIA's backend rejects the
        # extra None fields (audio, refusal, function_call, annotations)
        # that OpenAI's SDK includes if you dump the whole message object.
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
            print("EXECUTING SQL:", args["sql"])
            result = run_sql(args["sql"])
            print("RESULT:", result[:300])
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