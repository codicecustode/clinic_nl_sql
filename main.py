import json
import os
import re
import sqlite3
import logging
import time
import uuid
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.io as pio
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from vanna.core.user import RequestContext
from vanna.tools.run_sql import DataFrameComponent

from vanna_setup import agent, agent_memory, get_agent, get_fallback_agent, get_available_providers, agents

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "clinic.db")

# FastAPI app
app = FastAPI(
    title="Clinic NL2SQL API",
    description="Natural Language to SQL powered by Vanna 2.0",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cache
_cache: dict[str, Any] = {}
_cache_ttl: dict[str, float] = {}
CACHE_TTL_SECONDS = 300


def cache_get(key: str):
    if key in _cache and time.time() - _cache_ttl[key] < CACHE_TTL_SECONDS:
        return _cache[key]
    return None


def cache_set(key: str, value):
    _cache[key] = value
    _cache_ttl[key] = time.time()


# Rate limiting
_rate_window: dict[str, list[float]] = {}
RATE_LIMIT = 30
RATE_WINDOW = 60.0


def check_rate_limit(ip: str) -> bool:
    now = time.time()
    hits = [t for t in _rate_window.get(ip, []) if now - t < RATE_WINDOW]
    if len(hits) >= RATE_LIMIT:
        return False
    hits.append(now)
    _rate_window[ip] = hits
    return True


# SQL validation
_DANGEROUS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|EXEC|EXECUTE"
    r"|xp_|sp_|GRANT|REVOKE|SHUTDOWN|ATTACH|DETACH|PRAGMA)\b",
    re.IGNORECASE,
)
_SYSTEM_TABLES = re.compile(
    r"\b(sqlite_master|sqlite_temp_master|sqlite_sequence|information_schema)\b",
    re.IGNORECASE,
)


def validate_sql(sql: str) -> tuple[bool, str]:
    s = sql.strip().lstrip(";").strip()
    if not s.upper().startswith("SELECT"):
        return False, "Only SELECT queries are permitted."
    if _DANGEROUS.search(s):
        return False, "Query contains a forbidden keyword."
    if _SYSTEM_TABLES.search(s):
        return False, "Query must not access system tables."
    return True, "ok"


# Chart helper
def maybe_generate_chart(columns: list, rows: list) -> tuple[dict | None, str | None]:
    if not rows or len(columns) < 2:
        return None, None
    try:
        df = pd.DataFrame(rows, columns=columns)
        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        text_cols = df.select_dtypes(exclude="number").columns.tolist()
        if not numeric_cols:
            return None, None
        x_col = text_cols[0] if text_cols else columns[0]
        y_col = numeric_cols[0]
        if len(df) <= 20:
            fig = px.bar(df, x=x_col, y=y_col, title=f"{y_col} by {x_col}")
            chart_type = "bar"
        else:
            fig = px.line(df, x=x_col, y=y_col, title=f"{y_col} over {x_col}")
            chart_type = "line"
        return json.loads(pio.to_json(fig)), chart_type
    except Exception:
        return None, None


# Parse Vanna UiComponent chunks
def parse_chunks(chunks: list) -> dict:
    """
    Walk all UiComponent chunks emitted by agent.send_message().
    - DataFrameComponent  → extract rows, columns, row_count
    - RichTextComponent   → extract content text (for SQL if code_language='sql')
    - SimpleTextComponent → extract summary text
    Returns a dict with keys: text, sql, columns, rows, row_count
    """
    result = {"text": "", "sql": None, "columns": [], "rows": [], "row_count": 0}

    for chunk in chunks:
        rc = getattr(chunk, "rich_component", None)
        sc = getattr(chunk, "simple_component", None)

        if rc is not None:
            # DataFrameComponent — this is what RunSqlTool emits
            if isinstance(rc, DataFrameComponent):
                if rc.rows and rc.columns:
                    result["columns"] = rc.columns
                    # rows is a list of dicts — convert to list of lists
                    result["rows"] = [[row.get(c) for c in rc.columns] for row in rc.rows]
                    result["row_count"] = rc.row_count or len(result["rows"])

            # RichTextComponent — may contain SQL (code_language='sql') or summary text
            elif hasattr(rc, "content") and rc.content:
                lang = getattr(rc, "code_language", None)
                if lang and lang.lower() == "sql":
                    result["sql"] = rc.content.strip()
                else:
                    result["text"] += rc.content

        if sc is not None and hasattr(sc, "text") and sc.text:
            result["text"] += sc.text

    # Fallback: try to extract SQL from text if not found as a code block
    if not result["sql"] and result["text"]:
        sql_match = re.search(r"```sql\s*(.*?)\s*```", result["text"], re.DOTALL | re.IGNORECASE)
        if sql_match:
            result["sql"] = sql_match.group(1).strip()
        else:
            sel_match = re.search(r"(SELECT[\s\S]+?;)", result["text"], re.IGNORECASE)
            if sel_match:
                result["sql"] = sel_match.group(1).strip()

    return result


# Pydantic models
class ChatRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)


