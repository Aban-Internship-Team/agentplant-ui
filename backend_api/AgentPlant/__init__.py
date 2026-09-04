"""FastAPI package for AgentPlant (natural-language plant → dynamics).

HTTP surface for chat, drafts, and artifacts. Standalone in-memory conversation
store; no external product dependencies.
"""

from backend_api.AgentPlant.service import create_artifact, run_plant_model_chat
from backend_api.AgentPlant.router import router

__all__ = [
    "create_artifact",
    "run_plant_model_chat",
    "router",
]
