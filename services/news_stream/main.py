"""
News Stream WebSocket Service
Connects to Alpaca News WebSocket for real-time breaking news
Complements RSS feeds with instant professional news sources
"""
import asyncio
import logging
import sys
import json
from datetime import datetime, timezone
from alpaca.data.live import NewsDataStream

import db
import config

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Alpaca News WebSocket stream
news_stream = NewsDataStream(
    api_key=config.ALPACA_API_KEY,
    secret_key=config.ALPACA_API_SECRET
)

# Track news processing stats
news_stats = {
    'total_received': 0,
    'stored': 0,
    'duplicates': 0,
    'errors': 0
}


async def handle_news(news_item):
    """
    Handle real-time news from Alpaca News WebSocket
    
    Sources: Benzinga, Reuters, and other professional feeds
    Updates instantly as news breaks (not 5-minute RSS delay)
    """
    try:
        news_stats['total_received'] += 1
        
        logger.info("=" * 80)
        logger.info(f"📰 BREAKING NEWS: {news_item.headline}")
        logger.info(f"   Source: {news_item.source}")
        logger.info(f"   Symbols: {', '.join(news_item.symbols)}")
        logger.info(f"   Time: {news_item.created_at}")
        
        # Store in database (uses same schema as RSS news)
        news_id = db.store_news_item({
            'source': news_item.source,
            'title': news_item.headline,
            'summary': news_item.summary or '',
            'content': news_item.content or '',
            'author': news_item.author or 'Unknown',
            'url': news_item.url,
            'published_at': news_item.created_at,
            'tickers': news_item.symbols,
            'external_id': str(news_item.id),
            'source_type': 'alpaca_websocket'
        })
        
        if news_id:
            news_stats['stored'] += 1
            logger.info(f"✅ Stored as news ID: {news_id}")
            logger.info(f"   Tickers affected: {len(news_item.symbols)}")
            
            # Queue for sentiment analysis (classifier will pick it up)
            # Same flow as RSS news - goes to classifier_worker
            for ticker in news_item.symbols:
                logger.debug(f"   Will analyze sentiment for {ticker}")
            
            # Log stats periodically
            if news_stats['stored'] % 10 == 0:
                logger.info(f"📊 Stats: {news_stats}")
        else:
            news_stats['duplicates'] += 1
            logger.debug(f"⚠️ Duplicate news (already in database)")
        
        logger.info("=" * 80)
        
    except Exception as e:
        news_stats['errors'] += 1
        logger.error(f"❌ Error processing news: {e}", exc_info=True)


async def main():
    """
    Run News WebSocket stream forever
    Auto-reconnects on disconnect
    """
    logger.info("=" * 80)
    logger.info("🚀 News Stream WebSocket Service")
    logger.info(f"   Started: {datetime.now(timezone.utc)}")
    logger.info(f"   Source: Alpaca News API")
    logger.info(f"   Mode: Real-time streaming")
    logger.info("=" * 80)
    logger.info("📡 Connecting to Alpaca News WebSocket...")
    
    # Subscribe to news handler
    news_stream.subscribe_news(handle_news, '*')  # All news
    
    try:
        # Run forever - auto-reconnects on disconnect
        logger.info("✅ WebSocket connected - listening for news...")
        await news_stream._run_forever()
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down gracefully...")
    except Exception as e:
        logger.error(f"💥 FATAL ERROR: {e}", exc_info=True)
        logger.error(f"Final stats: {news_stats}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