class ChatResponse(BaseModel):
    message: str
    sql_query: str | None = None
    columns: list[str] = []
    rows: list[list] = []
    row_count: int = 0
    chart: dict | None = None
    chart_type: str | None = None
    cached: bool = False



# /models endpoint
@app.get("/models", tags=["Models"])
async def list_models():
    return {"providers": get_available_providers()}


# /chat endpoint
@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(request: Request, body: ChatRequest):
    client_ip = request.client.host or "unknown"

    if not check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded.")

    question = body.question.strip()
    log.info(f"[chat] question={question!r}")

    cache_key = question.lower()
    cached_resp = cache_get(cache_key)
    if cached_resp:
        cached_resp["cached"] = True
        return ChatResponse(**cached_resp)

    # Call Vanna Agent with fallback
    current_agent, provider_used = get_agent()
    req_context = RequestContext()
    conv_id = f"chat-{uuid.uuid4().hex[:8]}"

    try:
        all_chunks = []
        async for chunk in current_agent.send_message(req_context, question, conversation_id=conv_id):
            all_chunks.append(chunk)
        parsed = parse_chunks(all_chunks)
        log.info(f"[chat] parsed ({provider_used}): sql={bool(parsed['sql'])}, rows={parsed['row_count']}")

    except Exception as exc:
        log.warning(f"[chat] {provider_used} failed: {exc}, trying fallback...")
        fallback = get_fallback_agent(provider_used)
        if fallback is None:
            return ChatResponse(message=f"All providers failed. Last error: {exc}")
        current_agent, provider_used = fallback
        try:
            all_chunks = []
            async for chunk in current_agent.send_message(req_context, question, conversation_id=conv_id):
                all_chunks.append(chunk)
            parsed = parse_chunks(all_chunks)
            log.info(f"[chat] parsed ({provider_used} fallback): sql={bool(parsed['sql'])}, rows={parsed['row_count']}")
        except Exception as exc2:
            log.error(f"[chat] fallback also failed: {exc2}", exc_info=True)
            return ChatResponse(message=f"All providers failed. Error: {exc2}")

    #  Case 1: Agent returned data rows directly (RunSqlTool executed SQL)
    if parsed["rows"] and parsed["columns"]:
        columns = parsed["columns"]
        rows = parsed["rows"]
        row_count = parsed["row_count"] or len(rows)
        sql = parsed["sql"]

        chart, chart_type = maybe_generate_chart(columns, rows)
        summary = parsed["text"].strip() or (
            f"Found {row_count} row{'s' if row_count != 1 else ''} "
            f"with columns: {', '.join(columns)}."
        )

        resp_data = dict(
            message=summary,
            sql_query=sql,
            columns=columns,
            rows=rows,
            row_count=row_count,
            chart=chart,
            chart_type=chart_type,
            cached=False,
        )
        cache_set(cache_key, resp_data)
        log.info(f"[chat] success (agent ran SQL) — {row_count} rows")
        return ChatResponse(**resp_data)

    #  Case 2: Agent returned SQL but didn't execute (fallback: run ourselves)
    if parsed["sql"]:
        sql = parsed["sql"]
        valid, reason = validate_sql(sql)
        if not valid:
            log.warning(f"[chat] SQL blocked: {reason}")
            return ChatResponse(message=f"Query blocked: {reason}", sql_query=sql)

        try:
            con = sqlite3.connect(DB_PATH)
            df = pd.read_sql_query(sql, con)
            con.close()
        except Exception as exc:
            log.error(f"[chat] SQL execution error: {exc}")
            return ChatResponse(message=f"Query failed: {exc}", sql_query=sql)

        if df.empty:
            return ChatResponse(message="No data found.", sql_query=sql)

        columns = list(df.columns)
        rows = df.values.tolist()
        row_count = len(rows)
        chart, chart_type = maybe_generate_chart(columns, rows)
        summary = f"Found {row_count} row{'s' if row_count != 1 else ''} with columns: {', '.join(columns)}."

        resp_data = dict(
            message=summary,
            sql_query=sql,
            columns=columns,
            rows=rows,
            row_count=row_count,
            chart=chart,
            chart_type=chart_type,
            cached=False,
        )
        cache_set(cache_key, resp_data)
        log.info(f"[chat] success (fallback SQL run) — {row_count} rows")
        return ChatResponse(**resp_data)

    # Case 3: No data, just a text response
    return ChatResponse(message=parsed["text"] or "I couldn't answer that question.")


#  /health endpoint
@app.get("/health", tags=["Health"])
async def health():
    db_status = "disconnected"
    try:
        con = sqlite3.connect(DB_PATH)
        con.execute("SELECT 1")
        con.close()
        db_status = "connected"
    except Exception:
        pass

    memory_count = 0
    try:
        store = (
            getattr(agent_memory, "_tool_usage_store", None)
            or getattr(agent_memory, "_store", None)
            or getattr(agent_memory, "memories", None)
        )
        if store is not None:
            memory_count = len(store)
    except Exception:
        pass

    return {"status": "ok", "database": db_status, "agent_memory_items": memory_count}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
