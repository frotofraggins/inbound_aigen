"""
Trade Stream WebSocket Service
Connects to Alpaca WebSocket for real-time trade updates
Syncs positions instantly when trades fill (<1 second latency)
"""
import asyncio
import contextlib
import logging
import sys
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from alpaca.trading.stream import TradingStream

import db
import config

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Alpaca WebSocket stream
stream = TradingStream(
    api_key=config.ALPACA_API_KEY,
    secret_key=config.ALPACA_API_SECRET,
    paper=config.IS_PAPER_TRADING
)

def _alpaca_headers() -> dict:
    return {
        "APCA-API-KEY-ID": config.ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": config.ALPACA_API_SECRET,
        "Accept": "application/json"
    }


def _parse_activity_time(value: str):
    if not value:
        return None
    try:
        if "T" in value:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return datetime.fromisoformat(f"{value}T00:00:00+00:00")
    except Exception:
        return None


def fetch_account_activities(after=None):
    """
    Fetch recent account activities via REST.
    Uses 'after' as a moving cursor and relies on DB upsert for idempotency.
    """
    params = {
        "page_size": config.ACCOUNT_ACTIVITY_PAGE_SIZE,
        "direction": "desc"
    }
    if after:
        if after.tzinfo is None:
            after = after.replace(tzinfo=timezone.utc)
        after_str = after.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        params["after"] = after_str

    base_url = config.ALPACA_BASE_URL.rstrip("/")
    url = f"{base_url}/v2/account/activities?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers=_alpaca_headers(), method="GET")

    with urllib.request.urlopen(request, timeout=10) as response:
        payload = response.read().decode("utf-8")
        data = json.loads(payload)

    return data if isinstance(data, list) else data.get("activities", [])


async def poll_account_activities():
    """
    Periodically pull account activities for learning/audit storage.
    """
    cursor_time = db.get_latest_account_activity_time()
    if cursor_time:
        cursor_time = cursor_time - timedelta(minutes=5)
    else:
        cursor_time = datetime.now(timezone.utc) - timedelta(days=config.ACCOUNT_ACTIVITY_LOOKBACK_DAYS)

    while True:
        try:
            activities = await asyncio.to_thread(fetch_account_activities, after=cursor_time)
            inserted = 0
            newest_time = cursor_time

            for activity in reversed(activities):
                if db.insert_account_activity(activity, account_name=config.ACCOUNT_NAME):
                    inserted += 1
                ts = _parse_activity_time(activity.get("transaction_time") or activity.get("date"))
                if ts and (newest_time is None or ts > newest_time):
                    newest_time = ts

            if newest_time and cursor_time and newest_time > cursor_time:
                cursor_time = newest_time - timedelta(seconds=1)

            if activities or inserted:
                logger.info(f"📥 Account activities: fetched={len(activities)} inserted={inserted}")
        except Exception as e:
            logger.error(f"❌ Account activity poll failed: {e}", exc_info=True)

        await asyncio.sleep(config.ACCOUNT_ACTIVITY_POLL_SECONDS)

def parse_option_symbol(symbol: str):
    """
    Parse option symbol from Alpaca format
    Example: AAPL250131C00150000
    Returns: (ticker, strike_price, exp_date, instrument_type)
    """
    if len(symbol) <= 10:
        # Stock symbol
        return symbol, None, None, 'STOCK'
    
    # Option symbol format: TICKER + YYMMDD + C/P + 8-digit strike
    strike_str = symbol[-8:]  # Last 8 chars
    opt_type = symbol[-9]  # C or P
    exp_str = symbol[-15:-9]  # YYMMDD
    ticker = symbol[:-15].strip()
    
    # Parse values
    strike_price = int(strike_str) / 1000.0
    exp_date = f"20{exp_str[0:2]}-{exp_str[2:4]}-{exp_str[4:6]}"
    instrument_type = 'CALL' if opt_type == 'C' else 'PUT'
    
    return ticker, strike_price, exp_date, instrument_type


