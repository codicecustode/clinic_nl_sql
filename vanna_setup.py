import os
import logging
from dotenv import load_dotenv

from vanna import Agent, AgentConfig
from vanna.core.registry import ToolRegistry
from vanna.core.user import UserResolver, User, RequestContext
from vanna.tools import RunSqlTool, VisualizeDataTool
from vanna.tools.agent_memory import SaveQuestionToolArgsTool, SearchSavedCorrectToolUsesTool, SaveTextMemoryTool
from vanna.integrations.sqlite import SqliteRunner
from vanna.integrations.local.agent_memory import DemoAgentMemory
from vanna.core.system_prompt.default import DefaultSystemPromptBuilder

load_dotenv()
log = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "clinic.db")

# ── Provider configs ──────────────────────────────────────────────────────────
PROVIDERS = {
    "gemini": {
        "label": "Google Gemini",
        "key_env": "GOOGLE_API_KEY",
        "model_env": "GEMINI_MODEL",
        "default_model": "gemini-2.5-flash",
        "type": "gemini",
    },
    "groq": {
        "label": "Groq",
        "key_env": "GROQ_API_KEY",
        "model_env": "GROQ_MODEL",
        "default_model": "llama-3.3-70b-versatile",
        "type": "openai",
        "base_url": "https://api.groq.com/openai/v1",
    },
    "nvidia": {
        "label": "NVIDIA",
        "key_env": "NVIDIA_API_KEY",
        "model_env": "NVIDIA_MODEL",
        "default_model": "deepseek-ai/deepseek-v4.1-flash",
        "type": "openai",
        "base_url": "https://integrate.api.nvidia.com/v1",
    },
    "ollama": {
        "label": "Ollama",
        "key_env": None,
        "model_env": "OLLAMA_MODEL",
        "default_model": "llama3",
        "type": "openai",
        "base_url": "http://localhost:11434/v1",
    },
}


def _build_llm_service(provider_id: str):
    """Create a Vanna LLM service for a provider. Returns None if the key isn't set."""
    config = PROVIDERS[provider_id]
    api_key = os.getenv(config["key_env"], "").strip() if config["key_env"] else "ollama"
    if not api_key:
        return None
    model = os.getenv(config["model_env"], config["default_model"])

    if config["type"] == "gemini":
        from vanna.integrations.google import GeminiLlmService
        return GeminiLlmService(model=model, api_key=api_key)
    else:
        from vanna.integrations.openai import OpenAILlmService
        return OpenAILlmService(model=model, api_key=api_key, base_url=config["base_url"])


# ── Shared resources (tools, memory, prompt) ──────────────────────────────────
SCHEMA_PROMPT = """
You are a SQL expert assistant for a clinic management database (SQLite).

DATABASE SCHEMA:

TABLE: patients
  id INTEGER PRIMARY KEY
  first_name TEXT NOT NULL
  last_name TEXT NOT NULL
  email TEXT (nullable)
  phone TEXT (nullable)
  date_of_birth DATE
  gender TEXT  -- values: 'M' or 'F'
  city TEXT
  registered_date DATE

TABLE: doctors
  id INTEGER PRIMARY KEY
  name TEXT NOT NULL
  specialization TEXT  -- values: Dermatology, Cardiology, Orthopedics, General, Pediatrics
  department TEXT
  phone TEXT

TABLE: appointments
  id INTEGER PRIMARY KEY
  patient_id INTEGER REFERENCES patients(id)
  doctor_id INTEGER REFERENCES doctors(id)
  appointment_date DATETIME
  status TEXT  -- values: Scheduled, Completed, Cancelled, No-Show
  notes TEXT (nullable)

TABLE: treatments
  id INTEGER PRIMARY KEY
  appointment_id INTEGER REFERENCES appointments(id)
  treatment_name TEXT
  cost REAL
  duration_minutes INTEGER

TABLE: invoices
  id INTEGER PRIMARY KEY
  patient_id INTEGER REFERENCES patients(id)
  invoice_date DATE
  total_amount REAL
  paid_amount REAL
  status TEXT  -- values: Paid, Pending, Overdue

RULES:
- ALWAYS write SELECT-only queries.
- Use strftime('%Y-%m', date_column) for monthly grouping in SQLite.
- Use date('now', '-N months') for date filtering.
- For date of birth age calculation use: (strftime('%Y', 'now') - strftime('%Y', date_of_birth)).
- Never query sqlite_master or system tables.
- Always use proper JOINs with correct foreign keys as shown above.
"""

system_prompt_builder = DefaultSystemPromptBuilder(base_prompt=SCHEMA_PROMPT)
sql_runner = SqliteRunner(database_path=DB_PATH)
db_tool = RunSqlTool(sql_runner=sql_runner)
agent_memory = DemoAgentMemory(max_items=1000)


class SimpleUserResolver(UserResolver):
    async def resolve_user(self, request_context: RequestContext) -> User:
        email = request_context.get_cookie("vanna_email") or "guest@clinic.local"
        group = "admin" if email == os.getenv("ADMIN_EMAIL", "admin@clinic.local") else "user"
        return User(id=email, email=email, group_memberships=[group])


user_resolver = SimpleUserResolver()

tools = ToolRegistry()
tools.register_local_tool(db_tool,                          access_groups=["admin", "user"])
tools.register_local_tool(VisualizeDataTool(),              access_groups=["admin", "user"])
tools.register_local_tool(SaveQuestionToolArgsTool(),       access_groups=["admin"])
tools.register_local_tool(SearchSavedCorrectToolUsesTool(), access_groups=["admin", "user"])
tools.register_local_tool(SaveTextMemoryTool(),             access_groups=["admin", "user"])


# ── Build one agent per available provider ────────────────────────────────────
agents: dict[str, Agent] = {}
primary_provider: str | None = None

# Preferred order: gemini first (most generous free tier), then groq, nvidia, ollama
for pid in ["gemini", "groq", "nvidia", "ollama"]:
    llm = _build_llm_service(pid)
    if llm is None:
        continue
    agents[pid] = Agent(
        llm_service=llm,
        tool_registry=tools,
        user_resolver=user_resolver,
        agent_memory=agent_memory,
        config=AgentConfig(),
        system_prompt_builder=system_prompt_builder,
    )
    if primary_provider is None:
        primary_provider = pid
    log.info("Agent created for %s (%s)", PROVIDERS[pid]["label"], pid)

if not agents:
    raise RuntimeError("No LLM API keys found. Set at least one of: GOOGLE_API_KEY, GROQ_API_KEY, NVIDIA_API_KEY")

# The default agent (used when no fallback is needed)
agent = agents[primary_provider]
log.info("Primary agent: %s, total agents: %d", primary_provider, len(agents))


def get_available_providers() -> list[dict]:
    """List providers for /models endpoint."""
    return [
        {"id": pid, "label": PROVIDERS[pid]["label"], "available": pid in agents, "primary": pid == primary_provider}
        for pid in PROVIDERS if pid != "ollama"
    ]


def get_agent(provider: str | None = None) -> tuple[Agent, str]:
    """Get the agent for a provider, or the primary one."""
    if provider and provider in agents:
        return agents[provider], provider
    return agents[primary_provider], primary_provider


def get_fallback_agent(failed_provider: str) -> tuple[Agent, str] | None:
    """Get the next available agent after one fails."""
    for pid, ag in agents.items():
        if pid != failed_provider:
            log.info("Falling back from %s to %s", failed_provider, pid)
            return ag, pid
    return None
