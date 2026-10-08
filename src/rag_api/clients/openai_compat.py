"""Chat and embedding clients for any OpenAI-compatible server (Ollama, vLLM, TEI).

Which server answers is decided by `LLM_BASE_URL` / `EMBED_BASE_URL` alone.
"""

from collections.abc import AsyncIterator, Sequence
from typing import cast

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from rag_api.clients.protocols import ChatMessage
from rag_api.settings import Settings


def _as_params(messages: Sequence[ChatMessage]) -> list[ChatCompletionMessageParam]:
    return cast(
        "list[ChatCompletionMessageParam]",
        [{"role": m.role, "content": m.content} for m in messages],
    )


class OpenAIChat:
    def __init__(self, settings: Settings) -> None:
        self._client = AsyncOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            timeout=settings.llm_timeout_s,
            max_retries=0,
        )
        self._model = settings.llm_model
        self._temperature = settings.llm_temperature
        self._max_tokens = settings.llm_max_tokens

    async def stream(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=_as_params(messages),
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            stream=True,
        )
        async for event in response:
            if event.choices and event.choices[0].delta.content:
                yield event.choices[0].delta.content

    async def complete(self, messages: Sequence[ChatMessage]) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=_as_params(messages),
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        return response.choices[0].message.content or ""

    async def ping(self) -> str:
        listing = await self._client.models.list()
        ids = {model.id for model in listing.data}
        if self._model not in ids:
            raise RuntimeError(f"model {self._model!r} not served; available: {sorted(ids)}")
        return f"serving {self._model}"


class OpenAIEmbedder:
    def __init__(self, settings: Settings) -> None:
        self._client = AsyncOpenAI(
            base_url=settings.embed_base_url,
            api_key=settings.embed_api_key,
            timeout=settings.llm_timeout_s,
            max_retries=0,
        )
        self._model = settings.embed_model
        self._batch = settings.embed_batch_size

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch):
            batch = list(texts[start : start + self._batch])
            response = await self._client.embeddings.create(model=self._model, input=batch)
            ordered = sorted(response.data, key=lambda item: item.index)
            vectors.extend(item.embedding for item in ordered)
        return vectors

    async def ping(self) -> str:
        vectors = await self.embed(["ping"])
        return f"{self._model} returns {len(vectors[0])}-dim vectors"
