---
inclusion: auto
---

# Strands Agents Integration Guide

## Agent Architecture

The RAG pipeline uses Strands Agents (Amazon Bedrock) for intelligent orchestration
of LLM-dependent tasks. Agents are organized by domain concern.

## Agent Registry

| Agent | Location | Tier | Role |
|-------|----------|------|------|
| Retrieval Agent | `src/agents/retrieval_agent.py` | lite | Hybrid search orchestration |
| Generation Agent | `src/agents/generation_agent.py` | pro | Grounded answer production |
| Citation Verification Agent | `src/agents/citation_verification_agent.py` | lite | Faithfulness validation |
| Ingestion Agent | `src/agents/ingestion_agent.py` | lite | Document processing pipeline |
| Evaluation Agent | `src/agents/evaluation_agent.py` | pro | Quality benchmarking |
| Orchestrator | `src/agents/orchestrator.py` | — | Coordinates all agents |

## Model Tier Configuration

```
lite    = us.amazon.nova-lite-v1:0    ($0.06/$0.24 per 1M tokens)
pro     = us.amazon.nova-pro-v1:0     ($0.80/$3.20 per 1M tokens)
premium = us.anthropic.claude-sonnet-4 ($3.00/$15.00 per 1M tokens)
```

Environment variables:
- `RAG_AGENT_REGION=us-east-1`
- `RAG_AGENT_TIER=lite` (global default)
- `RAG_GENERATION_TIER=pro` (per-agent override)

## Tool Design Pattern

Every agent tool follows this structure:

```python
@tool
def tool_name(param1: str, param2: int = 10) -> str:
    """One-line description of what this tool does.

    Longer explanation of when and how the agent should use this tool.

    Args:
        param1: Description of parameter.
        param2: Description with default noted.
    """
    import asyncio

    async def _run() -> dict:
        # Call port interface
        result = await some_port.operation(param1)
        return {"key": "value", "success": True}

    result = asyncio.run(_run())
    return str(result)
```

Rules:
1. Tools return `str` (JSON-serialized dicts) — agents work with text
2. Async port calls wrapped in `asyncio.run()` inside the tool
3. Tools are closures over injected port instances
4. Error handling returns structured error dict, never raises
5. Limit output size — truncate text previews to 500 chars

## Integration with Domain Services

Domain services can delegate to agents OR be called by agents:

```python
# Option A: Service delegates to agent (recommended for LLM-heavy logic)
class GenerationService:
    def __init__(self, generation_agent: Agent):
        self._agent = generation_agent

    async def generate(self, query: str, context: list[ScoredChunk]) -> GenerationResult:
        response = self._agent(f"Generate answer for: {query}\nContext: {context}")
        return self._parse_response(response)

# Option B: Agent calls service via tool (for deterministic logic)
@tool
def validate_document(document_id: str) -> str:
    """Validate document format and size."""
    result = security_service.validate_filename(filename)
    ...
```

## Testing Agents

- Unit tests mock the model — test tool logic independently
- Integration tests use real Bedrock calls with `@pytest.mark.integration`
- Never call Bedrock in CI unit tests — mock the Agent class
- Use the `MockEmbeddingPort`, `MockVectorStore` etc. from `src/agents/demo.py`

## Cost Control

- Development: Use `lite` tier for all agents (~$0.06/1M tokens)
- Testing: Use `lite` tier, limit queries to 10 per test run
- Production: Use `pro` for generation/evaluation, `lite` for others
- Set `RAG_AGENT_MAX_TOKENS=2048` during development to limit cost
- Monitor via token tracking in observability layer
