#!/usr/bin/env python3
"""
Historical Pattern Analyzer

Analyzes past trades to identify patterns that preceded successful big moves.
Helps optimize signal generation and entry timing.

Author: AI System Owner
Date: 2026-02-07
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Optional
import psycopg2
import boto3
from collections import defaultdict

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class PatternAnalyzer:
    """Analyzes historical trades to find patterns preceding big moves"""
    
    def __init__(self):
        """Initialize analyzer with database credentials"""
        self.db_config = self._get_db_config()
        self.patterns = defaultdict(list)
        self.big_moves = []  # Trades with >10% gain
        self.losers = []     # Trades with loss
        
    def _get_db_config(self) -> Dict[str, str]:
        """Get database configuration from environment or hardcoded defaults"""
        logger.info("Using database configuration")
        
        # Use known RDS endpoint from other services
        return {
            'host': 'ops-pipeline-db.cls4wuyg010k.us-west-2.rds.amazonaws.com',
            'port': 5432,
            'database': 'ops_pipeline',
            'user': os.environ.get('DB_USER', 'postgres'),
            'password': os.environ.get('DB_PASSWORD', '')  # Will use IAM auth if empty
        }
    
    def fetch_historical_trades(self, days_back: int = 30) -> List[Dict]:
        """Fetch closed trades from position_history"""
        logger.info(f"Fetching trades from last {days_back} days")
        
        conn = psycopg2.connect(**self.db_config)
        try:
            cursor = conn.cursor()
            
            since_date = datetime.now(timezone.utc) - timedelta(days=days_back)
            
            cursor.execute("""
                SELECT 
                    id,
                    ticker,
                    instrument_type,
                    side,
                    option_symbol,
                    entry_time,
                    exit_time,
                    entry_price,
                    exit_price,
                    quantity,
                    pnl_dollars,
                    pnl_pct,
                    max_hold_minutes,
                    exit_reason,
                    'large' as account_name,
                    strategy_type,
                    0 as confidence_score,
                    NULL as entry_signal_type,
                    best_unrealized_pnl_pct,
                    NULL as trailing_stop_locked
                FROM position_history
                WHERE exit_time >= %s
                ORDER BY exit_time DESC
            """, (since_date,))
            
            trades = []
            for row in cursor.fetchall():
                trade = {
                    'id': row[0],
                    'ticker': row[1],
                    'instrument_type': row[2],
                    'side': row[3],
                    'option_symbol': row[4],
                    'entry_time': row[5],
                    'closed_at': row[6],
                    'entry_price': float(row[7]) if row[7] else 0,
                    'exit_price': float(row[8]) if row[8] else 0,
                    'quantity': float(row[9]) if row[9] else 0,
                    'realized_pnl': float(row[10]) if row[10] else 0,
                    'realized_pnl_pct': float(row[11]) if row[11] else 0,
                    'max_hold_minutes': row[12],
                    'close_reason': row[13],
                    'account_name': row[14],
                    'strategy_type': row[15],
                    'confidence_score': float(row[16]) if row[16] else 0,
                    'entry_signal_type': row[17],
                    'peak_price': float(row[18]) if row[18] else None,
                    'trailing_stop_locked': float(row[19]) if row[19] else None,
                }
                
                # Calculate hold time
                if trade['entry_time'] and trade['closed_at']:
                    hold_time = trade['closed_at'] - trade['entry_time']
                    trade['hold_minutes'] = hold_time.total_seconds() / 60
                else:
                    trade['hold_minutes'] = 0
                
                # Calculate peak gain if available
                if trade['peak_price'] and trade['entry_price'] > 0:
                    trade['peak_gain_pct'] = ((trade['peak_price'] - trade['entry_price']) / trade['entry_price']) * 100
                else:
                    trade['peak_gain_pct'] = None
                
                trades.append(trade)
            
            logger.info(f"Fetched {len(trades)} historical trades")
            return trades
            
        finally:
            conn.close()
    
    def fetch_features_for_trade(self, ticker: str, entry_time: datetime) -> Optional[Dict]:
        """Fetch market features at time of trade entry"""
        conn = psycopg2.connect(**self.db_config)
        try:
            cursor = conn.cursor()
            
            # Get features within 5 minutes of entry
            time_window_start = entry_time - timedelta(minutes=5)
            time_window_end = entry_time + timedelta(minutes=1)
            
            cursor.execute("""
                SELECT 
                    sma20,
                    sma50,
                    trend_state,
                    vol_ratio,
                    volume_ratio,
                    volume_surge,
                    distance_sma20,
                    distance_sma50,
                    ts
                FROM lane_features
                WHERE ticker = %s 
                  AND ts BETWEEN %s AND %s
                ORDER BY ts DESC
                LIMIT 1
            """, (ticker, time_window_start, time_window_end))
            
            row = cursor.fetchone()
            if row:
                return {
                    'sma20': float(row[0]) if row[0] else None,
                    'sma50': float(row[1]) if row[1] else None,
                    'trend_state': int(row[2]) if row[2] is not None else None,
                    'vol_ratio': float(row[3]) if row[3] else None,
                    'volume_ratio': float(row[4]) if row[4] else None,
                    'volume_surge': row[5],
                    'distance_sma20': float(row[6]) if row[6] else None,
                    'distance_sma50': float(row[7]) if row[7] else None,
                    'feature_timestamp': row[8]
                }
            return None
            
        finally:
            conn.close()
    
    def categorize_trades(self, trades: List[Dict]):
        """Categorize trades into big winners, small winners, losers"""
        logger.info("Categorizing trades by outcome")
        
        big_winners = []    # >20% gain
        good_winners = []   # 10-20% gain
        small_winners = []  # 0-10% gain
        small_losers = []   # 0 to -20% loss
        big_losers = []     # < -20% loss
        
        for trade in trades:
            pnl_pct = trade['realized_pnl_pct']
            
            if pnl_pct >= 20:
                big_winners.append(trade)
            elif pnl_pct >= 10:
                good_winners.append(trade)
            elif pnl_pct > 0:
                small_winners.append(trade)
            elif pnl_pct >= -20:
                small_losers.append(trade)
            else:
                big_losers.append(trade)
        
        logger.info(f"Big winners (>20%): {len(big_winners)}")
        logger.info(f"Good winners (10-20%): {len(good_winners)}")
        logger.info(f"Small winners (0-10%): {len(small_winners)}")
        logger.info(f"Small losers (0 to -20%): {len(small_losers)}")
        logger.info(f"Big losers (<-20%): {len(big_losers)}")
        
        return {
            'big_winners': big_winners,
            'good_winners': good_winners,
            'small_winners': small_winners,
            'small_losers': small_losers,
            'big_losers': big_losers
        }
    
    def analyze_common_patterns(self, trades: List[Dict], category: str) -> Dict:
        """Find common patterns in a category of trades"""
        logger.info(f"Analyzing patterns for {category}")
        
        if not trades:
            return {'count': 0, 'patterns': {}}
        
        patterns = {
            'strategies': defaultdict(int),
            'entry_signals': defaultdict(int),
            'tickers': defaultdict(int),
            'close_reasons': defaultdict(int),
            'avg_confidence': 0,
            'avg_hold_minutes': 0,
            'with_features': 0
        }
        
        total_confidence = 0
        total_hold = 0
        
        for trade in trades:
            # Strategy distribution
            if trade['strategy_type']:
                patterns['strategies'][trade['strategy_type']] += 1
            
            # Entry signal distribution
            if trade['entry_signal_type']:
                patterns['entry_signals'][trade['entry_signal_type']] += 1
            
            # Ticker distribution
            patterns['tickers'][trade['ticker']] += 1
            
            # Close reason distribution
            if trade['close_reason']:
                patterns['close_reasons'][trade['close_reason']] += 1
            
            # Averages
            if trade['confidence_score']:
                total_confidence += trade['confidence_score']
            total_hold += trade['hold_minutes']
        
        count = len(trades)
        patterns['avg_confidence'] = total_confidence / count if count > 0 else 0
        patterns['avg_hold_minutes'] = total_hold / count if count > 0 else 0
        
        # Convert defaultdicts to regular dicts for JSON serialization
        patterns['strategies'] = dict(patterns['strategies'])
        patterns['entry_signals'] = dict(patterns['entry_signals'])
        patterns['tickers'] = dict(patterns['tickers'])
        patterns['close_reasons'] = dict(patterns['close_reasons'])
        
        return {
            'count': count,
            'patterns': patterns
        }
    
    def identify_predictive_features(self, categorized: Dict) -> Dict:
        """Identify which features predict big moves"""
        logger.info("Identifying predictive features")
        
        big_winners = categorized['big_winners']
        big_losers = categorized['big_losers']
        
        winner_features = []
        loser_features = []
        
        # Sample features for winners
        for trade in big_winners[:10]:  # Sample first 10
            features = self.fetch_features_for_trade(trade['ticker'], trade['entry_time'])
            if features:
                winner_features.append(features)
        
        # Sample features for losers
        for trade in big_losers[:10]:  # Sample first 10
            features = self.fetch_features_for_trade(trade['ticker'], trade['entry_time'])
            if features:
                loser_features.append(features)
        
        # Calculate averages
        def avg_features(feature_list):
            if not feature_list:
                return {}
            
            result = {}
            for key in ['vol_ratio', 'volume_ratio', 'distance_sma20', 'distance_sma50']:
                values = [f[key] for f in feature_list if f.get(key) is not None]
                result[key] = sum(values) / len(values) if values else None
            
            # Trend state distribution
            trends = [f['trend_state'] for f in feature_list if f.get('trend_state') is not None]
            result['trend_states'] = dict((t, trends.count(t)) for t in set(trends))
            
            # Volume surge count
            surges = [f['volume_surge'] for f in feature_list if f.get('volume_surge') is not None]
            result['volume_surge_count'] = sum(1 for s in surges if s is True)
            
            return result
        
        return {
            'big_winners': {
                'sample_size': len(winner_features),
                'avg_features': avg_features(winner_features)
            },
            'big_losers': {
                'sample_size': len(loser_features),
                'avg_features': avg_features(loser_features)
            }
        }
    
    def generate_insights(self, categorized: Dict, patterns: Dict) -> List[str]:
        """Generate actionable insights from analysis"""
        insights = []
        
        big_winners = categorized['big_winners']
        big_losers = categorized['big_losers']
        
        total_trades = sum(len(v) for v in categorized.values())
        win_rate = (len(big_winners) + len(categorized['good_winners']) + len(categorized['small_winners'])) / total_trades if total_trades > 0 else 0
        
        insights.append(f"📊 Overall win rate: {win_rate*100:.1f}%")
        
        # Strategy insights
        if patterns['big_winners']['patterns']['strategies']:
            top_strategy = max(patterns['big_winners']['patterns']['strategies'].items(), key=lambda x: x[1])
            insights.append(f"🎯 Best strategy for big wins: {top_strategy[0]} ({top_strategy[1]} trades)")
        
        # Confidence insights
        winner_conf = patterns['big_winners']['patterns']['avg_confidence']
        loser_conf = patterns['big_losers']['patterns']['avg_confidence']
        if winner_conf > loser_conf:
            insights.append(f"✅ Higher confidence correlates with wins: {winner_conf:.2f} vs {loser_conf:.2f}")
        else:
            insights.append(f"⚠️ Confidence NOT predictive: winners {winner_conf:.2f} vs losers {loser_conf:.2f}")
        
        # Hold time insights
        winner_hold = patterns['big_winners']['patterns']['avg_hold_minutes']
        loser_hold = patterns['big_losers']['patterns']['avg_hold_minutes']
        insights.append(f"⏱️ Winners held {winner_hold:.0f} min vs losers {loser_hold:.0f} min")
        
        # Close reason insights
        if patterns['big_losers']['patterns']['close_reasons']:
            top_loss_reason = max(patterns['big_losers']['patterns']['close_reasons'].items(), key=lambda x: x[1])
            insights.append(f"❌ Main loss reason: {top_loss_reason[0]} ({top_loss_reason[1]} trades)")
        
        return insights
    
    def run(self, days_back: int = 30) -> Dict:
        """Run full pattern analysis"""
        start_time = datetime.now(timezone.utc)
        logger.info("=" * 80)
        logger.info("HISTORICAL PATTERN ANALYZER - STARTING")
        logger.info(f"Time: {start_time.isoformat()}")
        logger.info(f"Analyzing last {days_back} days")
        logger.info("=" * 80)
        
        try:
            # Fetch trades
            trades = self.fetch_historical_trades(days_back)
            
            if not trades:
                logger.warning("No trades found in the specified period")
                return {
                    'statusCode': 200,
                    'body': json.dumps({
                        'message': 'No trades to analyze',
                        'trades_count': 0
                    })
                }
            
            # Categorize
            categorized = self.categorize_trades(trades)
            
            # Analyze patterns
            patterns = {}
            for category, trades_list in categorized.items():
                patterns[category] = self.analyze_common_patterns(trades_list, category)
            
            # Identify predictive features
            predictive_features = self.identify_predictive_features(categorized)
            
            # Generate insights
            insights = self.generate_insights(categorized, patterns)
            
            # Print summary
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            
            logger.info("=" * 80)
            logger.info("ANALYSIS COMPLETE")
            logger.info("=" * 80)
            
            logger.info(f"Total trades analyzed: {len(trades)}")
            logger.info("")
            logger.info("📊 DISTRIBUTION:")
            for category, data in patterns.items():
                logger.info(f"  {category}: {data['count']} trades")
            
            logger.info("")
            logger.info("💡 KEY INSIGHTS:")
            for insight in insights:
                logger.info(f"  {insight}")
            
            logger.info("")
            logger.info(f"Duration: {duration:.2f} seconds")
            logger.info("=" * 80)
            
            # Return results
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Analysis completed successfully',
                    'trades_analyzed': len(trades),
                    'categorized': {k: len(v) for k, v in categorized.items()},
                    'patterns': patterns,
                    'predictive_features': predictive_features,
                    'insights': insights,
                    'duration_seconds': duration
                }, default=str)
            }
            
        except Exception as e:
            logger.error(f"Error during analysis: {e}", exc_info=True)
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'message': 'Analysis failed',
                    'error': str(e)
                })
            }


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Analyze historical trading patterns')
    parser.add_argument('--days', type=int, default=30, help='Number of days to analyze')
    args = parser.parse_args()
    
    analyzer = PatternAnalyzer()
    result = analyzer.run(days_back=args.days)
    
    # Exit with appropriate code
    sys.exit(0 if result['statusCode'] == 200 else 1)


if __name__ == '__main__':
    main()
