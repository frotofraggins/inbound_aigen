"""
Opportunity Analyzer Service
Nightly analysis of missed trading opportunities using Bedrock Sonnet
"""
import boto3
import json
import os
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from decimal import Decimal

class OpportunityAnalyzer:
    """
    Analyzes missed trading opportunities using AI.
    Identifies volume surges that were skipped and explains why.
    """
    
    def __init__(self):
        """Initialize clients and configuration"""
        self.bedrock = boto3.client('bedrock-runtime', region_name='us-west-2')
        self.ses = boto3.client('ses', region_name='us-west-2')
        self.model_id = "anthropic.claude-3-5-sonnet-20241022-v2:0"
        
        # Database connection
        self.db_host = os.environ['DB_HOST']
        self.db_name = os.environ['DB_NAME']
        self.db_user = os.environ['DB_USER']
        self.db_password = os.environ['DB_PASSWORD']
        
        # Email configuration
        self.email_from = os.environ.get('EMAIL_FROM', 'noreply@ops-pipeline.com')
        self.email_to = os.environ.get('EMAIL_TO', 'nsflournoy@gmail.com')
    
    def get_db_connection(self):
        """Create database connection"""
        return psycopg2.connect(
            host=self.db_host,
            database=self.db_name,
            user=self.db_user,
            password=self.db_password,
            cursor_factory=RealDictCursor
        )
    
    def get_missed_surges(self, analysis_date: date) -> List[Dict]:
        """
        Get volume surges from analysis_date that were NOT traded.
        
        Args:
            analysis_date: Date to analyze (typically today)
            
        Returns:
            List of missed surge opportunities
        """
        conn = self.get_db_connection()
        cur = conn.cursor()
        
        # Find significant volume surges that didn't result in trades
        cur.execute("""
            WITH surge_events AS (
                SELECT DISTINCT ON (lf.ticker, DATE_TRUNC('hour', lf.ts))
                    lf.ticker,
                    lf.ts,
                    lf.close_price,
                    lf.volume_ratio,
                    lf.sma_20,
                    lf.rsi_14,
                    lf.bb_position,
                    -- Get sentiment from news around this time
                    (
                        SELECT AVG(sentiment_score)
                        FROM inbound_events_classified
                        WHERE ticker = lf.ticker
                        AND created_at BETWEEN lf.ts - INTERVAL '2 hours' AND lf.ts + INTERVAL '1 hour'
                    ) as sentiment_score
                FROM lane_features_clean lf
                WHERE 
                    DATE(lf.ts AT TIME ZONE 'America/New_York') = %s
                    AND lf.volume_ratio >= 2.0
                ORDER BY lf.ticker, DATE_TRUNC('hour', lf.ts), lf.volume_ratio DESC
            ),
            traded_tickers AS (
                SELECT DISTINCT ticker
                FROM dispatch_executions
                WHERE DATE(created_at AT TIME ZONE 'America/New_York') = %s
            )
            SELECT 
                se.ticker,
                se.ts,
                se.close_price,
                se.volume_ratio,
                se.sma_20,
                se.rsi_14,
                se.bb_position,
                se.sentiment_score
            FROM surge_events se
            WHERE se.ticker NOT IN (SELECT ticker FROM traded_tickers)
            ORDER BY se.volume_ratio DESC
            LIMIT 20
        """, (analysis_date, analysis_date))
        
        missed = cur.fetchall()
        cur.close()
        conn.close()
        
        return [dict(row) for row in missed]
    
    def analyze_missed_opportunity(self, surge: Dict) -> Dict:
        """
        Use Bedrock to analyze why a surge was missed and if it was tradeable.
        
        Args:
            surge: Missed surge data
            
        Returns:
            AI analysis of the opportunity
        """
        
        # Build analysis prompt
        prompt = f"""You are a day trading analyst reviewing missed opportunities.

DETECTED BUT SKIPPED:
Ticker: {surge['ticker']}
Time: {surge['ts'].strftime('%I:%M %p ET')}
Volume Surge: {float(surge['volume_ratio']):.2f}x normal
Price: ${float(surge['close_price']):.2f}
SMA20: ${float(surge['sma_20']) if surge['sma_20'] else 'N/A'}
RSI: {float(surge['rsi_14']) if surge['rsi_14'] else 'N/A'}
Bollinger Band Position: {float(surge['bb_position']) if surge['bb_position'] else 'N/A'}
Sentiment Score: {float(surge['sentiment_score']) if surge['sentiment_score'] else 'neutral (0.0)'}

OUR TRADING RULES:
- Minimum volume ratio: 2.0x (✓ passed: {float(surge['volume_ratio']):.2f}x)
- Minimum sentiment magnitude: 0.10 absolute
- Confidence threshold: 0.55
- RSI not overbought/oversold (30-70 range)
- Must have clear technical setup

TASK: Analyze this missed opportunity.

Questions:
1. Was this a REAL trading opportunity or just noise?
   - Consider: volume spike reason, technical setup, sentiment context
   - Confidence: 0.0-1.0 (how certain it was tradeable)

2. If we HAD traded this, what would likely have happened?
   - Estimate profit/loss percentage
   - Consider: typical intraday move on this volume, technical resistance/support
   - Range: -5% to +5% realistic intraday

3. Should we have traded this? YES or NO
   - Consider: risk/reward, setup quality, consistency with strategy

4. Why was it skipped?
   - Identify exact rule that blocked it
   - Was rule correct or too strict?

5. Threshold adjustment needed?
   - If missed real opportunity: suggest parameter change
   - If correctly skipped: confirm current thresholds appropriate

Return JSON:
{{
  "real_opportunity": true|false,
  "opportunity_confidence": 0.0-1.0,
  "estimated_profit_pct": -5.0 to +5.0,
  "should_have_traded": true|false,
  "why_skipped": "specific rule explanation",
  "rule_assessment": "correct|too_strict|edge_case",
  "suggested_adjustment": "specific recommendation or 'none'",
  "reasoning": "brief explanation of analysis"
}}

JSON Response:"""

        try:
            # Call Bedrock
            response = self.bedrock.invoke_model(
                modelId=self.model_id,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 1000,
                    "temperature": 0.4,
                    "messages": [{
                        "role": "user",
                        "content": prompt
                    }]
                })
            )
            
            # Parse response
            result = json.loads(response['body'].read())
            content = result['content'][0]['text']
            
            # Extract JSON
            content = content.strip()
            if content.startswith('```'):
                lines = content.split('\n')
                content = '\n'.join(lines[1:-1]) if len(lines) > 2 else content
                if content.startswith('json'):
                    content = content[4:].strip()
            
            analysis = json.loads(content)
            return analysis
            
        except Exception as e:
            print(f"Bedrock analysis error for {surge['ticker']}: {e}")
            return {
                'real_opportunity': False,
                'opportunity_confidence': 0.0,
                'estimated_profit_pct': 0.0,
                'should_have_traded': False,
                'why_skipped': 'Analysis error',
                'rule_assessment': 'unknown',
                'suggested_adjustment': 'none',
                'reasoning': f'Error: {str(e)}'
            }
    
    def store_analysis(self, analysis_date: date, surge: Dict, analysis: Dict):
        """Store missed opportunity analysis in database"""
        conn = self.get_db_connection()
        cur = conn.cursor()
        
        try:
            cur.execute("""
                INSERT INTO missed_opportunities (
                    analysis_date, ticker, ts,
                    volume_ratio, close_price, sentiment_score,
                    why_skipped, rule_that_blocked,
                    real_opportunity, estimated_profit_pct,
                    should_have_traded, ai_reasoning, suggested_adjustment
                ) VALUES (
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, %s
                )
            """, (
                analysis_date,
                surge['ticker'],
                surge['ts'],
                surge['volume_ratio'],
                surge['close_price'],
                surge['sentiment_score'],
                analysis['why_skipped'],
                analysis.get('rule_assessment', 'unknown'),
                analysis['real_opportunity'],
                analysis['estimated_profit_pct'],
                analysis['should_have_traded'],
                analysis['reasoning'],
                analysis['suggested_adjustment']
            ))
            
            conn.commit()
            
        except Exception as e:
            conn.rollback()
            print(f"Database error storing analysis: {e}")
            raise
        finally:
            cur.close()
            conn.close()
    
    def generate_email_report(self, analysis_date: date, missed_surges: List[Dict], analyses: List[Dict]) -> str:
        """Generate HTML email report"""
        
        # Count should-have-traded
        should_trade_count = sum(1 for a in analyses if a['should_have_traded'])
        total_missed_profit = sum(a['estimated_profit_pct'] for a in analyses if a['should_have_traded'])
        
        # Build HTML
        html = f"""
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 20px; }}
        h1 {{ color: #2c3e50; }}
        h2 {{ color: #34495e; margin-top: 30px; }}
        .summary {{ background: #ecf0f1; padding: 15px; border-radius: 5px; margin: 20px 0; }}
        .opportunity {{ background: #fff; border: 1px solid #bdc3c7; padding: 15px; margin: 10px 0; border-radius: 5px; }}
        .should-trade {{ border-left: 4px solid #e74c3c; }}
        .correct-skip {{ border-left: 4px solid #2ecc71; }}
        .metric {{ display: inline-block; margin-right: 20px; }}
        .label {{ font-weight: bold; color: #7f8c8d; }}
        .recommendation {{ background: #fff3cd; padding: 10px; margin-top: 10px; border-radius: 3px; }}
    </style>
</head>
<body>
    <h1>Daily Trading Analysis - {analysis_date.strftime('%B %d, %Y')}</h1>
    
    <div class="summary">
        <h2>Summary</h2>
        <div class="metric">
            <span class="label">Total Surges Detected:</span> {len(missed_surges)}
        </div>
        <div class="metric">
            <span class="label">Should Have Traded:</span> {should_trade_count}
        </div>
        <div class="metric">
            <span class="label">Correctly Skipped:</span> {len(analyses) - should_trade_count}
        </div>
        <div class="metric">
            <span class="label">Potential Missed Profit:</span> {total_missed_profit:+.1f}%
        </div>
    </div>
    
    <h2>Missed Opportunities</h2>
"""
        
        # Add each opportunity
        for surge, analysis in zip(missed_surges, analyses):
            css_class = 'should-trade' if analysis['should_have_traded'] else 'correct-skip'
            status = '❌ MISSED' if analysis['should_have_traded'] else '✓ CORRECT SKIP'
            
            html += f"""
    <div class="opportunity {css_class}">
        <h3>{surge['ticker']} - {surge['ts'].strftime('%I:%M %p ET')} {status}</h3>
        
        <div class="metric">
            <span class="label">Volume Surge:</span> {float(surge['volume_ratio']):.2f}x
        </div>
        <div class="metric">
            <span class="label">Price:</span> ${float(surge['close_price']):.2f}
        </div>
        <div class="metric">
            <span class="label">Sentiment:</span> {float(surge['sentiment_score']) if surge['sentiment_score'] else 0.0:.2f}
        </div>
        
        <p><strong>Why Skipped:</strong> {analysis['why_skipped']}</p>
        <p><strong>AI Analysis:</strong> {analysis['reasoning']}</p>
        <p><strong>Estimated Outcome:</strong> {analysis['estimated_profit_pct']:+.1f}% if traded</p>
        
        {f'<div class="recommendation"><strong>Recommendation:</strong> {analysis["suggested_adjustment"]}</div>' if analysis['suggested_adjustment'] != 'none' else ''}
    </div>
"""
        
        html += """
    <h2>Threshold Recommendations</h2>
    <ul>
"""
        
        # Aggregate recommendations
        adjustments = [a['suggested_adjustment'] for a in analyses if a['suggested_adjustment'] != 'none']
        if adjustments:
            for adj in set(adjustments):
                html += f"        <li>{adj}</li>\n"
        else:
            html += "        <li>Current thresholds performing well - no changes recommended</li>\n"
        
        html += """
    </ul>
</body>
</html>
"""
        
        return html
    
    def send_email_report(self, analysis_date: date, html_body: str):
        """Send email report via SES"""
        
        subject = f"Daily Trading Analysis - {analysis_date.strftime('%B %d, %Y')}"
        
        try:
            self.ses.send_email(
                Source=self.email_from,
                Destination={'ToAddresses': [self.email_to]},
                Message={
                    'Subject': {'Data': subject},
                    'Body': {
                        'Html': {'Data': html_body}
                    }
                }
            )
            print(f"Email report sent to {self.email_to}")
            
        except Exception as e:
            print(f"Email error: {e}")
            raise
    
    def run(self, analysis_date: Optional[date] = None) -> Dict:
        """
        Main execution: Analyze missed opportunities, generate report.
        
        Args:
            analysis_date: Date to analyze (default: today)
            
        Returns:
            Summary of execution
        """
        if analysis_date is None:
            # Use yesterday (since running at 6 PM, market just closed)
            analysis_date = date.today()
        
        print(f"=== Opportunity Analyzer Starting for {analysis_date} ===")
        start_time = datetime.now()
        
        # 1. Get missed surges
        print("Finding missed volume surges...")
        missed_surges = self.get_missed_surges(analysis_date)
        print(f"  - Found {len(missed_surges)} missed surges")
        
        if not missed_surges:
            print("No missed opportunities to analyze")
            return {
                'success': True,
                'analysis_date': str(analysis_date),
                'missed_count': 0,
                'message': 'No missed opportunities'
            }
        
        # 2. Analyze each with Bedrock
        print("Analyzing with Bedrock...")
        analyses = []
        for surge in missed_surges:
            print(f"  - Analyzing {surge['ticker']} at {surge['ts'].strftime('%H:%M')}")
            analysis = self.analyze_missed_opportunity(surge)
            analyses.append(analysis)
            
            # Store in database
            self.store_analysis(analysis_date, surge, analysis)
        
        # 3. Generate email report
        print("Generating email report...")
        html_report = self.generate_email_report(analysis_date, missed_surges, analyses)
        
        # 4. Send email
        print("Sending email report...")
        self.send_email_report(analysis_date, html_report)
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        should_trade_count = sum(1 for a in analyses if a['should_have_traded'])
        
        summary = {
            'success': True,
            'analysis_date': str(analysis_date),
            'missed_count': len(missed_surges),
            'should_have_traded': should_trade_count,
            'correctly_skipped': len(analyses) - should_trade_count,
            'elapsed_seconds': elapsed
        }
        
        print(f"=== Opportunity Analyzer Complete ({elapsed:.1f}s) ===")
        print(f"Analyzed {len(missed_surges)} opportunities, {should_trade_count} should have traded")
        
        return summary


def lambda_handler(event, context):
    """AWS Lambda handler"""
    try:
        # Allow override of analysis date via event
        analysis_date = None
        if 'analysis_date' in event:
            analysis_date = date.fromisoformat(event['analysis_date'])
        
        analyzer = OpportunityAnalyzer()
        result = analyzer.run(analysis_date)
        
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
    result = OpportunityAnalyzer().run()
    print(json.dumps(result, indent=2, default=str))
