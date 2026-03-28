"""
Mispricing Detection Strategy

Uses AI/LLM to estimate true probabilities and identify mispriced markets.
"""

import asyncio
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import json

from ..client import Market, OrderBook, OrderSide

logger = logging.getLogger(__name__)


class Confidence(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class MarketAssessment:
    """AI assessment of a market"""
    market: Market
    current_price: float
    estimated_probability: float
    confidence: Confidence
    reasoning: str
    key_factors: List[str]
    deviation: float  # Difference between market and estimated probability
    is_mispriced: bool
    
    def __str__(self):
        direction = "OVERVALUED" if self.estimated_probability < self.current_price else "UNDERVALUED"
        return (
            f"MarketAssessment({direction}, "
            f"market={self.current_price:.1%}, "
            f"estimated={self.estimated_probability:.1%}, "
            f"deviation={abs(self.deviation):.1%}, "
            f"confidence={self.confidence.value})"
        )


@dataclass
class MispricingOpportunity:
    """Represents a mispricing trading opportunity"""
    assessment: MarketAssessment
    direction: OrderSide  # BUY if undervalued, SELL if overvalued
    token_id: str
    expected_profit_pct: float
    liquidity: float
    timestamp: datetime


class MispricingStrategy:
    """
    Mispricing Detection Strategy
    
    Uses LLM/AI to:
    1. Analyze market question and context
    2. Estimate true probability
    3. Compare with market price
    4. Trade when significant deviation exists
    
    Risk: Higher than arbitrage (model may be wrong)
    Reward: Higher potential returns
    """
    
    def __init__(
        self,
        min_deviation_pct: float = 0.10,
        min_confidence: Confidence = Confidence.MEDIUM,
        max_markets_per_cycle: int = 5,
        ai_model: str = "gpt-4o-mini",
        max_api_calls_per_day: int = 100,
        news_enabled: bool = False
    ):
        """
        Initialize mispricing strategy.
        
        Args:
            min_deviation_pct: Minimum price deviation to act on (default 10%)
            min_confidence: Minimum confidence required (default MEDIUM)
            max_markets_per_cycle: Max markets to analyze per cycle (default 5)
            ai_model: AI model to use for analysis
            max_api_calls_per_day: Budget for AI API calls
            news_enabled: Whether to fetch news context (requires more API calls)
        """
        self.min_deviation_pct = min_deviation_pct
        self.min_confidence = min_confidence
        self.max_markets_per_cycle = max_markets_per_cycle
        self.ai_model = ai_model
        self.max_api_calls_per_day = max_api_calls_per_day
        self.news_enabled = news_enabled
        
        # API call tracking
        self._api_calls_today = 0
        self._last_reset = datetime.now().date()
        
        # AI client (lazy loaded)
        self._ai_client = None
        
    async def analyze_market(
        self,
        market: Market,
        news_context: str = ""
    ) -> Optional[MarketAssessment]:
        """
        Analyze a market using AI to estimate true probability.
        
        Uses Ollama for local LLM inference (no API costs).
        
        Args:
            market: The market to analyze
            news_context: Optional news context for the market
            
        Returns:
            MarketAssessment or None if analysis failed
        """
        # Check API budget
        if not self._check_api_budget():
            logger.warning("Analysis budget exceeded for today")
            return None
        
        # Use Ollama for local analysis
        if self.use_ollama:
            return await self._analyze_with_ollama(market, news_context)
        else:
            return await self._analyze_with_cloud(market, news_context)
    
    async def _analyze_with_ollama(
        self,
        market: Market,
        news_context: str = ""
    ) -> Optional[MarketAssessment]:
        """Analyze market using local Ollama model"""
        from ..ai.ollama_client import get_ollama_client
        
        try:
            # Get or create Ollama client
            if self._ollama_client is None:
                self._ollama_client = await get_ollama_client()
            
            # Analyze using Ollama
            result = await self._ollama_client.analyze_market(
                question=market.question,
                description=market.description or "",
                category=market.category,
                current_price=market.prices.get("YES", 0.5),
                news_context=news_context
            )
            
            # Increment counter
            self._api_calls_today += 1
            
            # Build assessment
            confidence_map = {
                'low': Confidence.LOW,
                'medium': Confidence.MEDIUM,
                'high': Confidence.HIGH
            }
            
            current_price = market.prices.get("YES", 0.5)
            estimated_prob = float(result.get('probability', current_price))
            deviation = estimated_prob - current_price
            
            return MarketAssessment(
                market=market,
                current_price=current_price,
                estimated_probability=estimated_prob,
                confidence=confidence_map.get(result.get('confidence', 'low').lower(), Confidence.LOW),
                reasoning=result.get('reasoning', ''),
                key_factors=result.get('key_factors', []),
                deviation=deviation,
                is_mispriced=abs(deviation) >= self.min_deviation_pct
            )
            
        except Exception as e:
            logger.error(f"Error analyzing market with Ollama {market.condition_id}: {e}")
            return None
    
    async def _analyze_with_cloud(
        self,
        market: Market,
        news_context: str = ""
    ) -> Optional[MarketAssessment]:
        """Analyze market using cloud API (OpenAI/Anthropic) - legacy method"""
        # Lazy load AI client
        if self._ai_client is None:
            self._ai_client = self._get_ai_client()
            if self._ai_client is None:
                logger.warning("AI client not available")
                return None
        
        # Build prompt
        prompt = self._build_analysis_prompt(market, news_context)
        
        try:
            # Call AI
            response = await self._call_ai(prompt)
            
            # Parse response
            assessment = self._parse_ai_response(market, response)
            
            # Increment API call counter
            self._api_calls_today += 1
            
            return assessment
            
        except Exception as e:
            logger.error(f"Error analyzing market {market.condition_id}: {e}")
            return None
    
    async def scan_markets(
        self,
        markets: List[Market],
        client
    ) -> List[MispricingOpportunity]:
        """
        Scan markets for mispricing opportunities.
        
        Args:
            markets: List of markets to analyze
            client: PolymarketClient instance
            
        Returns:
            List of mispricing opportunities
        """
        opportunities = []
        
        # Limit markets per cycle
        markets_to_analyze = markets[:self.max_markets_per_cycle]
        
        for market in markets_to_analyze:
            # Get current price
            yes_token = market.tokens.get("YES")
            if not yes_token:
                continue
            
            try:
                # Get order book for current price
                book = await client.get_order_book(yes_token)
                current_price = book.midpoint
                
                # Analyze with AI
                assessment = await self.analyze_market(market)
                
                if assessment and assessment.is_mispriced:
                    # Check confidence threshold
                    confidence_levels = {
                        Confidence.LOW: 1,
                        Confidence.MEDIUM: 2,
                        Confidence.HIGH: 3
                    }
                    
                    if confidence_levels[assessment.confidence] >= confidence_levels[self.min_confidence]:
                        # Determine direction
                        if assessment.estimated_probability > current_price:
                            # Undervalued - BUY YES
                            direction = OrderSide.BUY
                            expected_profit = assessment.estimated_probability - current_price
                        else:
                            # Overvalued - SELL YES (or BUY NO)
                            direction = OrderSide.SELL
                            expected_profit = current_price - assessment.estimated_probability
                        
                        opp = MispricingOpportunity(
                            assessment=assessment,
                            direction=direction,
                            token_id=yes_token,
                            expected_profit_pct=expected_profit,
                            liquidity=market.liquidity,
                            timestamp=datetime.now()
                        )
                        
                        opportunities.append(opp)
                        logger.info(f"Found mispricing: {opp}")
                        
            except Exception as e:
                logger.debug(f"Error scanning market {market.condition_id}: {e}")
                continue
        
        logger.info(f"Found {len(opportunities)} mispricing opportunities")
        return opportunities
    
    def _build_analysis_prompt(self, market: Market, news_context: str) -> str:
        """Build the prompt for AI analysis"""
        prompt = f"""You are a prediction market analyst. Estimate the TRUE probability of this event occurring.

MARKET QUESTION:
{market.question}

MARKET DESCRIPTION:
{market.description or 'No additional description'}

CATEGORY:
{market.category}

CURRENT MARKET PRICE (YES):
{market.prices.get('YES', 0.5):.2%}

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
"""
        return prompt
    
    def _parse_ai_response(self, market: Market, response: str) -> Optional[MarketAssessment]:
        """Parse AI response into MarketAssessment"""
        try:
            # Extract JSON from response
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            
            if json_start == -1 or json_end == 0:
                logger.error("No JSON found in AI response")
                return None
            
            json_str = response[json_start:json_end]
            data = json.loads(json_str)
            
            # Parse data
            estimated_prob = float(data.get('probability', 0.5))
            confidence_str = data.get('confidence', 'low').lower()
            reasoning = data.get('reasoning', '')
            key_factors = data.get('key_factors', [])
            
            # Validate probability
            estimated_prob = max(0.01, min(0.99, estimated_prob))
            
            # Map confidence
            confidence_map = {
                'low': Confidence.LOW,
                'medium': Confidence.MEDIUM,
                'high': Confidence.HIGH
            }
            confidence = confidence_map.get(confidence_str, Confidence.LOW)
            
            # Calculate deviation
            current_price = market.prices.get('YES', 0.5)
            deviation = estimated_prob - current_price
            
            # Check if mispriced
            is_mispriced = abs(deviation) >= self.min_deviation_pct
            
            return MarketAssessment(
                market=market,
                current_price=current_price,
                estimated_probability=estimated_prob,
                confidence=confidence,
                reasoning=reasoning,
                key_factors=key_factors,
                deviation=deviation,
                is_mispriced=is_mispriced
            )
            
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing AI response: {e}")
            return None
        except Exception as e:
            logger.error(f"Error processing AI response: {e}")
            return None
    
    async def _call_ai(self, prompt: str) -> str:
        """Make AI API call"""
        import os
        
        openai_key = os.getenv('OPENAI_API_KEY')
        anthropic_key = os.getenv('ANTHROPIC_API_KEY')
        
        if openai_key:
            return await self._call_openai(prompt, openai_key)
        elif anthropic_key:
            return await self._call_anthropic(prompt, anthropic_key)
        else:
            raise ValueError("No AI API key configured")
    
    async def _call_openai(self, prompt: str, api_key: str) -> str:
        """Call OpenAI API"""
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            data = {
                "model": self.ai_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 500
            }
            
            async with session.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=data
            ) as resp:
                result = await resp.json()
                return result['choices'][0]['message']['content']
    
    async def _call_anthropic(self, prompt: str, api_key: str) -> str:
        """Call Anthropic API"""
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            headers = {
                "x-api-key": api_key,
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01"
            }
            data = {
                "model": "claude-3-haiku-20240307",  # Use efficient model
                "max_tokens": 500,
                "messages": [{"role": "user", "content": prompt}]
            }
            
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=data
            ) as resp:
                result = await resp.json()
                return result['content'][0]['text']
    
    def _get_ai_client(self):
        """Get AI client (for future local model support)"""
        # Placeholder for local model integration
        return None
    
    def _check_api_budget(self) -> bool:
        """Check if we're within API call budget"""
        today = datetime.now().date()
        
        # Reset counter if new day
        if self._last_reset != today:
            self._api_calls_today = 0
            self._last_reset = today
        
        return self._api_calls_today < self.max_api_calls_per_day