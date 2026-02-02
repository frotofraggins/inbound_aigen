"""
AI-powered ticker inference using AWS Bedrock
Identifies affected stocks from news text using Claude
"""
import boto3
import json
from typing import List, Dict, Optional

class TickerInferenceClient:
    """
    Uses AWS Bedrock (Claude) to infer which stocks are affected by news.
    Handles cases where ticker symbols aren't explicitly mentioned.
    """
    
    def __init__(self, model_id: str = "anthropic.claude-3-haiku-20240307-v1:0", region: str = "us-west-2"):
        """
        Initialize Bedrock client.
        
        Args:
            model_id: Bedrock model ID (Haiku for cost, Sonnet for quality)
            region: AWS region
        """
        self.bedrock = boto3.client('bedrock-runtime', region_name=region)
        self.model_id = model_id
    
    def infer_tickers(
        self,
        title: str,
        summary: Optional[str],
        ticker_universe: List[str]
    ) -> List[str]:
        """
        Use Claude to infer which tickers are affected by news.
        
        Args:
            title: News headline
            summary: News summary (may be None)
            ticker_universe: List of valid ticker symbols
            
        Returns:
            List of ticker symbols (filtered for confidence > 0.5)
        """
        
        # Construct prompt
        prompt = f"""You are a financial analyst identifying which stocks are affected by news.

News Headline: {title}
News Summary: {summary or 'N/A'}

Available Stocks: {', '.join(ticker_universe)}

Task: Identify which stocks from the available list are affected by this news.

Consider:
- Direct mentions (company names, products)
- Sector/industry impact (e.g., AI news affects NVDA, semiconductor news affects multiple)
- Economic/policy impact (e.g., tariffs affect importers like AAPL)
- Competitive dynamics (e.g., pharma breakthroughs affect competitors)

For each affected stock, provide:
1. ticker: Symbol from available list (REQUIRED)
2. impact: "direct" | "sector" | "indirect" (REQUIRED)
3. confidence: 0.0-1.0 (REQUIRED)
4. reason: Brief explanation (OPTIONAL)

Return JSON array. Example:
[
  {{"ticker": "NVDA", "impact": "sector", "confidence": 0.8, "reason": "AI chip demand"}},
  {{"ticker": "AAPL", "impact": "indirect", "confidence": 0.6, "reason": "Tariff exposure"}}
]

Only include stocks with confidence > 0.5.
Return [] if no clear connection to available stocks.

JSON Response:"""
        
        try:
            # Call Bedrock
            response = self.bedrock.invoke_model(
                modelId=self.model_id,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 500,
                    "temperature": 0.3,  # Lower for more consistent output
                    "messages": [{
                        "role": "user",
                        "content": prompt
                    }]
                })
            )
            
            # Parse response
            result = json.loads(response['body'].read())
            content = result['content'][0]['text']
            
            # Extract JSON from response
            # Claude may return: ```json\n[...]\n``` or just [...]
            content = content.strip()
            if content.startswith('```'):
                # Remove markdown code fences
                lines = content.split('\n')
                content = '\n'.join(lines[1:-1]) if len(lines) > 2 else lines[0]
            
            # Parse JSON array
            inferences = json.loads(content)
            
            # Filter and validate
            valid_tickers = []
            for inf in inferences:
                ticker = inf.get('ticker')
                confidence = inf.get('confidence', 0.0)
                
                # Validate
                if ticker and ticker in ticker_universe and confidence > 0.5:
                    valid_tickers.append(ticker)
            
            return sorted(list(set(valid_tickers)))  # Deduplicate
            
        except json.JSONDecodeError as e:
            # Log parsing error but don't fail
            print(f"AI inference JSON parse error: {e}")
            print(f"Response: {content[:200]}")
            return []
            
        except Exception as e:
            # Log Bedrock error but don't fail
            print(f"AI inference error: {type(e).__name__}: {e}")
            return []
    
    def infer_with_fallback(
        self,
        title: str,
        summary: Optional[str],
        ticker_universe: List[str],
        timeout_seconds: int = 3
    ) -> List[str]:
        """
        Infer tickers with timeout and fallback to empty list.
        
        Args:
            title: News headline
            summary: News summary
            ticker_universe: Valid tickers
            timeout_seconds: Max time to wait for Bedrock
            
        Returns:
            List of inferred tickers or [] if timeout/error
        """
        import signal as sig
        
        def timeout_handler(signum, frame):
            raise TimeoutError("Bedrock inference timeout")
        
        try:
            # Set timeout
            sig.signal(sig.SIGALRM, timeout_handler)
            sig.alarm(timeout_seconds)
            
            # Try inference
            result = self.infer_tickers(title, summary, ticker_universe)
            
            # Clear timeout
            sig.alarm(0)
            
            return result
            
        except TimeoutError:
            print(f"AI inference timeout after {timeout_seconds}s")
            return []
        except Exception as e:
            print(f"AI inference fallback error: {e}")
            return []
        finally:
            sig.alarm(0)
