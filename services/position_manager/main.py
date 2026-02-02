"""
Position Manager - Main orchestration
Runs every 1 minute to monitor and manage all open positions
"""
import logging
import sys
from datetime import datetime, timedelta, timezone

import monitor
import exits
import db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)


def main():
    """
    Main position manager loop
    
    Flow:
    1. Sync new positions from filled executions
    2. Get all open positions
    3. For each position:
       - Update current price
       - Check for partial fills
       - Check exit conditions
       - Force close if needed
    4. Log summary
    """
    start_time = datetime.now(timezone.utc)
    logger.info("=" * 80)
    logger.info("Position Manager starting")
    logger.info(f"Run time: {start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    logger.info("=" * 80)
    
    # Phase 17: Initialize bar fetcher for options learning
    from config import ALPACA_API_KEY, ALPACA_API_SECRET
    from bar_fetcher import OptionBarFetcher
    monitor.bar_fetcher = OptionBarFetcher(ALPACA_API_KEY, ALPACA_API_SECRET)
    logger.info("✓ Option bar fetcher initialized for AI learning")
    
    try:
        # Step 1: FIRST sync positions directly from Alpaca API (Phase 3 Fix)
        # This catches ALL positions including manual trades and logging gaps
        logger.info("Step 1: Syncing from Alpaca API...")
        alpaca_synced = monitor.sync_from_alpaca_positions()
        if alpaca_synced > 0:
            logger.info(f"✓ Synced {alpaca_synced} position(s) from Alpaca")
        
        # Step 2: THEN sync new positions from recent executions in our database
        # Look back 10 minutes to catch any executions since last run
        sync_since = start_time - timedelta(minutes=10)
        logger.info(f"\nStep 2: Syncing positions from executions since {sync_since.strftime('%H:%M:%S')}")
        
        new_count = monitor.sync_new_positions(sync_since)
        if new_count > 0:
            logger.info(f"✓ Created {new_count} new position(s) from filled executions")
        else:
            logger.info("No new positions to create from database")
        
        # Step 2: Get all open positions
        logger.info("\nFetching open positions...")
        open_positions = db.get_open_positions()
        
        if not open_positions:
            logger.info("No open positions to monitor")
            logger.info("=" * 80)
            logger.info("Position Manager completed successfully")
            logger.info("=" * 80)
            return
        
        logger.info(f"✓ Found {len(open_positions)} open position(s)")
        
        # Log position summary
        logger.info("\nPosition Summary:")
        logger.info("-" * 80)
        for pos in open_positions:
            logger.info(
                f"  {pos['id']}: {pos['ticker']} {pos['instrument_type']} "
                f"({pos['strategy_type']}) - "
                f"Entry: ${pos['entry_price']:.2f}, "
                f"Stop: ${pos['stop_loss']:.2f}, "
                f"Target: ${pos['take_profit']:.2f}"
            )
        logger.info("-" * 80)
        
        # Step 3: Monitor each position
        positions_closed = 0
        positions_updated = 0
        positions_errored = 0
        
        for position in open_positions:
            position_id = position['id']
            ticker = position['ticker']
            
            try:
                logger.info(f"\n▶ Processing position {position_id} ({ticker})...")
                
                # Update price and P&L
                price_updated = monitor.update_position_price(position)
                
                if not price_updated:
                    logger.warning(f"  ⚠ Could not update price for {ticker}")
                    positions_errored += 1
                    continue
                
                logger.info(
                    f"  Price: ${position['current_price']:.2f}, "
                    f"P&L: ${position.get('current_pnl_dollars', 0):.2f} "
                    f"({position.get('current_pnl_percent', 0):.2f}%)"
                )
                positions_updated += 1
                
                # Check for partial fills
                actual_qty = monitor.check_partial_fill(position)
                if actual_qty is not None:
                    logger.info(f"  ⚠ Partial fill detected: handling quantity adjustment")
                    exits.handle_partial_fill(position, actual_qty)
                
                # Check exit conditions
                exit_triggers = monitor.check_exit_conditions(position)
                
                if exit_triggers:
                    # Exit triggered
                    top_trigger = exit_triggers[0]
                    logger.warning(
                        f"  🚨 EXIT TRIGGERED: {top_trigger['message']}"
                    )
                    
                    # Check if it's a partial exit
                    if top_trigger.get('type') == 'partial':
                        # Partial exit - close some, keep rest
                        quantity_to_close = top_trigger['quantity']
                        
                        success = exits.execute_partial_exit(
                            position,
                            quantity_to_close,
                            top_trigger['reason']
                        )
                        
                        if success:
                            logger.info(
                                f"  ✓ Partial exit executed: "
                                f"closed {quantity_to_close}, position continues"
                            )
                            positions_updated += 1
                        else:
                            logger.error(f"  ✗ Partial exit failed for position {position_id}")
                            positions_errored += 1
                    else:
                        # Full exit - close entire position
                        success = exits.force_close_position(
                            position,
                            top_trigger['reason'],
                            top_trigger['priority']
                        )
                        
                        if success:
                            logger.info(f"  ✓ Position {position_id} closed successfully")
                            positions_closed += 1
                        else:
                            logger.error(f"  ✗ Failed to close position {position_id}")
                            positions_errored += 1
                else:
                    logger.info(f"  ✓ No exits triggered, position healthy")
                
            except Exception as e:
                logger.error(f"  ✗ Error processing position {position_id}: {e}")
                positions_errored += 1
        
        # Step 4: Log final summary
        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()
        
        logger.info("\n" + "=" * 80)
        logger.info("Position Manager Summary")
        logger.info("=" * 80)
        logger.info(f"Total positions monitored: {len(open_positions)}")
        logger.info(f"Positions updated:         {positions_updated}")
        logger.info(f"Positions closed:          {positions_closed}")
        logger.info(f"Positions with errors:     {positions_errored}")
        logger.info(f"Duration:                  {duration:.2f} seconds")
        logger.info("=" * 80)
        
        if positions_errored > 0:
            logger.warning("⚠ Some positions encountered errors - check logs above")
        else:
            logger.info("✓ All positions processed successfully")
        
        logger.info("Position Manager completed")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"FATAL ERROR in position manager: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    import time
    import os
    
    # Run mode: ONCE (for testing) or LOOP (for ECS Service)
    run_mode = os.getenv('RUN_MODE', 'LOOP')
    
    if run_mode == 'ONCE':
        logger.info("Running in ONCE mode (single execution)")
        main()
    else:
        logger.info("Running in LOOP mode (ECS Service)")
        logger.info("Will check positions every 5 minutes")
        
        while True:
            try:
                main()
                logger.info("Sleeping for 5 minutes until next check...")
                time.sleep(300)  # 5 minutes
            except KeyboardInterrupt:
                logger.info("Shutting down gracefully...")
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                logger.info("Waiting 1 minute before retry...")
                time.sleep(60)
