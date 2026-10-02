import json
from functools import lru_cache
from pathlib import Path

from core.config import KB_PATH
from core.knowledge.schemas import KnowledgeBase


@lru_cache
def load_knowledge_base(path: Path = KB_PATH) -> KnowledgeBase:
    """Load and validate the seed knowledge base (cached; restart the server after editing it)."""
    with open(path, encoding="utf-8") as f:
        return KnowledgeBase.model_validate(json.load(f))
