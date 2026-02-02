#!/usr/bin/env python3
"""
Classification Worker - Main Entry Point
Continuously polls and classifies unprocessed financial news events
"""

import json
import time
import sys
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from config import load_config
from db import DatabaseClient
from nlp.model import SentimentClassifier
from nlp.tickers import extract_tickers, format_text_for_classification
from nlp.ai_ticker_inference import TickerInferenceClient

# Run mode: 'batch' (scheduled task) or 'service' (24/7)
RUN_MODE = os.environ.get('RUN_MODE', 'batch')
MAX_BATCH_ITERATIONS = int(os.environ.get('MAX_BATCH_ITERATIONS', '10'))

def log(event: str, **kwargs):
    """Structured JSON logging"""
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **kwargs
    }
    print(json.dumps(log_entry), flush=True)

def process_event(
    event: Dict[str, Any],
    classifier: SentimentClassifier,
    ticker_whitelist: list,
    ai_inference: Optional[TickerInferenceClient] = None
) -> Dict[str, Any]:
    """
    Process single event: classify sentiment and extract tickers
    
    Args:
        event: Event dictionary from database
        classifier: Sentiment classifier instance
        ticker_whitelist: List of valid ticker symbols
        ai_inference: Optional AI ticker inference client
        
    Returns:
        Classification result dictionary
    """
    try:
        # Combine title and summary
        text = format_text_for_classification(
            event['title'],
            event.get('summary', '')
        )
        
        # Classify sentiment
        sentiment, score = classifier.classify(text)
        
        # Extract tickers via regex
        tickers = extract_tickers(text, ticker_whitelist)
        
        # If no tickers found and AI inference available, use it
        if not tickers and ai_inference:
            ai_tickers = ai_inference.infer_with_fallback(
                event['title'],
                event.get('summary', ''),
                ticker_whitelist,
                timeout_seconds=3
            )
            if ai_tickers:
                tickers = ai_tickers
                log("ai_ticker_inference_used",
                    event_id=event['id'],
                    inferred_tickers=ai_tickers)
        
        return {
            'raw_event_id': event['id'],
            'sentiment': sentiment,
            'sentiment_score': score,
            'extracted_tickers': tickers,
            'error': None
        }
        
    except Exception as e:
        log("process_event_error", 
            event_id=event['id'],
            error=str(e),
            error_type=type(e).__name__)
        
        return {
            'raw_event_id': event['id'],
            'sentiment': 'neutral',
            'sentiment_score': 0.0,
            'extracted_tickers': [],
            'error': str(e)
        }

def process_batch(
    events: list,
    classifier: SentimentClassifier,
    db_client: DatabaseClient,
    config: dict,
    ai_inference: Optional[TickerInferenceClient] = None
) -> Dict[str, int]:
    """
    Process batch of events
    
    Args:
        events: List of event dictionaries
        classifier: Sentiment classifier
        db_client: Database client
        config: Configuration dictionary
        
    Returns:
        Statistics dictionary
    """
    start_time = time.time()
    
    stats = {
        'processed': 0,
        'inserted': 0,
        'duplicates': 0,
        'errors': 0
    }
    
    try:
        for event in events:
            # Process event
            result = process_event(event, classifier, config['tickers'], ai_inference)
            
            # Save to database
            inserted = db_client.save_classification(
                raw_event_id=result['raw_event_id'],
                sentiment=result['sentiment'],
                sentiment_score=result['sentiment_score'],
                extracted_tickers=result['extracted_tickers'],
                error=result['error']
            )
            
            stats['processed'] += 1
            
            if inserted:
                stats['inserted'] += 1
            else:
                stats['duplicates'] += 1
            
            if result['error']:
                stats['errors'] += 1
        
        # Commit transaction
        db_client.commit()
        
        latency_ms = (time.time() - start_time) * 1000
        
        log("batch_processed",
            batch_size=len(events),
            processed=stats['processed'],
            inserted=stats['inserted'],
            duplicates=stats['duplicates'],
            errors=stats['errors'],
            latency_ms=round(latency_ms, 2))
        
        return stats
        
    except Exception as e:
        # Rollback on batch failure
        db_client.rollback()
        
        log("batch_error",
            batch_size=len(events),
            error=str(e),
            error_type=type(e).__name__)
        
        stats['errors'] = len(events)
        return stats

def main():
    """
    Main worker loop
    Continuously processes unprocessed events
    """
    log("classifier_worker_start")
    
    try:
        # Load configuration
        config = load_config()
        log("config_loaded",
            batch_size=config['batch_size'],
            poll_seconds=config['poll_seconds'],
            ticker_count=len(config['tickers']))
        
        # Initialize database client
        db_client = DatabaseClient(config['db'])
        db_client.connect()
        log("db_connected")
        
        # Initialize and load sentiment model
        log("model_loading", model_name=config['model_name'])
        classifier = SentimentClassifier(config['model_name'])
        classifier.load_model()
        log("model_loaded", model_name=config['model_name'])
        
        # Initialize AI ticker inference (optional, graceful fallback if unavailable)
        try:
            ai_inference = TickerInferenceClient()
            log("ai_inference_enabled", model="claude-3-haiku")
        except Exception as e:
            ai_inference = None
            log("ai_inference_disabled", reason=str(e))
        
        # Main processing loop
        total_processed = 0
        idle_cycles = 0
        iterations = 0
        
        # In batch mode, process for limited iterations then exit
        # In service mode, loop forever
        while True:
            iterations += 1
            
            # Batch mode: exit after max iterations or when idle
            if RUN_MODE == 'batch' and iterations > MAX_BATCH_ITERATIONS:
                log("batch_mode_complete", 
                    iterations=iterations,
                    total_processed=total_processed)
                break
            try:
                # Check unprocessed count
                unprocessed_count = db_client.get_unprocessed_count()
                
                if unprocessed_count == 0:
                    idle_cycles += 1
                    
                    # In batch mode, exit if no work
                    if RUN_MODE == 'batch':
                        log("batch_mode_no_work",
                            total_processed=total_processed)
                        break
                    
                    # In service mode, log and sleep
                    if idle_cycles % 12 == 1:  # Log every minute when idle
                        log("worker_idle",
                            unprocessed=unprocessed_count,
                            total_processed=total_processed)
                    
                    time.sleep(config['poll_seconds'])
                    continue
                
                # Reset idle counter
                idle_cycles = 0
                
                # Claim batch using SKIP LOCKED
                events = db_client.claim_unprocessed_batch(config['batch_size'])
                
                if not events:
                    # No events claimed (another worker got them)
                    log("batch_empty", unprocessed=unprocessed_count)
                    time.sleep(config['poll_seconds'])
                    continue
                
                log("batch_claimed",
                    batch_size=len(events),
                    unprocessed=unprocessed_count)
                
                # Process batch
                stats = process_batch(events, classifier, db_client, config, ai_inference)
                
                total_processed += stats['processed']
                
                log("worker_stats",
                    total_processed=total_processed,
                    unprocessed_remaining=unprocessed_count - len(events))
                
            except KeyboardInterrupt:
                log("worker_shutdown", reason="keyboard_interrupt")
                break
                
            except Exception as e:
                log("worker_loop_error",
                    error=str(e),
                    error_type=type(e).__name__)
                time.sleep(config['poll_seconds'])
        
        # Cleanup
        db_client.close()
        log("classifier_worker_stopped", total_processed=total_processed)
        sys.exit(0)
        
    except Exception as e:
        log("classifier_worker_failed",
            error=str(e),
            error_type=type(e).__name__)
        sys.exit(1)

if __name__ == '__main__':
    main()
