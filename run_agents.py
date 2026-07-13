"""Quick-start script to run RAG pipeline agents.

Run from project root:
    python run_agents.py              # Run all demos
    python run_agents.py ask          # Test the ask pipeline
    python run_agents.py ingest       # Test document ingestion
    python run_agents.py quick        # Quick single-agent test
    python run_agents.py config       # Show current configuration

Requires:
    - AWS credentials configured (aws configure)
    - Model access enabled in Bedrock console for us-east-1
"""

from __future__ import annotations

import os
import sys

# Set defaults if not already configured
os.environ.setdefault("RAG_AGENT_REGION", "us-east-1")
os.environ.setdefault("RAG_AGENT_TIER", "lite")
os.environ.setdefault("RAG_AGENT_TEMPERATURE", "0.1")
os.environ.setdefault("RAG_AGENT_MAX_TOKENS", "4096")


def show_config():
    """Display current agent configuration."""
    from src.agents.base import (
        AGENT_TIER_DEFAULTS,
        BEDROCK_MODEL_TIERS,
        get_config_for_agent,
    )

    print("=" * 60)
    print("RAG Pipeline Agents — Current Configuration")
    print("=" * 60)
    print()
    print(f"  Region:      {os.environ.get('RAG_AGENT_REGION', 'us-east-1')}")
    print(f"  Global Tier: {os.environ.get('RAG_AGENT_TIER', 'lite')}")
    print(f"  Temperature: {os.environ.get('RAG_AGENT_TEMPERATURE', '0.1')}")
    print(f"  Max Tokens:  {os.environ.get('RAG_AGENT_MAX_TOKENS', '4096')}")
    print()
    print("  Model Tiers Available:")
    for tier, model_id in BEDROCK_MODEL_TIERS.items():
        print(f"    {tier.value:8s} → {model_id}")
    print()
    print("  Agent → Model Mapping (current):")
    for agent_role, default_tier in AGENT_TIER_DEFAULTS.items():
        cfg = get_config_for_agent(agent_role)
        print(f"    {agent_role:25s} → {cfg.model_id} ({cfg.tier.value})")
    print()
    print("  Cost Estimates (per 1M tokens, input/output):")
    print("    lite    : $0.06 / $0.24   (Amazon Nova Lite)")
    print("    pro     : $0.80 / $3.20   (Amazon Nova Pro)")
    print("    premium : $3.00 / $15.00  (Claude Sonnet 4)")
    print()


def quick_test():
    """Quick test: single agent call to verify everything works."""
    from strands import Agent
    from strands.models import BedrockModel

    from src.agents.base import get_default_config

    config = get_default_config()

    print("=" * 60)
    print("Quick Test — Single Agent Call")
    print("=" * 60)
    print(f"\n  Model: {config.model_id}")
    print(f"  Region: {config.region_name}")
    print(f"  Tier: {config.tier.value}")
    print("\n  Sending: 'What is 2 + 2? Answer in one word.'\n")

    model = BedrockModel(
        model_id=config.model_id,
        region_name=config.region_name,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
    )
    agent = Agent(model=model)
    response = agent("What is 2 + 2? Answer in one word.")
    print(f"  Response: {response}")
    print("\n  ✅ Agent is working!\n")


def test_ask():
    """Test the full ask pipeline with mock ports."""
    from src.agents.demo import demo_ask

    demo_ask()


def test_ingest():
    """Test the ingestion pipeline with mock ports."""
    from src.agents.demo import demo_ingest

    demo_ingest()


def run_all():
    """Run all demo scenarios."""
    show_config()
    print("\n" + "=" * 60)
    print("Running Quick Test...")
    print("=" * 60 + "\n")
    quick_test()


def main():
    """Entry point."""
    commands = {
        "config": show_config,
        "quick": quick_test,
        "ask": test_ask,
        "ingest": test_ingest,
    }

    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd in commands:
            commands[cmd]()
        elif cmd in ("help", "--help", "-h"):
            print(__doc__)
        else:
            print(f"Unknown command: {cmd}")
            print(f"Available: {', '.join(commands.keys())}")
            sys.exit(1)
    else:
        run_all()


if __name__ == "__main__":
    main()
