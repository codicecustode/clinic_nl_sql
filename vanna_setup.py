import os
import sqlite3
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

DB_PATH = os.getenv("DB_PATH", "clinic.db")

#  LLM Service
_llm_choice = os.getenv("LLM_PROVIDER", "gemini").lower()

if _llm_choice == "gemini":
    from vanna.integrations.google import GeminiLlmService
    llm_service = GeminiLlmService(
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        api_key=os.getenv("GOOGLE_API_KEY"),
    )
elif _llm_choice == "groq":
    from vanna.integrations.openai import OpenAILlmService
    llm_service = OpenAILlmService(
        model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        api_key=os.getenv("GROQ_API_KEY"),
        base_url="https://api.groq.com/openai/v1",
    )
elif _llm_choice == "ollama":
    from vanna.integrations.openai import OpenAILlmService
    llm_service = OpenAILlmService(
        model=os.getenv("OLLAMA_MODEL", "llama3"),
        api_key="ollama",
        base_url="http://localhost:11434/v1",
    )
else:
    raise ValueError(f"Unknown LLM_PROVIDER '{_llm_choice}'. Choose: gemini | groq | ollama")

#  Database schema system prompt 
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

#  Database runner 
sql_runner = SqliteRunner(database_path=DB_PATH)
db_tool = RunSqlTool(sql_runner=sql_runner)

#  Agent memory 
agent_memory = DemoAgentMemory(max_items=1000)

#  User resolver 
class SimpleUserResolver(UserResolver):
    async def resolve_user(self, request_context: RequestContext) -> User:
        email = request_context.get_cookie("vanna_email") or "guest@clinic.local"
        group = "admin" if email == os.getenv("ADMIN_EMAIL", "admin@clinic.local") else "user"
        return User(id=email, email=email, group_memberships=[group])

user_resolver = SimpleUserResolver()

#  Tool registry 
tools = ToolRegistry()
tools.register_local_tool(db_tool,                          access_groups=["admin", "user"])
tools.register_local_tool(VisualizeDataTool(),              access_groups=["admin", "user"])
tools.register_local_tool(SaveQuestionToolArgsTool(),       access_groups=["admin"])
tools.register_local_tool(SearchSavedCorrectToolUsesTool(), access_groups=["admin", "user"])
tools.register_local_tool(SaveTextMemoryTool(),             access_groups=["admin", "user"])

#  Agent 
agent = Agent(
    llm_service=llm_service,
    tool_registry=tools,
    user_resolver=user_resolver,
    agent_memory=agent_memory,
    config=AgentConfig(),
    system_prompt_builder=system_prompt_builder,
)
