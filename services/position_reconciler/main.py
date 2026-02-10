#!/usr/bin/env python3
"""
Position Reconciliation Service

Syncs database positions with Alpaca positions every 5 minutes.
Resolves phantom positions and detects missing positions.

Author: AI System Owner
Date: 2026-02-07
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Set, Optional
import psycopg2
from alpaca.trading.client import TradingClient
import boto3

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class PositionReconciler:
    """Reconciles database positions with Alpaca positions"""
    
    def __init__(self):
        """Initialize reconciler with database and Alpaca credentials"""
        self.db_config = self._get_db_config()
        self.alpaca_clients = self._get_alpaca_clients()
        self.reconciliation_results = {
            'large': {'checked': 0, 'phantoms': 0, 'missing': 0, 'synced': 0},
            'tiny': {'checked': 0, 'phantoms': 0, 'missing': 0, 'synced': 0}
        }
    
    def _get_db_config(self) -> Dict[str, str]:
        """Get database configuration from Secrets Manager"""
        logger.info("Loading database credentials from Secrets Manager")
        
        secrets_client = boto3.client('secretsmanager', region_name='us-west-2')
        response = secrets_client.get_secret_value(SecretId='ops-pipeline/db-credentials')
        db_secret = json.loads(response['SecretString'])
        
        return {
            'host': db_secret['host'],
            'port': db_secret.get('port', 5432),
            'database': db_secret['database'],
            'user': db_secret['username'],
            'password': db_secret['password']
        }
    
    def _get_alpaca_clients(self) -> Dict[str, TradingClient]:
        """Get Alpaca trading clients for both accounts"""
        logger.info("Loading Alpaca credentials from Secrets Manager")
        
        secrets_client = boto3.client('secretsmanager', region_name='us-west-2')
        
        # Large account
        response = secrets_client.get_secret_value(SecretId='ops-pipeline/alpaca')
        large_creds = json.loads(response['SecretString'])
        large_client = TradingClient(
            large_creds['api_key'],
            large_creds['secret_key'],
            paper=True
        )
        
        # Tiny account
        response = secrets_client.get_secret_value(SecretId='ops-pipeline/alpaca/tiny')
        tiny_creds = json.loads(response['SecretString'])
        tiny_client = TradingClient(
            tiny_creds['api_key'],
            tiny_creds['secret_key'],
            paper=True
        )
        
        return {
            'large': large_client,
            'tiny': tiny_client
        }
    
    def get_db_positions(self, account_name: str) -> Dict[str, Dict]:
        """Get all open positions from database for an account"""
        logger.info(f"Fetching database positions for account: {account_name}")
        
        conn = psycopg2.connect(**self.db_config)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    id,
                    ticker,
                    option_symbol,
                    instrument_type,
                    side,
                    quantity,
                    entry_price,
                    current_price,
                    unrealized_pnl_pct,
                    status,
                    entry_time
                FROM active_positions
                WHERE account_name = %s AND status = 'open'
                ORDER BY id
            """, (account_name,))
            
            positions = {}
            for row in cursor.fetchall():
                pos_id, ticker, option_symbol, instrument_type, side, quantity, \
                entry_price, current_price, pnl_pct, status, entry_time = row
                
                key = option_symbol if option_symbol else ticker
                positions[key] = {
                    'id': pos_id,
                    'ticker': ticker,
                    'symbol': key,
                    'instrument_type': instrument_type,
                    'side': side,
                    'quantity': float(quantity),
                    'entry_price': float(entry_price) if entry_price else 0,
                    'current_price': float(current_price) if current_price else 0,
                    'pnl_pct': float(pnl_pct) if pnl_pct else 0,
                    'entry_time': entry_time
                }
            
            logger.info(f"Found {len(positions)} open positions in database for {account_name}")
            return positions
            
        finally:
            conn.close()
    
    def get_alpaca_positions(self, account_name: str) -> Dict[str, Dict]:
        """Get all open positions from Alpaca for an account"""
        logger.info(f"Fetching Alpaca positions for account: {account_name}")
        
        client = self.alpaca_clients[account_name]
        
        try:
            alpaca_positions = client.get_all_positions()
            
            positions = {}
            for pos in alpaca_positions:
                positions[pos.symbol] = {
                    'symbol': pos.symbol,
                    'quantity': float(pos.qty),
                    'entry_price': float(pos.avg_entry_price),
                    'current_price': float(pos.current_price),
                    'pnl_pct': float(pos.unrealized_plpc) * 100,
                    'market_value': float(pos.market_value)
                }
            
            logger.info(f"Found {len(positions)} open positions in Alpaca for {account_name}")
            return positions
            
        except Exception as e:
            logger.error(f"Error fetching Alpaca positions for {account_name}: {e}")
            return {}
    
    def mark_phantom_position(self, position_id: int, symbol: str, account_name: str):
        """Mark a phantom position (in DB but not in Alpaca) as reconciled"""
        logger.warning(f"Marking phantom position {position_id} ({symbol}) as reconciled")
        
        conn = psycopg2.connect(**self.db_config)
        try:
            cursor = conn.cursor()
            
            # Update position status to closed with reconciliation reason
            cursor.execute("""
                UPDATE active_positions
                SET 
                    status = 'closed',
                    closed_at = %s,
                    close_reason = 'phantom_reconciled',
                    notes = COALESCE(notes || ' | ', '') || 
                           'Position not found in Alpaca during reconciliation at ' || %s
                WHERE id = %s
            """, (
                datetime.now(timezone.utc),
                datetime.now(timezone.utc).isoformat(),
                position_id
            ))
            
            # Move to position_history if migration supports it
            cursor.execute("""
                INSERT INTO position_history (
                    ticker, instrument_type, side, option_symbol,
                    entry_time, closed_at, entry_price, exit_price,
                    quantity, realized_pnl, realized_pnl_pct,
                    max_hold_minutes, close_reason, account_name
                )
                SELECT 
                    ticker, instrument_type, side, option_symbol,
                    entry_time, %s as closed_at, entry_price, current_price as exit_price,
                    quantity, 
                    (current_price - entry_price) * quantity as realized_pnl,
                    CASE WHEN entry_price > 0 
                        THEN ((current_price - entry_price) / entry_price * 100)
                        ELSE 0 
                    END as realized_pnl_pct,
                    max_hold_minutes, 'phantom_reconciled' as close_reason, account_name
                FROM active_positions
                WHERE id = %s
            """, (
                datetime.now(timezone.utc),
                position_id
            ))
            
            conn.commit()
            logger.info(f"Successfully reconciled phantom position {position_id}")
            
        except Exception as e:
            logger.error(f"Error marking phantom position {position_id}: {e}")
            conn.rollback()
        finally:
            conn.close()
    
    def create_missing_position(self, symbol: str, alpaca_pos: Dict, account_name: str):
        """Create database entry for position found in Alpaca but not in DB"""
        logger.warning(f"Creating missing database entry for {symbol} in {account_name} account")
        
        conn = psycopg2.connect(**self.db_config)
        try:
            cursor = conn.cursor()
            
            # Determine instrument type and ticker from symbol
            instrument_type = 'option' if len(symbol) > 10 else 'stock'
            ticker = symbol[:symbol.index('2')] if instrument_type == 'option' else symbol
            
            cursor.execute("""
                INSERT INTO active_positions (
                    ticker,
                    instrument_type,
                    side,
                    option_symbol,
                    entry_time,
                    entry_price,
                    current_price,
                    quantity,
                    status,
                    account_name,
                    max_hold_minutes,
                    notes
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                ticker,
                instrument_type,
                'long',  # Assume long for now
                symbol if instrument_type == 'option' else None,
                datetime.now(timezone.utc),
                alpaca_pos['entry_price'],
                alpaca_pos['current_price'],
                alpaca_pos['quantity'],
                'open',
                account_name,
                240,  # Default 4 hours
                f"Position discovered during reconciliation at {datetime.now(timezone.utc).isoformat()}"
            ))
            
            conn.commit()
            logger.info(f"Successfully created missing position for {symbol}")
            
        except Exception as e:
            logger.error(f"Error creating missing position for {symbol}: {e}")
            conn.rollback()
        finally:
            conn.close()
    
    def sync_position_prices(self, position_id: int, db_pos: Dict, alpaca_pos: Dict):
        """Update database position with current Alpaca prices"""
        conn = psycopg2.connect(**self.db_config)
        try:
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE active_positions
                SET 
                    current_price = %s,
                    unrealized_pnl = ((%s - entry_price) * quantity),
                    unrealized_pnl_pct = CASE 
                        WHEN entry_price > 0 
                        THEN ((%s - entry_price) / entry_price * 100)
                        ELSE 0 
                    END,
                    last_updated = %s
                WHERE id = %s
            """, (
                alpaca_pos['current_price'],
                alpaca_pos['current_price'],
                alpaca_pos['current_price'],
                datetime.now(timezone.utc),
                position_id
            ))
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"Error syncing prices for position {position_id}: {e}")
            conn.rollback()
        finally:
            conn.close()
    
    def reconcile_account(self, account_name: str):
        """Reconcile positions for a specific account"""
        logger.info(f"=" * 80)
        logger.info(f"Starting reconciliation for {account_name} account")
        logger.info(f"=" * 80)
        
        # Get positions from both sources
        db_positions = self.get_db_positions(account_name)
        alpaca_positions = self.get_alpaca_positions(account_name)
        
        db_symbols = set(db_positions.keys())
        alpaca_symbols = set(alpaca_positions.keys())
        
        # Find phantoms (in DB but not in Alpaca)
        phantom_symbols = db_symbols - alpaca_symbols
        
        # Find missing (in Alpaca but not in DB)
        missing_symbols = alpaca_symbols - db_symbols
        
        # Find matching (in both)
        matching_symbols = db_symbols & alpaca_symbols
        
        # Process phantoms
        for symbol in phantom_symbols:
            pos = db_positions[symbol]
            logger.warning(f"PHANTOM: {symbol} (ID {pos['id']}) - in DB but not in Alpaca")
            self.mark_phantom_position(pos['id'], symbol, account_name)
            self.reconciliation_results[account_name]['phantoms'] += 1
        
        # Process missing
        for symbol in missing_symbols:
            pos = alpaca_positions[symbol]
            logger.warning(f"MISSING: {symbol} - in Alpaca but not in DB")
            self.create_missing_position(symbol, pos, account_name)
            self.reconciliation_results[account_name]['missing'] += 1
        
        # Sync matching positions
        for symbol in matching_symbols:
            db_pos = db_positions[symbol]
            alpaca_pos = alpaca_positions[symbol]
            
            # Check if prices are significantly different (>1%)
            price_diff = abs(db_pos['current_price'] - alpaca_pos['current_price'])
            if price_diff > 0.01 * alpaca_pos['current_price']:
                logger.info(f"SYNC: {symbol} - updating price from ${db_pos['current_price']:.2f} to ${alpaca_pos['current_price']:.2f}")
                self.sync_position_prices(db_pos['id'], db_pos, alpaca_pos)
                self.reconciliation_results[account_name]['synced'] += 1
        
        self.reconciliation_results[account_name]['checked'] = len(db_symbols)
        
        logger.info(f"Reconciliation complete for {account_name}")
        logger.info(f"Checked: {len(db_symbols)}, Phantoms: {len(phantom_symbols)}, Missing: {len(missing_symbols)}, Synced: {self.reconciliation_results[account_name]['synced']}")
    
    def run(self):
        """Run reconciliation for both accounts"""
        start_time = datetime.now(timezone.utc)
        logger.info("=" * 80)
        logger.info("POSITION RECONCILIATION SERVICE - STARTING")
        logger.info(f"Time: {start_time.isoformat()}")
        logger.info("=" * 80)
        
        try:
            # Reconcile large account
            self.reconcile_account('large')
            
            # Reconcile tiny account
            self.reconcile_account('tiny')
            
            # Print summary
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            
            logger.info("=" * 80)
            logger.info("RECONCILIATION SUMMARY")
            logger.info("=" * 80)
            
            for account in ['large', 'tiny']:
                results = self.reconciliation_results[account]
                logger.info(f"{account.upper()} Account:")
                logger.info(f"  Positions checked: {results['checked']}")
                logger.info(f"  Phantoms resolved: {results['phantoms']}")
                logger.info(f"  Missing positions added: {results['missing']}")
                logger.info(f"  Prices synced: {results['synced']}")
            
            logger.info(f"Duration: {duration:.2f} seconds")
            logger.info("=" * 80)
            
            # Return success
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Reconciliation completed successfully',
                    'results': self.reconciliation_results,
                    'duration_seconds': duration
                })
            }
            
        except Exception as e:
            logger.error(f"Error during reconciliation: {e}", exc_info=True)
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'message': 'Reconciliation failed',
                    'error': str(e)
                })
            }


def main():
    """Main entry point"""
    reconciler = PositionReconciler()
    result = reconciler.run()
    
    # Exit with appropriate code
    sys.exit(0 if result['statusCode'] == 200 else 1)


if __name__ == '__main__':
    main()
