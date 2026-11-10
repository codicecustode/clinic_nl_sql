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
elif _llm_choice == "nvidia":
    from vanna.integrations.openai import OpenAILlmService
    llm_service = OpenAILlmService(
        model=os.getenv("NVIDIA_MODEL", "deepseek-ai/deepseek-v4.1-flash"),
        api_key=os.getenv("NVIDIA_API_KEY"),
        base_url="https://integrate.api.nvidia.com/v1",
    )
elif _llm_choice == "ollama":
    from vanna.integrations.openai import OpenAILlmService
    llm_service = OpenAILlmService(
        model=os.getenv("OLLAMA_MODEL", "llama3"),
        api_key="ollama",
        base_url="http://localhost:11434/v1",
    )
else:
    raise ValueError(f"Unknown LLM_PROVIDER '{_llm_choice}'. Choose: gemini | groq | nvidia | ollama")
