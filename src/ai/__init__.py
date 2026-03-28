"""
AI Package - Local LLM Integration via Ollama

Uses local Ollama models for market analysis instead of cloud APIs.
Primary: glm-4.7-flash (best reasoning)
Fallback: qwen3:14b (good local model)
"""

from .ollama_client import OllamaClient, get_ollama_client, analyze_market_with_ollama

__all__ = ["OllamaClient", "get_ollama_client", "analyze_market_with_ollama"]