async def handle_trade_update(data):
    """
    Handle real-time trade updates from Alpaca
    Syncs positions instantly when orders fill
    """
    try:
        event = data.event
        order = data.order
        
        logger.info("=" * 80)
        logger.info(f"📨 TRADE EVENT: {event}")
        logger.info(f"   Symbol: {order.symbol}")
        logger.info(f"   Order ID: {order.id}")
        logger.info(f"   Status: {order.status}")
        
        if event == 'fill':
            logger.info(f"✅ ORDER FILLED - Syncing position...")
            
            # Parse symbol
            ticker, strike_price, exp_date, instrument_type = parse_option_symbol(order.symbol)
            is_option = instrument_type in ['CALL', 'PUT']
            
            # Get fill details
            qty = float(order.filled_qty)
            entry_price = float(order.filled_avg_price)
            
            logger.info(f"   Ticker: {ticker}")
            logger.info(f"   Type: {instrument_type}")
            logger.info(f"   Qty: {qty}")
            logger.info(f"   Fill Price: ${entry_price:.2f}")
            
            if is_option:
                logger.info(f"   Strike: ${strike_price}")
                logger.info(f"   Expiry: {exp_date}")
            
            # Calculate stops based on instrument type
            if is_option:
                stop_loss = entry_price * 0.75  # -25% for options
                take_profit = entry_price * 1.50  # +50% for options
            else:
                stop_loss = entry_price * 0.98  # -2% for stocks
                take_profit = entry_price * 1.03  # +3% for stocks
            
            # Sync to database INSTANTLY
            position_id = db.create_position_from_alpaca(
                ticker=ticker,
                instrument_type=instrument_type,
                side='long',
                quantity=qty,
                entry_price=entry_price,
                current_price=entry_price,
                strike_price=strike_price,
                expiration_date=exp_date,
                stop_loss=stop_loss,
                take_profit=take_profit,
                option_symbol=order.symbol if is_option else None
            )
            
            logger.info(f"✅ Position {position_id} synced in REAL-TIME")
            logger.info(f"   Stop Loss: ${stop_loss:.2f}")
            logger.info(f"   Take Profit: ${take_profit:.2f}")
            
            # Log WebSocket event
            db.log_position_event(
                position_id,
                'synced_realtime_websocket',
                {
                    'order_id': str(order.id),
                    'filled_at': str(order.filled_at),
                    'latency': '<1 second',
                    'method': 'websocket_trade_stream'
                }
            )
            
            logger.info("=" * 80)
            
        elif event == 'partial_fill':
            logger.warning(f"⚠️ PARTIAL FILL: {order.filled_qty}/{order.qty}")
            logger.info(f"   Waiting for full fill...")
            
        elif event == 'canceled':
            logger.info(f"❌ ORDER CANCELED: {order.symbol}")
            
        elif event == 'rejected':
            logger.error(f"🚫 ORDER REJECTED: {order.symbol}")
            logger.error(f"   Reason: {order.status}")
            
        elif event == 'new':
            logger.info(f"🆕 NEW ORDER: {order.symbol}")
            logger.info(f"   Qty: {order.qty}")
            logger.info(f"   Type: {order.type}")
            
    except Exception as e:
        logger.error(f"❌ Error handling trade update: {e}", exc_info=True)


async def main():
    """
    Run WebSocket stream forever
    Auto-reconnects on disconnect
    """
    logger.info("=" * 80)
    logger.info("🚀 Trade Stream WebSocket Service")
    logger.info(f"   Started: {datetime.now()}")
    logger.info(f"   Mode: {'PAPER' if config.IS_PAPER_TRADING else 'LIVE'} Trading")
    logger.info(f"   Endpoint: {config.ALPACA_BASE_URL}")
    logger.info("=" * 80)
    logger.info("📡 Connecting to Alpaca WebSocket...")
    
    activity_task = asyncio.create_task(poll_account_activities())
    stream.subscribe_trade_updates(handle_trade_update)

    try:
        # Run forever - auto-reconnects
        await stream._run_forever()
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down gracefully...")
    except Exception as e:
        logger.error(f"💥 FATAL ERROR: {e}", exc_info=True)
        sys.exit(1)
    finally:
        activity_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await activity_task


if __name__ == "__main__":
    asyncio.run(main())
