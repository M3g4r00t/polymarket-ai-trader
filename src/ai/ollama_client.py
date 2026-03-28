"""
Ollama AI Client for Local LLM Integration

Uses local Ollama models for market analysis instead of cloud APIs.
"""

import asyncio
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import json
import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class OllamaModel:
    """Available Ollama model"""
    name: str
    size: str
    modified: str


class OllamaClient:
    """
    Client for Ollama local LLM API.
    
    Provides AI capabilities using local models instead of cloud APIs.
    Primary: glm-4.7-flash (best reasoning)
    Fallback: qwen3:14b (good local model)
    """
    
    OLLAMA_API = "http://localhost:11434"
    
    # Model priority (best first)
    MODEL_PRIORITY = [
        "glm-4.7-flash",    # Best reasoning, largest model
        "qwen3:14b",        # Good local fallback
        "llama3",           # Smaller alternative
    ]
    
    def __init__(
        self,
        preferred_model: Optional[str] = None,
        fallback_model: str = "qwen3:14b",
        temperature: float = 0.3,
        max_tokens: int = 500
    ):
        """
        Initialize Ollama client.
        
        Args:
            preferred_model: Model to use (None = auto-detect best)
            fallback_model: Fallback if preferred not available
            temperature: Temperature for generation
            max_tokens: Maximum tokens to generate
        """
        self.preferred_model = preferred_model
        self.fallback_model = fallback_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        self._available_models: List[OllamaModel] = []
        self._selected_model: Optional[str] = None
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def initialize(self) -> bool:
        """
        Initialize client and detect available models.
        
        Returns:
            True if at least one model is available
        """
        self._session = aiohttp.ClientSession()
        
        # Get available models
        try:
            async with self._session.get(f"{self.OLLAMA_API}/api/tags") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._available_models = [
                        OllamaModel(
                            name=m["name"],
                            size=m.get("size", "unknown"),
                            modified=m.get("modified_at", "unknown")
                        )
                        for m in data.get("models", [])
                    ]
                    logger.info(f"Found {len(self._available_models)} Ollama models: {[m.name for m in self._available_models]}")
                else:
                    logger.warning(f"Ollama API returned status {resp.status}")
        except aiohttp.ClientError as e:
            logger.error(f"Cannot connect to Ollama: {e}")
            return False
        
        # Select model
        self._selected_model = self._select_model()
        
        if self._selected_model:
            logger.info(f"Using Ollama model: {self._selected_model}")
            return True
        else:
            logger.error("No suitable Ollama model available")
            return False
    
    def _select_model(self) -> Optional[str]:
        """Select the best available model"""
        available_names = [m.name.split(":")[0] for m in self._available_models]
        
        # If preferred model specified, check if available
        if self.preferred_model:
            base_name = self.preferred_model.split(":")[0]
            for model in self._available_models:
                if model.name.startswith(base_name):
                    return model.name
        
        # Try priority order
        for model_name in self.MODEL_PRIORITY:
            for available in self._available_models:
                if available.name.startswith(model_name.split(":")[0]):
                    return available.name
        
        # Fallback to first available
        if self._available_models:
            return self._available_models[0].name
        
        return None
    
    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> Optional[str]:
        """
        Generate response from Ollama model.
        
        Args:
            prompt: Input prompt
            model: Model to use (None = selected model)
            temperature: Override temperature
            max_tokens: Override max tokens
            
        Returns:
            Generated text or None if failed
        """
        if not self._session:
            await self.initialize()
        
        model = model or self._selected_model
        if not model:
            logger.error("No model available")
            return None
        
        temperature = temperature if temperature is not None else self.temperature
        max_tokens = max_tokens if max_tokens is not None else self.max_tokens
        
        try:
            async with self._session.post(
                f"{self.OLLAMA_API}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens
                    }
                },
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("response", "")
                else:
                    logger.error(f"Ollama generate failed: {resp.status}")
                    return None
                    
        except asyncio.TimeoutError:
            logger.error("Ollama request timed out")
            return None
        except Exception as e:
            logger.error(f"Ollama generate error: {e}")
            return None
    
    async def analyze_market(
        self,
        question: str,
        description: str,
        category: str,
        current_price: float,
        news_context: str = ""
    ) -> Dict[str, Any]:
        """
        Analyze a prediction market and estimate probability.
        
        Args:
            question: Market question
            description: Market description
            category: Market category
            current_price: Current market price (0-1)
            news_context: Optional news context
            
        Returns:
            Dict with probability, confidence, reasoning
        """
        prompt = f"""You are a prediction market analyst. Estimate the TRUE probability of this event occurring.

MARKET QUESTION:
{question}

MARKET DESCRIPTION:
{description or 'No additional description'}

CATEGORY:
{category}

CURRENT MARKET PRICE (YES):
{current_price:.1%}

{f'RECENT NEWS CONTEXT:{chr(10)}{news_context}' if news_context else ''}

Analyze this market and provide your estimate of the TRUE probability.
Consider:
1. Base rates for similar events
2. Historical patterns
3. Current news and context (if provided)
4. Potential biases in the market
5. Resolution criteria and timeline

Respond ONLY with valid JSON in this exact format:
{{
    "probability": 0.XX,
    "confidence": "low" or "medium" or "high",
    "reasoning": "Brief explanation of your estimate",
    "key_factors": ["factor1", "factor2", "factor3"]
}}

Your probability should be a number between 0 and 1.
Your confidence reflects how certain you are about your estimate.
Be objective and consider all perspectives."""

        response = await self.generate(prompt, temperature=0.2)
        
        if not response:
            return {
                "probability": current_price,
                "confidence": "low",
                "reasoning": "Failed to get AI analysis",
                "key_factors": []
            }
        
        # Parse JSON from response
        try:
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            
            if json_start == -1 or json_end == 0:
                logger.error("No JSON found in Ollama response")
                return {
                    "probability": current_price,
                    "confidence": "low",
                    "reasoning": response,
                    "key_factors": []
                }
            
            data = json.loads(response[json_start:json_end])
            
            # Validate probability
            prob = float(data.get('probability', current_price))
            prob = max(0.01, min(0.99, prob))
            
            return {
                "probability": prob,
                "confidence": data.get('confidence', 'low'),
                "reasoning": data.get('reasoning', ''),
                "key_factors": data.get('key_factors', [])
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing Ollama response: {e}")
            return {
                "probability": current_price,
                "confidence": "low",
                "reasoning": response,
                "key_factors": []
            }
    
    async def close(self):
        """Close the client session"""
        if self._session:
            await self._session.close()
    
    @property
    def model_name(self) -> str:
        """Get the currently selected model name"""
        return self._selected_model or "none"


# Singleton instance for global use
_ollama_client: Optional[OllamaClient] = None


async def get_ollama_client() -> OllamaClient:
    """Get or create the global Ollama client"""
    global _ollama_client
    
    if _ollama_client is None:
        _ollama_client = OllamaClient()
        await _ollama_client.initialize()
    
    return _ollama_client


async def analyze_market_with_ollama(
    question: str,
    description: str,
    category: str,
    current_price: float,
    news_context: str = ""
) -> Dict[str, Any]:
    """
    Convenience function to analyze a market using Ollama.
    
    Args:
        question: Market question
        description: Market description
        category: Market category
        current_price: Current market price (0-1)
        news_context: Optional news context
        
    Returns:
        Dict with probability, confidence, reasoning
    """
    client = await get_ollama_client()
    return await client.analyze_market(
        question=question,
        description=description,
        category=category,
        current_price=current_price,
        news_context=news_context
    )