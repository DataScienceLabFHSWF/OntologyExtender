"""LangChain-based Ollama provider — chat, embeddings, and tool binding.

Ported from GraphQAAgent ``LangChainOllamaProvider``.  Uses
``langchain-ollama`` for both ``ChatOllama`` (generation / tool-calling)
and ``OllamaEmbeddings`` (vector operations).
"""

from __future__ import annotations

from typing import Any

import structlog
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.embeddings import Embeddings

from ontology_hitl.core.config import Settings

logger = structlog.get_logger(__name__)


class OllamaConnector:
    """LangChain-based Ollama provider for chat + embeddings.

    Wraps :class:`ChatOllama` for LLM generation (including tool-calling) and
    :class:`OllamaEmbeddings` for vector operations.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

        self.chat_model: BaseChatModel = ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_url,
            temperature=settings.llm_temperature,
            num_ctx=4096,
            num_predict=2048,
        )

        self.embeddings: Embeddings = OllamaEmbeddings(
            model=settings.ollama_embedding_model,
            base_url=settings.ollama_url,
        )

        logger.info(
            "ollama.init",
            model=settings.ollama_model,
            embedding_model=settings.ollama_embedding_model,
            base_url=settings.ollama_url,
        )

    # -- lifecycle ----------------------------------------------------------

    async def connect(self) -> None:
        """Verify connectivity by sending a lightweight request."""
        try:
            await self.chat_model.ainvoke("ping")
            logger.info("ollama.connected", base_url=self._settings.ollama_url)
        except Exception as exc:
            logger.error("ollama.connect_failed", error=str(exc))
            raise

    async def close(self) -> None:
        logger.info("ollama.closed")

    # -- generation ---------------------------------------------------------

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate text from a prompt."""
        try:
            response = await self.chat_model.ainvoke(prompt)
            return response.content
        except Exception as exc:
            logger.error("ollama.generate_error", error=str(exc))
            return f"Error: {exc}"

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """Chat-style generation with message history."""
        from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

        lc_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                lc_messages.append(SystemMessage(content=content))
            elif role == "assistant":
                lc_messages.append(AIMessage(content=content))
            else:
                lc_messages.append(HumanMessage(content=content))

        try:
            response = await self.chat_model.ainvoke(lc_messages)
            return response.content
        except Exception as exc:
            logger.error("ollama.chat_error", error=str(exc))
            return f"Error: {exc}"

    # -- embeddings ---------------------------------------------------------

    async def embed(self, text: str) -> list[float]:
        """Embed a single text string."""
        try:
            return await self.embeddings.aembed_query(text)
        except Exception as exc:
            logger.error("ollama.embed_error", error=str(exc))
            return []

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts in one call."""
        try:
            return await self.embeddings.aembed_documents(texts)
        except Exception as exc:
            logger.error("ollama.embed_batch_error", error=str(exc))
            return [[] for _ in texts]

    # -- LangChain accessors ------------------------------------------------

    def get_chat_model(self) -> BaseChatModel:
        """Return the LangChain chat model (for tool binding, chains, etc.)."""
        return self.chat_model

    def get_embeddings(self) -> Embeddings:
        """Return the LangChain embeddings model."""
        return self.embeddings
