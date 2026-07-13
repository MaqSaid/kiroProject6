"""Simple Strands Agent Example.

This agent uses community tools (calculator, python_repl, http_request)
and can answer questions using those capabilities.

Prerequisites:
  pip install strands-agents strands-agents-tools

  Set one of these environment variables based on your provider:
    - AWS_BEDROCK_API_KEY (or configure AWS credentials via `aws configure`)
    - ANTHROPIC_API_KEY
    - OPENAI_API_KEY
    - GOOGLE_API_KEY
    - LLAMA_API_KEY

Usage:
  python agent.py
"""

from strands import Agent
from strands_tools import calculator, http_request, python_repl

# --- Choose your model provider (uncomment one) ---

# Option 1: Amazon Bedrock (default - no model= needed)
agent = Agent(
    tools=[calculator, python_repl, http_request],
    system_prompt="You are a helpful assistant skilled in math, coding, and web research.",
)

# Option 2: Anthropic
# from strands.models.anthropic import AnthropicModel
# import os
# model = AnthropicModel(
#     client_args={"api_key": os.environ["ANTHROPIC_API_KEY"]},
#     model_id="claude-sonnet-4-20250514",
#     max_tokens=2048,
# )
# agent = Agent(model=model, tools=[calculator, python_repl, http_request],
#               system_prompt="You are a helpful assistant.")

# Option 3: OpenAI
# from strands.models.openai import OpenAIModel
# import os
# model = OpenAIModel(
#     client_args={"api_key": os.environ["OPENAI_API_KEY"]},
#     model_id="gpt-5-mini",
# )
# agent = Agent(model=model, tools=[calculator, python_repl, http_request],
#               system_prompt="You are a helpful assistant.")

# --- Run the agent ---
if __name__ == "__main__":
    print("🤖 Strands Agent Ready! Ask me anything (Ctrl+C to quit)\n")

    # Single question example
    response = agent("What is 42 * 17 + 99?")
    print(f"\nAgent response: {response}\n")

    # Multi-turn conversation (agent remembers context)
    agent("My name is Saram.")
    response = agent("What's my name?")
    print(f"Agent remembers: {response}")
