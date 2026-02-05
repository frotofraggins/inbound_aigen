"""
Database operations for Position Manager
"""
import psycopg2
import psycopg2.extras
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging
import json

from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

logger = logging.getLogger(__name__)


class DatabaseConnection:
    """Database connection manager"""
    
    def __init__(self):
        self.conn = None
        
    def connect(self):
        """Establish database connection"""
        try:
            self.conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                dbname=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
                connect_timeout=10
            )
            logger.info("Database connection established")
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def get_filled_executions_since(since_time: datetime) -> List[Dict[str, Any]]:
    """
    Get all FILLED executions since a given time that aren't already tracked
    Uses execution_mode to identify real trades (ALPACA_PAPER or LIVE)
    """
    query = """
    SELECT 
        de.execution_id as id,
        de.recommendation_id,
        de.ticker,
        de.instrument_type,
        de.strategy_type,
        COALESCE(de.side, 'long') as side,
        de.qty as quantity,
        de.entry_price,
        de.stop_loss_price as stop_loss,
        de.take_profit_price as take_profit,
        de.strike_price,
        de.expiration_date,
        de.max_hold_minutes,
        de.broker_order_id,
        de.stop_order_id,
        de.target_order_id,
        COALESCE(de.status, 'FILLED') as status,
        COALESCE(de.executed_at, de.simulated_ts) as executed_at
    FROM dispatch_executions de
    LEFT JOIN active_positions ap ON ap.execution_id = de.execution_id
    WHERE de.execution_mode IN ('ALPACA_PAPER', 'LIVE')
      AND de.simulated_ts >= %s
      AND ap.id IS NULL  -- Not already tracked
    ORDER BY de.simulated_ts DESC
    """
    
    with DatabaseConnection() as db:
        with db.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, (since_time,))
            results = cur.fetchall()
            return [dict(row) for row in results]


def create_active_position(execution: Dict[str, Any]) -> int:
    """
    Create a new active position from an execution
    """
    query = """
    INSERT INTO active_positions (
        execution_id, ticker, instrument_type, strategy_type,
        side, quantity, entry_price, entry_time,
        strike_price, expiration_date,
        stop_loss, take_profit, max_hold_minutes,
        bracket_order_accepted, stop_order_id, target_order_id,
        current_price, status
    ) VALUES (
        %s, %s, %s, %s,
        %s, %s, %s, %s,
        %s, %s,
        %s, %s, %s,
        %s, %s, %s,
        %s, 'open'
    )
    RETURNING id
    """
    
    with DatabaseConnection() as db:
        with db.conn.cursor() as cur:
            cur.execute(query, (
                execution['id'],
                execution['ticker'],
                execution['instrument_type'],
                execution['strategy_type'],
                execution['side'],
                execution['quantity'],
                execution['entry_price'],
                execution['executed_at'],
                execution.get('strike_price'),
                execution.get('expiration_date'),
                execution['stop_loss'],
                execution['take_profit'],
                execution.get('max_hold_minutes', 240),
                bool(execution.get('stop_order_id') and execution.get('target_order_id')),
                execution.get('stop_order_id'),
                execution.get('target_order_id'),
                execution['entry_price']  # Initial current_price = entry_price
            ))
            position_id = cur.fetchone()[0]
            db.conn.commit()
            logger.info(f"Created active position {position_id} for execution {execution['id']}")
            return position_id


def get_open_positions() -> List[Dict[str, Any]]:
    """
    Get all currently open positions
    """
    query = """
    SELECT 
        id, execution_id, ticker, instrument_type, strategy_type,
        side, quantity, entry_price, entry_time,
        strike_price, expiration_date,
        stop_loss, take_profit, max_hold_minutes,
        bracket_order_accepted, stop_order_id, target_order_id,
        current_price, current_pnl_dollars, current_pnl_percent,
        last_checked_at, check_count,
        status, created_at
    FROM active_positions
    WHERE status = 'open'
    ORDER BY entry_time ASC
    """
    
    with DatabaseConnection() as db:
        with db.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query)
            results = cur.fetchall()
            return [dict(row) for row in results]


