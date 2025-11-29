"""
LLM client for trading decisions.

COMPATIBILITY LAYER: This module re-exports from llm.client.
Please import from llm.client directly in new code.
"""
from llm.client import call_deepseek_api

__all__ = ["call_deepseek_api"]
