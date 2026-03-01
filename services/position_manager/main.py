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
    
    # Import account configuration
    from config import ACCOUNT_NAME
    logger.info(f"Managing positions for account: {ACCOUNT_NAME}")
    
    # Phase 17: Initialize bar fetcher for options learning
    from config import ALPACA_API_KEY, ALPACA_API_SECRET
    from bar_fetcher import OptionBarFetcher
    monitor.bar_fetcher = OptionBarFetcher(ALPACA_API_KEY, ALPACA_API_SECRET)
    logger.info("✓ Option bar fetcher initialized for AI learning")
    
    # Initialize EOD exit engine for this monitoring cycle
    try:
        monitor._eod_engine = monitor._init_eod_engine()
        if monitor._eod_engine:
            logger.info(f"✓ EOD exit engine initialized (tier={monitor._eod_engine.account_tier}, "
                        f"vix={monitor._eod_engine.vix_regime.effective_regime})")
        else:
            logger.warning("⚠ EOD engine not initialized, falling back to legacy close")
    except Exception as e:
        logger.warning(f"⚠ EOD engine init failed: {e}, falling back to legacy close")
        monitor._eod_engine = None

    # Initialize close-loop monitor
    try:
        from eod_config import EODConfig
        from close_loop import CloseLoopMonitor
        account_tier = 'tiny' if ACCOUNT_NAME == 'tiny' else 'large'
        eod_config = EODConfig.for_account_tier(account_tier)
        monitor._close_loop_monitor = CloseLoopMonitor(eod_config)
        logger.info("✓ Close-loop monitor initialized")
    except Exception as e:
        logger.warning(f"⚠ Close-loop monitor init failed: {e}")
        monitor._close_loop_monitor = None
    
    try:
        # Step 1: FIRST sync from database executions (has features from recommendation JOIN)
        # CRITICAL: This must run before Alpaca sync so positions get entry_features_json
        sync_since = start_time - timedelta(minutes=10)
        logger.info(f"Step 1: Syncing positions from executions since {sync_since.strftime('%H:%M:%S')}")
        
        new_count = monitor.sync_new_positions(sync_since, ACCOUNT_NAME)
        if new_count > 0:
            logger.info(f"✓ Created {new_count} new position(s) from filled executions")
        else:
            logger.info("No new positions to create from database")
        
        # Step 2: THEN sync from Alpaca API to catch manual trades and logging gaps
        # These won't have features (no recommendation), which is correct
        logger.info("\nStep 2: Syncing from Alpaca API...")
        alpaca_synced = monitor.sync_from_alpaca_positions()
        if alpaca_synced > 0:
            logger.info(f"✓ Synced {alpaca_synced} position(s) from Alpaca")
        
        # Step 2b: Clean up positions stuck in 'closing' for >30 minutes
        cleaned = db.cleanup_stuck_closing(ACCOUNT_NAME, max_age_minutes=30)
        if cleaned > 0:
            logger.warning(f"⚠ Cleaned up {cleaned} stuck 'closing' position(s)")
        
        # Step 3: Get all open positions for THIS account only
        logger.info(f"\nFetching open positions for account: {ACCOUNT_NAME}")
        open_positions = db.get_open_positions(account_name=ACCOUNT_NAME)
        
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
        
        # Step 4: Check close-loop integrity before exit evaluation
        if monitor._close_loop_monitor:

            # Log overnight outcomes for positions held overnight (R6.4)
            try:
                outcome_count = monitor.log_overnight_outcomes(open_positions)
                if outcome_count > 0:
                    logger.info(f"✓ Logged {outcome_count} overnight outcome(s)")
            except Exception as e:
                logger.error(f"Overnight outcome logging failed: {e}")

            try:
                stuck_actions = monitor._close_loop_monitor.check_stuck_positions(open_positions)
                for action in stuck_actions:
                    logger.warning(f"  Close-loop: position {action.position_id} → {action.action}: {action.reason}")
                    db.log_position_event(action.position_id, f'close_{action.action}', {
                        'action': action.action, 'reason': action.reason,
                    })

                dup_actions = monitor._close_loop_monitor.detect_duplicates(open_positions)
                for action in dup_actions:
                    logger.warning(f"  Duplicate: position {action.position_id} → {action.action}: {action.reason}")
                    db.log_position_event(action.position_id, 'duplicate_cleanup', {
                        'action': action.action, 'reason': action.reason,
                    })
            except Exception as e:
                logger.error(f"Close-loop check failed: {e}")

        # Step 5: Monitor each position
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
        
        # Step 6: Log final summary
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
        raise  # Re-raise so the outer loop can catch and retry


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
                logger.info("Sleeping for 1 minute until next check...")
                time.sleep(60)  # 1 minute - CRITICAL: was 300s, positions were closing in 4 min before we could monitor!
            except KeyboardInterrupt:
                logger.info("Shutting down gracefully...")
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                logger.info("Waiting 1 minute before retry...")
                time.sleep(60)
