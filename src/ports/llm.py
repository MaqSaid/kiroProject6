from typing import Protocol

from pydantic import BaseModel


class Message(BaseModel):
    role: str
    content: str


class LLMResponse(BaseModel):
    content: str
    tokens_used: int
    model: str


class LLMPort(Protocol):
    async def generate(self, messages: list[Message], max_tokens: int) -> LLMResponse: ...
    async def generate_structured(
        self, messages: list[Message], schema: type[BaseModel]
    ) -> BaseModel: ...