def update_position_price(
    position_id: int,
    current_price: float,
    pnl_dollars: float,
    pnl_percent: float
) -> None:
    """
    Update position with current price and P&L
    """
    query = """
    UPDATE active_positions
    SET current_price = %s,
        current_pnl_dollars = %s,
        current_pnl_percent = %s,
        last_checked_at = NOW(),
        check_count = check_count + 1,
        updated_at = NOW()
    WHERE id = %s
    """
    
    with DatabaseConnection() as db:
        with db.conn.cursor() as cur:
            cur.execute(query, (current_price, pnl_dollars, pnl_percent, position_id))
            db.conn.commit()


def update_position_status(position_id: int, status: str) -> None:
    """
    Update position status
    """
    query = """
    UPDATE active_positions
    SET status = %s,
        updated_at = NOW()
    WHERE id = %s
    """
    
    with DatabaseConnection() as db:
        with db.conn.cursor() as cur:
            cur.execute(query, (status, position_id))
            db.conn.commit()
            logger.info(f"Position {position_id} status updated to {status}")


def close_position(
    position_id: int,
    close_reason: str,
    final_price: Optional[float] = None
) -> None:
    """
    Mark position as closed
    """
    query = """
    UPDATE active_positions
    SET status = 'closed',
        close_reason = %s,
        closed_at = NOW(),
        updated_at = NOW()
    WHERE id = %s
    """
    
    if final_price:
        query = """
        UPDATE active_positions
        SET status = 'closed',
            close_reason = %s,
            current_price = %s,
            closed_at = NOW(),
            updated_at = NOW()
        WHERE id = %s
        """
    
    with DatabaseConnection() as db:
        with db.conn.cursor() as cur:
            if final_price:
                cur.execute(query, (close_reason, final_price, position_id))
            else:
                cur.execute(query, (close_reason, position_id))
            db.conn.commit()
            logger.info(f"Position {position_id} closed: {close_reason}")


def update_position_quantity(position_id: int, quantity: float) -> None:
    """
    Update position quantity (for partial fills)
    """
    query = """
    UPDATE active_positions
    SET quantity = %s,
        updated_at = NOW()
    WHERE id = %s
    """
    
    with DatabaseConnection() as db:
        with db.conn.cursor() as cur:
            cur.execute(query, (quantity, position_id))
            db.conn.commit()
            logger.info(f"Position {position_id} quantity updated to {quantity}")


def log_position_event(
    position_id: int,
    event_type: str,
    event_data: Dict[str, Any]
) -> None:
    """
    Log a position monitoring event
    """
    query = """
    INSERT INTO position_events (position_id, event_type, event_data)
    VALUES (%s, %s, %s)
    """
    
    with DatabaseConnection() as db:
        with db.conn.cursor() as cur:
            cur.execute(query, (position_id, event_type, json.dumps(event_data)))
            db.conn.commit()


def get_position_by_id(position_id: int) -> Optional[Dict[str, Any]]:
    """
    Get a specific position by ID
    """
    query = """
    SELECT 
        id, execution_id, ticker, instrument_type, strategy_type,
        side, quantity, entry_price, entry_time,
        strike_price, expiration_date,
        stop_loss, take_profit, max_hold_minutes,
        bracket_order_accepted, stop_order_id, target_order_id,
        current_price, current_pnl_dollars, current_pnl_percent,
        last_checked_at, check_count,
        status, close_reason, created_at, closed_at
    FROM active_positions
    WHERE id = %s
    """
    
    with DatabaseConnection() as db:
        with db.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, (position_id,))
            result = cur.fetchone()
            return dict(result) if result else None


def update_bracket_orders(
    position_id: int,
    stop_order_id: Optional[str],
    target_order_id: Optional[str],
    accepted: bool
) -> None:
    """
    Update bracket order information
    """
    query = """
    UPDATE active_positions
    SET stop_order_id = %s,
        target_order_id = %s,
        bracket_order_accepted = %s,
        updated_at = NOW()
    WHERE id = %s
    """
    
    with DatabaseConnection() as db:
        with db.conn.cursor() as cur:
            cur.execute(query, (stop_order_id, target_order_id, accepted, position_id))
            db.conn.commit()
            logger.info(f"Position {position_id} bracket orders updated")


# Phase 17: Options bar capture methods

