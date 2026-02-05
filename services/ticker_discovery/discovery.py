"""
Ticker Discovery Service
Uses AWS Bedrock (Claude Sonnet) to analyze market and recommend tickers for trading
"""
import boto3
import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import psycopg2
from psycopg2.extras import RealDictCursor

class TickerDiscovery:
    """
    AI-powered ticker discovery using Bedrock Sonnet.
    Analyzes market data, news, volume trends to recommend 25-50 tickers.
    """
    
    def __init__(self):
        """Initialize clients and configuration"""
        self.bedrock = boto3.client('bedrock-runtime', region_name='us-west-2')
        self.ssm = boto3.client('ssm', region_name='us-west-2')
        self.secrets = boto3.client('secretsmanager', region_name='us-west-2')
        self.model_id = "anthropic.claude-3-5-sonnet-20241022-v2:0"
        
        # Load database configuration from SSM and Secrets Manager
        self._load_config()
    
    def _load_config(self):
        """Load configuration from AWS services (SSM + Secrets Manager)"""
        # Database configuration from SSM
        self.db_host = self.ssm.get_parameter(Name='/ops-pipeline/db_host')['Parameter']['Value']
        self.db_port = self.ssm.get_parameter(Name='/ops-pipeline/db_port')['Parameter']['Value']
        self.db_name = self.ssm.get_parameter(Name='/ops-pipeline/db_name')['Parameter']['Value']
        
        # Database credentials from Secrets Manager
        secret_value = self.secrets.get_secret_value(SecretId='ops-pipeline/db')
        secret_data = json.loads(secret_value['SecretString'])
        self.db_user = secret_data['username']
        self.db_password = secret_data['password']
    
    def get_db_connection(self):
        """Create database connection"""
        return psycopg2.connect(
            host=self.db_host,
            database=self.db_name,
            user=self.db_user,
            password=self.db_password,
            cursor_factory=RealDictCursor
        )
    
    def get_market_context(self) -> Dict:
        """
        Gather market context for AI analysis.
        Returns data about recent news, volume surges, active tickers.
        """
        conn = self.get_db_connection()
        cur = conn.cursor()
        
        # Get recent news clusters (last 24h)
        # Note: tickers is an array, so we unnest it
        cur.execute("""
            SELECT 
                UNNEST(tickers) as ticker,
                COUNT(*) as mention_count,
                AVG(sentiment_score) as avg_sentiment,
                STRING_AGG(DISTINCT ier.title, ' | ' ORDER BY ier.title) as headlines
            FROM inbound_events_classified iec
            JOIN inbound_events_raw ier ON ier.id = iec.raw_event_id
            WHERE 
                iec.created_at > NOW() - INTERVAL '24 hours'
                AND tickers IS NOT NULL
                AND array_length(tickers, 1) > 0
            GROUP BY UNNEST(tickers)
            ORDER BY mention_count DESC
            LIMIT 50
        """)
        news_clusters = cur.fetchall()
        
        # Get volume surges (last 24h)
        cur.execute("""
            SELECT 
                ticker,
                MAX(volume_ratio) as max_volume_ratio,
                AVG(volume_ratio) as avg_volume_ratio,
                COUNT(*) as surge_count
            FROM lane_features_clean
            WHERE 
                ts > NOW() - INTERVAL '24 hours'
                AND volume_ratio > 2.0
            GROUP BY ticker
            ORDER BY max_volume_ratio DESC
            LIMIT 50
        """)
        volume_surges = cur.fetchall()
        
        # Get currently tracked tickers with their performance
        cur.execute("""
            SELECT 
                ticker,
                COUNT(*) as bar_count,
                MAX(close) as high_price,
                MIN(close) as low_price,
                AVG(volume_ratio) as avg_volume
            FROM lane_features_clean
            WHERE ts > NOW() - INTERVAL '7 days'
            GROUP BY ticker
            ORDER BY bar_count DESC
            LIMIT 100
        """)
        current_tickers = cur.fetchall()
        
        cur.close()
        conn.close()
        
        return {
            'news_clusters': [dict(row) for row in news_clusters],
            'volume_surges': [dict(row) for row in volume_surges],
            'current_tickers': [dict(row) for row in current_tickers],
            'analysis_time': datetime.now().isoformat()
        }
    
    def analyze_with_bedrock(self, market_context: Dict) -> List[Dict]:
        """
        Use Bedrock Sonnet to analyze market and recommend tickers.
        
        Returns:
            List of ticker recommendations with confidence scores
        """
        
        # Build prompt with market context
        prompt = f"""You are an expert day trading analyst. Analyze the current market data and recommend 35 stocks for intraday options trading.

MARKET CONTEXT (Last 24 hours):

Top News Mentions:
{self._format_news_clusters(market_context['news_clusters'][:10])}

Volume Surges:
{self._format_volume_surges(market_context['volume_surges'][:10])}

Current Portfolio Performance:
{self._format_current_tickers(market_context['current_tickers'][:15])}

SELECTION CRITERIA:
- Market cap >$5B (liquid, institutional interest)
- Daily volume >500K shares (sufficient liquidity)
- Has 0-7 DTE weekly options (required for day trading)
- Price >$20 (meaningful option premiums)
- Current catalyst (news, volume, technical breakout)

CONSIDER:
1. News momentum (which stories are driving volume?)
2. Volume leaders (sustained >2x average volume)
3. Sector rotation (AI, semiconductors, financials, healthcare trending?)
4. Earnings calendar (this week's reporters get extra activity)
5. Technical setups (new highs, support bounces, breakouts)
6. Options liquidity (must have active 0-7 DTE market)

DIVERSIFICATION:
- Include mix of sectors (don't overweight tech)
- Include value rotation opportunities
- Include defensive plays if market volatile
- Balance growth vs value vs cyclicals

OUTPUT FORMAT:
Return JSON array of 35 recommendations. Each must have:
{{
  "ticker": "SYMBOL",
  "sector": "Technology|Healthcare|Financials|Energy|Consumer|Industrial",
  "catalyst": "Brief reason why tradeable today",
  "confidence": 0.0-1.0,
  "expected_volume": "high|medium|normal"
}}

Requirements:
- Must be 35 tickers exactly
- Confidence scores should span 0.6-0.95 (realistic range)
- Higher confidence for strong catalysts + volume
- Lower confidence for sector rotation plays
- Only include stocks you're confident meet ALL criteria above

JSON Array Response:"""

        try:
            # Call Bedrock Sonnet
            response = self.bedrock.invoke_model(
                modelId=self.model_id,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 4000,
                    "temperature": 0.5,  # Moderate creativity for discovery
                    "messages": [{
                        "role": "user",
                        "content": prompt
                    }]
                })
            )
            
            # Parse response
            result = json.loads(response['body'].read())
            content = result['content'][0]['text']
            
            # Log raw response for debugging
            print(f"Response length: {len(content)} characters")
            print(f"Response type: {'array' if content.strip().startswith('[') else 'object' if content.strip().startswith('{') else 'other'}")
            print(f"First 2000 chars:\n{content[:2000]}")
            
            # Extract JSON (may have markdown fences)
            content = content.strip()
            if content.startswith('```'):
                lines = content.split('\n')
                # Remove first and last lines (```)
                content = '\n'.join(lines[1:-1]) if len(lines) > 2 else content
                # Remove 'json' marker if present
                if content.startswith('json'):
                    content = content[4:].strip()
            
            print(f"After fence removal, starts with: {content[:50]}")
            
            # Parse JSON - handle both array and object responses
            parsed = json.loads(content)
            
            # If Bedrock returned object with "recommendations" key, extract array
            if isinstance(parsed, dict):
                print(f"Got dictionary with keys: {list(parsed.keys())}")
                if 'recommendations' in parsed:
                    recommendations = parsed['recommendations']
                    print(f"Extracted {len(recommendations)} from 'recommendations' key")
                elif 'tickers' in parsed:
                    recommendations = parsed['tickers']
                    print(f"Extracted {len(recommendations)} from 'tickers' key")
                else:
                    print(f"ERROR: Object has no 'recommendations' or 'tickers' key")
                    print(f"Full object: {json.dumps(parsed, indent=2)[:500]}")
                    recommendations = []
            else:
                recommendations = parsed
                print(f"Got array directly with {len(recommendations)} items")
            
            # Validate and filter
            valid_recs = []
            for rec in recommendations:
                if all(k in rec for k in ['ticker', 'sector', 'catalyst', 'confidence']):
                    # Ensure confidence is numeric
                    rec['confidence'] = float(rec['confidence'])
                    if 0.5 <= rec['confidence'] <= 1.0:
                        valid_recs.append(rec)
            
            return valid_recs
            
        except json.JSONDecodeError as e:
            print(f"JSON parse error: {e}")
            print(f"Response: {content[:500]}")
            raise
        except Exception as e:
            print(f"Bedrock error: {type(e).__name__}: {e}")
            raise
    
    def _format_news_clusters(self, clusters: List[Dict]) -> str:
        """Format news clusters for prompt"""
        if not clusters:
            return "No significant news clusters detected"
        
        lines = []
        for c in clusters:
            sentiment = "bullish" if c['avg_sentiment'] > 0.1 else "bearish" if c['avg_sentiment'] < -0.1 else "neutral"
            lines.append(f"  {c['ticker']}: {c['mention_count']} mentions, {sentiment} sentiment")
        return '\n'.join(lines)
    
    def _format_volume_surges(self, surges: List[Dict]) -> str:
        """Format volume surges for prompt"""
        if not surges:
            return "No significant volume surges detected"
        
        lines = []
        for s in surges:
            lines.append(f"  {s['ticker']}: {float(s['max_volume_ratio']):.2f}x surge, {s['surge_count']} occurrences")
        return '\n'.join(lines)
    
    def _format_current_tickers(self, tickers: List[Dict]) -> str:
        """Format current ticker performance for prompt"""
        if not tickers:
            return "No performance data available"
        
        lines = []
        for t in tickers:
            price_range = f"${float(t['low_price']):.2f}-${float(t['high_price']):.2f}"
            lines.append(f"  {t['ticker']}: {t['bar_count']} bars, {price_range}, {float(t['avg_volume']):.2f}x avg volume")
        return '\n'.join(lines)
    
    def store_recommendations(self, recommendations: List[Dict]):
        """
        Store recommendations in ticker_universe table.
        Marks old entries as inactive, inserts new ones.
        """
        conn = self.get_db_connection()
        cur = conn.cursor()
        
        try:
            # Mark all existing as inactive
            cur.execute("UPDATE ticker_universe SET active = false")
            
            # Insert new recommendations
            for rec in recommendations:
                cur.execute("""
                    INSERT INTO ticker_universe 
                    (ticker, sector, catalyst, confidence, expected_volume, active)
                    VALUES (%s, %s, %s, %s, %s, true)
                    ON CONFLICT (ticker) 
                    DO UPDATE SET
                        sector = EXCLUDED.sector,
                        catalyst = EXCLUDED.catalyst,
                        confidence = EXCLUDED.confidence,
                        expected_volume = EXCLUDED.expected_volume,
                        last_updated = NOW(),
                        active = true
                """, (
                    rec['ticker'],
                    rec['sector'],
                    rec['catalyst'],
                    rec['confidence'],
                    rec.get('expected_volume', 'normal')
                ))
            
            conn.commit()
            print(f"Stored {len(recommendations)} ticker recommendations")
            
        except Exception as e:
            conn.rollback()
            print(f"Database error storing recommendations: {e}")
            raise
        finally:
            cur.close()
            conn.close()
    
    def update_ssm_parameter(self, recommendations: List[Dict]):
        """
        Update SSM parameters with top 25-30 tickers.
        Other services will auto-pickup changes.
        
        Updates BOTH:
        - /ops-pipeline/tickers (used by telemetry service)
        - /ops-pipeline/universe_tickers (used by watchlist engine)
        """
        # Sort by confidence, take top 28
        sorted_recs = sorted(recommendations, key=lambda x: x['confidence'], reverse=True)
        top_tickers = [r['ticker'] for r in sorted_recs[:28]]
        
        # Update SSM parameters
        ticker_list = ','.join(top_tickers)
        
        # Update telemetry ticker list
        self.ssm.put_parameter(
            Name='/ops-pipeline/tickers',
            Value=ticker_list,
            Overwrite=True,
            Type='String'
        )
        
        # Update watchlist universe ticker list (MUST match telemetry list)
        self.ssm.put_parameter(
            Name='/ops-pipeline/universe_tickers',
            Value=ticker_list,
            Overwrite=True,
            Type='String'
        )
        
        print(f"Updated SSM parameters with {len(top_tickers)} tickers: {ticker_list}")
        
        return top_tickers
    
    def run(self) -> Dict:
        """
        Main execution: Analyze market, get recommendations, update DB and SSM.
        
        Returns:
            Summary of execution
        """
        print("=== Ticker Discovery Starting ===")
        start_time = datetime.now()
        
        # 1. Gather market context
        print("Gathering market context...")
        market_context = self.get_market_context()
        print(f"  - {len(market_context['news_clusters'])} news clusters")
        print(f"  - {len(market_context['volume_surges'])} volume surges")
        print(f"  - {len(market_context['current_tickers'])} tracked tickers")
        
        # 2. Analyze with Bedrock
        print("Analyzing with Bedrock Sonnet...")
        recommendations = self.analyze_with_bedrock(market_context)
        print(f"  - Got {len(recommendations)} recommendations")
        
        # 3. Store in database
        print("Storing recommendations...")
        self.store_recommendations(recommendations)
        
        # 4. Update SSM parameter
        print("Updating SSM parameter...")
        active_tickers = self.update_ssm_parameter(recommendations)
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        summary = {
            'success': True,
            'timestamp': datetime.now().isoformat(),
            'recommendations_count': len(recommendations),
            'active_tickers_count': len(active_tickers),
            'active_tickers': active_tickers,
            'elapsed_seconds': elapsed,
            'top_recommendations': sorted(recommendations, key=lambda x: x['confidence'], reverse=True)[:10]
        }
        
        print(f"=== Ticker Discovery Complete ({elapsed:.1f}s) ===")
        print(f"Active tickers: {', '.join(active_tickers[:10])}...")
        
        return summary


def lambda_handler(event, context):
    """AWS Lambda handler"""
    try:
        discovery = TickerDiscovery()
        result = discovery.run()
        
        return {
            'statusCode': 200,
            'body': json.dumps(result, default=str)
        }
        
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'success': False,
                'error': str(e),
                'error_type': type(e).__name__
            })
        }


if __name__ == '__main__':
    # For local testing
    result = TickerDiscovery().run()
    print(json.dumps(result, indent=2, default=str))
