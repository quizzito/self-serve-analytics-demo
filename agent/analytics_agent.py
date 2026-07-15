"""
Analytics agent using NVIDIA Build's free OpenAI-compatible endpoint.
Requires: pip install openai duckdb
          export NVIDIA_API_KEY=...
Run: python3 agent/analytics_agent.py "What was our net revenue over the trailing 30 days?"

Key design choice: the model is NOT trusted to write its own provenance
footer. It kept fabricating dates there even when told not to. Instead,
every run_sql call is logged during execution, and the footer is built in
code from that real trace after the model finishes -- so the footer can
no longer say anything that didn't actually happen.

The model is also required to end its answer with a strict
"FINAL_ANSWER: <value>" line, so evals/run_evals.py can grade numeric
answers with plain Python instead of a second LLM call.
"""
import json
import os
import re
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
    trusting the model to query and correctly report it."""
    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        result = con.execute("select max(order_date) from fct_orders_net").fetchone()
        return str(result[0])
    finally:
        con.close()


def strip_model_footer(text: str) -> str:
    """Remove any provenance-footer-looking lines the model wrote itself,
    since those are being replaced with a code-generated one built from the
    real execution trace. Matches blockquote lines starting with common
    footer field names."""
    footer_line = re.compile(
        r"^\s*>?\s*\*\*(Source|Window|Freshness|Confidence|Metric)", re.IGNORECASE
    )
    lines = [ln for ln in text.split("\n") if not footer_line.match(ln)]
    return "\n".join(lines).rstrip()


def build_provenance_footer(execution_log: list, freshness: str) -> str:
    """Built entirely from what actually happened during this run, not from
    anything the model claims. This is the fix for fabricated metadata:
    the footer can only say things that are true, because it's generated
    from the real execution trace, not recalled from the model's memory."""
    successful = [e for e in execution_log if e["success"]]
    n_attempts = len(execution_log)

    if not successful:
        return (
            f"\n\n> **Source:** no successful query executed · "
            f"**Queries attempted:** {n_attempts} · "
            f"**Freshness:** {freshness} · **Confidence:** low"
        )

    last_sql = successful[-1]["sql"]
    tables = sorted(set(
        m.lower() for m in re.findall(r"(?:from|join)\s+([a-zA-Z_][\w]*)", last_sql, re.IGNORECASE)
    ))
    tables_str = ", ".join(tables) if tables else "unknown"
    is_governed = all(t.startswith(("fct_", "dim_")) for t in tables) if tables else False
    layer = "canonical mart" if is_governed else "raw/staging (ungoverned, verify manually)"
    confidence = "high" if is_governed else "medium"

    sql_preview = last_sql.strip().replace("\n", " ")
    if len(sql_preview) > 160:
        sql_preview = sql_preview[:160] + "..."

    return (
        f"\n\n> **Source:** {layer} ({tables_str}) · "
        f"**Query executed:** `{sql_preview}` · "
        f"**Freshness:** {freshness} · **Confidence:** {confidence}"
    )


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
                "For 'trailing N days' windows, always use strict "
                "greater-than (>), never >=, against max(order_date) minus "
                "the interval. Using >= silently includes one extra day "
                "and will produce a slightly wrong answer, especially for "
                "ratio metrics like average order value. "
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
    execution_log = []

    system_prompt = (
        "You are an e-commerce analytics agent. You MUST use the run_sql "
        "tool to get real numbers before answering -- never write out a "
        "query as text without executing it. If a query errors, fix the "
        "SQL and call run_sql again -- do not give up and describe the fix "
        "as text instead of actually running it.\n\n"
        f"KNOWN FACT: the data's freshness (max order_date) is exactly "
        f"{freshness}. When computing any 'trailing N days' window, that "
        f"means from {freshness} minus N days through {freshness}.\n\n"
        "IMPORTANT OUTPUT FORMAT: do NOT write your own provenance footer "
        "or source/confidence metadata -- that is generated automatically "
        "after your answer. Just give a clear one or two sentence answer. "
        "Then, on its own final line, output exactly:\n"
        "FINAL_ANSWER: <the number or short value only, no dollar signs, "
        "no commas, no extra words -- e.g. FINAL_ANSWER: 12816.83 or "
        "FINAL_ANSWER: 2026-07-01>\n\n" + load_skill_context()
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]

    got_successful_result = False

    for turn in range(6):
        tool_choice = "auto" if got_successful_result else "required"
        resp = call_with_retry(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice=tool_choice,
        )
        choice = resp.choices[0]

        if not choice.message.tool_calls:
            final_text = strip_model_footer(choice.message.content or "")
            footer = build_provenance_footer(execution_log, freshness)
            return final_text + footer

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
            success = '"error"' not in result
            execution_log.append({"sql": args["sql"], "success": success})
            if success:
                got_successful_result = True
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                }
            )

    footer = build_provenance_footer(execution_log, freshness)
    return "Agent did not converge within the tool-use turn limit." + footer


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "What was our net revenue over the trailing 30 days?"
    print(answer_question(q))