def store_option_bars(bars: List[Dict[str, Any]]) -> int:
    """
    Store option bars in database for AI learning.
    Uses UPSERT to handle duplicates safely.
    
    Returns: Number of bars inserted/updated
    """
    if not bars:
        return 0
    
    query = """
        INSERT INTO option_bars (symbol, ts, open, high, low, close, volume, trade_count, vwap)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (symbol, ts) DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume,
            trade_count = EXCLUDED.trade_count,
            vwap = EXCLUDED.vwap
    """
    
    inserted = 0
    with DatabaseConnection() as db:
        with db.conn.cursor() as cur:
            for bar in bars:
                try:
                    cur.execute(query, (
                        bar['symbol'],
                        bar['timestamp'],
                        bar['open'],
                        bar['high'],
                        bar['low'],
                        bar['close'],
                        bar.get('volume'),
                        bar.get('trade_count'),
                        bar.get('vwap')
                    ))
                    inserted += 1
                except Exception as e:
                    logger.warning(f"Failed to insert bar for {bar.get('symbol')}: {e}")
            
            db.conn.commit()
    
    return inserted


def update_position_bar_metadata(
    position_id: int,
    bars_count: int,
    peak_premium: float,
    lowest_premium: float
) -> None:
    """
    Update position with bar capture metadata.
    Tracks how many bars captured and peak/lowest premiums seen.
    """
    query = """
        UPDATE dispatch_executions de
        SET 
            bars_captured_count = bars_captured_count + %s,
            peak_premium = GREATEST(COALESCE(peak_premium, 0), %s),
            lowest_premium = LEAST(COALESCE(lowest_premium, 999999), %s),
            last_bar_ts = NOW()
        FROM active_positions ap
        WHERE ap.execution_id = de.execution_id
          AND ap.id = %s
    """
    
    with DatabaseConnection() as db:
        with db.conn.cursor() as cur:
            cur.execute(query, (bars_count, peak_premium, lowest_premium, position_id))
            db.conn.commit()


# Phase 3-4: Trailing stops and advanced exit methods

def update_position_peak(position_id: int, peak_price: float) -> None:
    """
    Update position peak price for trailing stop calculation
    """
    query = """
    UPDATE active_positions
    SET peak_price = %s,
        updated_at = NOW()
    WHERE id = %s
    """
    
    with DatabaseConnection() as db:
        with db.conn.cursor() as cur:
            cur.execute(query, (peak_price, position_id))
            db.conn.commit()


def update_position_trailing_stop(position_id: int, trailing_stop_price: float) -> None:
    """
    Update position trailing stop price
    """
    query = """
    UPDATE active_positions
    SET trailing_stop_price = %s,
        updated_at = NOW()
    WHERE id = %s
    """
    
    with DatabaseConnection() as db:
        with db.conn.cursor() as cur:
            cur.execute(query, (trailing_stop_price, position_id))
            db.conn.commit()


def get_iv_history(ticker: str, days: int = 252) -> List[float]:
    """
    Get historical IV values for a ticker (for IV rank calculation)
    Returns list of IV values from most recent 'days' days
    """
    query = """
    SELECT implied_volatility
    FROM iv_history
    WHERE ticker = %s
      AND recorded_at >= NOW() - INTERVAL '%s days'
    ORDER BY recorded_at DESC
    """
    
    with DatabaseConnection() as db:
        with db.conn.cursor() as cur:
            cur.execute(query, (ticker, days))
            results = cur.fetchall()
            return [float(row[0]) for row in results if row[0] is not None]


def store_iv_value(ticker: str, implied_volatility: float) -> None:
    """
    Store an IV observation for IV rank calculations
    """
    query = """
    INSERT INTO iv_history (ticker, implied_volatility, recorded_at)
    VALUES (%s, %s, NOW())
    ON CONFLICT (ticker, recorded_at) DO UPDATE
    SET implied_volatility = EXCLUDED.implied_volatility
    """
    
    with DatabaseConnection() as db:
        with db.conn.cursor() as cur:
            cur.execute(query, (ticker, implied_volatility))
            db.conn.commit()


def get_historical_trade_stats(account_tier: str, days: int = 30) -> Dict[str, float]:
    """
    Get historical trade statistics for Kelly Criterion calculation
    """
    query = """
    SELECT 
        COUNT(*) FILTER (WHERE exit_pnl > 0)::float / NULLIF(COUNT(*), 0) as win_rate,
        AVG(exit_pnl_pct) FILTER (WHERE exit_pnl > 0) as avg_win,
        AVG(exit_pnl_pct) FILTER (WHERE exit_pnl < 0) as avg_loss,
        COUNT(*) as total_trades
    FROM ai_option_trades
    WHERE account_tier = %s
      AND closed_at > NOW() - INTERVAL '%s days'
    """
    
    with DatabaseConnection() as db:
        with db.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, (account_tier, days))
            result = cur.fetchone()
            return dict(result) if result else {
                'win_rate': 0.5,
                'avg_win': 30.0,
                'avg_loss': -15.0,
                'total_trades': 0
            }


# Phase 3: Alpaca sync helper functions

def get_position_by_symbol(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Get an active position by its ticker or option symbol
    Used to check if we're already tracking a position from Alpaca
    """
    query = """
    SELECT 
        id, execution_id, execution_uuid, ticker, instrument_type, strategy_type,
        side, quantity, entry_price, entry_time,
        strike_price, expiration_date, option_symbol,
        stop_loss, take_profit, max_hold_minutes,
        bracket_order_accepted, stop_order_id, target_order_id,
        current_price, current_pnl_dollars, current_pnl_percent,
        entry_features_json, entry_iv_rank, entry_spread_pct,
        best_unrealized_pnl_pct, worst_unrealized_pnl_pct,
        best_unrealized_pnl_dollars, worst_unrealized_pnl_dollars,
        last_mark_price,
        status, created_at
    FROM active_positions
    WHERE (ticker = %s OR option_symbol = %s)
      AND status = 'open'
    ORDER BY entry_time DESC
    LIMIT 1
    """
    
    with DatabaseConnection() as db:
        with db.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, (symbol, symbol))
            result = cur.fetchone()
            return dict(result) if result else None


def create_position_from_alpaca(
    ticker: str,
    instrument_type: str,
    side: str,
    quantity: float,
    entry_price: float,
    current_price: float,
    strike_price: Optional[float] = None,
    expiration_date: Optional[str] = None,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
    option_symbol: Optional[str] = None
) -> int:
    """
    Create a new active position from Alpaca API data
    This is used when syncing positions that weren't logged in dispatch_executions
    """
    # Avoid duplicate inserts by checking existing open position first
    symbol_key = option_symbol or ticker
    existing = get_position_by_symbol(symbol_key)
    if existing:
        logger.debug(f"Position for {symbol_key} already exists (id={existing['id']})")
        return existing['id']

    query = """
    INSERT INTO active_positions (
        ticker, instrument_type, strategy_type,
        side, quantity, entry_price, entry_time,
        strike_price, expiration_date, option_symbol,
        stop_loss, take_profit, max_hold_minutes,
        current_price, status, original_quantity,
        entry_features_json,
        entry_iv_rank,
        entry_spread_pct,
        best_unrealized_pnl_pct,
        worst_unrealized_pnl_pct,
        best_unrealized_pnl_dollars,
        worst_unrealized_pnl_dollars,
        last_mark_price
    ) VALUES (
        %s, %s, %s,
        %s, %s, %s, NOW(),
        %s, %s, %s,
        %s, %s, %s,
        %s, 'open', %s,
        %s::jsonb,
        %s,
        %s,
        %s,
        %s,
        %s,
        %s,
        %s
    )
    RETURNING id
    """
    
    with DatabaseConnection() as db:
        with db.conn.cursor() as cur:
            cur.execute(query, (
                ticker,
                instrument_type,
                'swing_trade',  # Default strategy for Alpaca-synced positions
                side,
                quantity,
                entry_price,
                strike_price,
                expiration_date,
                option_symbol,
                stop_loss,
                take_profit,
                240,  # Default 4 hour hold time
                current_price,
                quantity,  # original_quantity = quantity
                json.dumps({}),  # entry_features_json placeholder
                None,  # entry_iv_rank
                None,  # entry_spread_pct
                0.0,   # best_unrealized_pnl_pct
                0.0,   # worst_unrealized_pnl_pct
                0.0,   # best_unrealized_pnl_dollars
                0.0,   # worst_unrealized_pnl_dollars
                current_price  # last_mark_price
            ))
            result = cur.fetchone()
            if result:
                position_id = result[0]
                db.conn.commit()
                logger.info(f"Created position {position_id} from Alpaca sync: {ticker}")
                return position_id
            return None


def insert_account_activity(activity: Dict[str, Any], account_name: Optional[str] = None) -> bool:
    """
    Store Alpaca account activity for learning/audit purposes.
    Uses activity_id as the natural key for idempotency.
    """
    activity_id = activity.get('id')
    if not activity_id:
        return False

    def _num(val):
        try:
            return float(val) if val is not None else None
        except Exception:
            return None

    query = """
    INSERT INTO account_activities (
        activity_id, activity_type, activity_date, transaction_time,
        symbol, qty, price, net_amount, order_id, account_name, raw_json
    ) VALUES (
        %s, %s, %s, %s,
        %s, %s, %s, %s, %s, %s, %s::jsonb
    )
    ON CONFLICT (activity_id) DO NOTHING
    """

    with DatabaseConnection() as db:
        with db.conn.cursor() as cur:
            cur.execute(query, (
                activity_id,
                activity.get('activity_type'),
                activity.get('date'),
                activity.get('transaction_time'),
                activity.get('symbol'),
                _num(activity.get('qty')),
                _num(activity.get('price')),
                _num(activity.get('net_amount')),
                activity.get('order_id'),
                account_name,
                json.dumps(activity)
            ))
            inserted = cur.rowcount > 0
            if inserted:
                db.conn.commit()
            return inserted


def get_latest_account_activity_time() -> Optional[datetime]:
    """
    Return the latest activity timestamp recorded, if any.
    Uses transaction_time when available, otherwise activity_date.
    """
    query = """
    SELECT MAX(COALESCE(transaction_time, activity_date::timestamptz))
    FROM account_activities
    """
    try:
        with DatabaseConnection() as db:
            with db.conn.cursor() as cur:
                cur.execute(query)
                row = cur.fetchone()
                return row[0] if row else None
    except Exception as e:
        logger.warning(f"Could not fetch latest account activity time: {e}")
        return None


# Phase 3: WebSocket Idempotency

def check_event_processed(event_id: str) -> bool:
    """
    Check if a WebSocket event has already been processed.
    Returns True if event exists in dedupe table.
    """
    query = """
    SELECT 1 FROM alpaca_event_dedupe WHERE event_id = %s
    """
    
    try:
        with DatabaseConnection() as db:
            with db.conn.cursor() as cur:
                cur.execute(query, (event_id,))
                return cur.fetchone() is not None
    except Exception as e:
        logger.warning(f"Could not check event dedupe: {e}")
        return False


def record_event_processed(
    event_id: str,
    event_type: str,
    order_id: str,
    symbol: str,
    event_data: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Record that a WebSocket event has been processed.
    Returns True if successfully recorded, False if already exists.
    """
    query = """
    INSERT INTO alpaca_event_dedupe (
        event_id, event_type, order_id, symbol, event_data
    ) VALUES (
        %s, %s, %s, %s, %s::jsonb
    )
    ON CONFLICT (event_id) DO NOTHING
    """
    
    try:
        with DatabaseConnection() as db:
            with db.conn.cursor() as cur:
                cur.execute(query, (
                    event_id,
                    event_type,
                    order_id,
                    symbol,
                    json.dumps(event_data or {})
                ))
                inserted = cur.rowcount > 0
                if inserted:
                    db.conn.commit()
                return inserted
    except Exception as e:
        logger.error(f"Failed to record event dedupe: {e}")
        return False


def get_position_by_order_id(order_id: str) -> Optional[Dict[str, Any]]:
    """
    Get an active position by Alpaca order ID.
    Used to check if we've already created a position for this order.
    """
    query = """
    SELECT 
        id, execution_id, execution_uuid, ticker, instrument_type, strategy_type,
        side, quantity, entry_price, entry_time,
        strike_price, expiration_date, option_symbol,
        stop_loss, take_profit, max_hold_minutes,
        alpaca_order_id,
        status, created_at
    FROM active_positions
    WHERE alpaca_order_id = %s
    ORDER BY entry_time DESC
    LIMIT 1
    """
    
    try:
        with DatabaseConnection() as db:
            with db.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(query, (order_id,))
                result = cur.fetchone()
                return dict(result) if result else None
    except Exception as e:
        logger.warning(f"Could not fetch position by order_id: {e}")
        return None


def create_position_from_alpaca_with_order_id(
    ticker: str,
    instrument_type: str,
    side: str,
    quantity: float,
    entry_price: float,
    current_price: float,
    order_id: str,
    strike_price: Optional[float] = None,
    expiration_date: Optional[str] = None,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
    option_symbol: Optional[str] = None
) -> Optional[int]:
    """
    Create a new active position from Alpaca WebSocket with idempotency.
    Uses order_id to prevent duplicates.
    """
    # Check if position already exists for this order
    existing = get_position_by_order_id(order_id)
    if existing:
        logger.debug(f"Position already exists for order {order_id} (id={existing['id']})")
        return existing['id']
    
    # Also check by symbol to avoid duplicates from different sources
    symbol_key = option_symbol or ticker
    existing_by_symbol = get_position_by_symbol(symbol_key)
    if existing_by_symbol:
        logger.debug(f"Position for {symbol_key} already exists (id={existing_by_symbol['id']})")
        # Update with order_id if missing
        try:
            with DatabaseConnection() as db:
                with db.conn.cursor() as cur:
                    cur.execute(
                        "UPDATE active_positions SET alpaca_order_id = %s WHERE id = %s",
                        (order_id, existing_by_symbol['id'])
                    )
                    db.conn.commit()
        except Exception as e:
            logger.warning(f"Could not update order_id: {e}")
        return existing_by_symbol['id']

    query = """
    INSERT INTO active_positions (
        ticker, instrument_type, strategy_type,
        side, quantity, entry_price, entry_time,
        strike_price, expiration_date, option_symbol,
        stop_loss, take_profit, max_hold_minutes,
        current_price, status, original_quantity,
        alpaca_order_id,
        entry_features_json,
        entry_iv_rank,
        entry_spread_pct,
        best_unrealized_pnl_pct,
        worst_unrealized_pnl_pct,
        best_unrealized_pnl_dollars,
        worst_unrealized_pnl_dollars,
        last_mark_price
    ) VALUES (
        %s, %s, %s,
        %s, %s, %s, NOW(),
        %s, %s, %s,
        %s, %s, %s,
        %s, 'open', %s,
        %s,
        %s::jsonb,
        %s,
        %s,
        %s,
        %s,
        %s,
        %s,
        %s
    )
    ON CONFLICT (alpaca_order_id) DO NOTHING
    RETURNING id
    """
    
    try:
        with DatabaseConnection() as db:
            with db.conn.cursor() as cur:
                cur.execute(query, (
                    ticker,
                    instrument_type,
                    'swing_trade',  # Default strategy for Alpaca-synced positions
                    side,
                    quantity,
                    entry_price,
                    strike_price,
                    expiration_date,
                    option_symbol,
                    stop_loss,
                    take_profit,
                    240,  # Default 4 hour hold time
                    current_price,
                    quantity,  # original_quantity = quantity
                    order_id,
                    json.dumps({}),  # entry_features_json placeholder
                    None,  # entry_iv_rank
                    None,  # entry_spread_pct
                    0.0,   # best_unrealized_pnl_pct
                    0.0,   # worst_unrealized_pnl_pct
                    0.0,   # best_unrealized_pnl_dollars
                    0.0,   # worst_unrealized_pnl_dollars
                    current_price  # last_mark_price
                ))
                result = cur.fetchone()
                if result:
                    position_id = result[0]
                    db.conn.commit()
                    logger.info(f"Created position {position_id} from Alpaca WebSocket: {ticker} (order {order_id})")
                    return position_id
                else:
                    # Conflict occurred, fetch existing
                    existing = get_position_by_order_id(order_id)
                    return existing['id'] if existing else None
    except Exception as e:
        logger.error(f"Failed to create position from Alpaca: {e}")
        return None
