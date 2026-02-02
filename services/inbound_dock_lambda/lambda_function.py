import json
import hashlib
import boto3
import psycopg2
import feedparser
from datetime import datetime
from dateutil import parser as date_parser

def log(event, **kwargs):
    """Structured JSON logging"""
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "event": event,
        **kwargs
    }
    print(json.dumps(log_entry), flush=True)

def get_config():
    """Load configuration from AWS"""
    ssm = boto3.client('ssm', region_name='us-west-2')
    secrets = boto3.client('secretsmanager', region_name='us-west-2')
    
    # Get RSS feeds
    feeds_param = ssm.get_parameter(Name='/ops-pipeline/rss_feeds')
    feeds = json.loads(feeds_param['Parameter']['Value'])
    
    # Get DB connection details
    db_host = ssm.get_parameter(Name='/ops-pipeline/db_host')['Parameter']['Value']
    db_port = ssm.get_parameter(Name='/ops-pipeline/db_port')['Parameter']['Value']
    db_name = ssm.get_parameter(Name='/ops-pipeline/db_name')['Parameter']['Value']
    
    # Get DB credentials
    secret_value = secrets.get_secret_value(SecretId='ops-pipeline/db')
    secret_data = json.loads(secret_value['SecretString'])
    
    return {
        'feeds': feeds,
        'db': {
            'host': db_host,
            'port': int(db_port),
            'database': db_name,
            'user': secret_data['username'],
            'password': secret_data['password']
        }
    }

def compute_event_uid(entry):
    """
    Compute stable event UID from feed entry
    Priority: GUID > link > title+published
    """
    if hasattr(entry, 'id') and entry.id:
        source = entry.id
    elif hasattr(entry, 'link') and entry.link:
        source = entry.link
    else:
        title = entry.get('title', '')
        published = entry.get('published', '')
        source = f"{title}:{published}"
    
    return hashlib.sha256(source.encode('utf-8')).hexdigest()

def parse_published_date(entry):
    """Extract and parse published date from entry"""
    try:
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            return datetime(*entry.published_parsed[:6])
        elif hasattr(entry, 'published') and entry.published:
            return date_parser.parse(entry.published)
        elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
            return datetime(*entry.updated_parsed[:6])
        elif hasattr(entry, 'updated') and entry.updated:
            return date_parser.parse(entry.updated)
    except Exception as e:
        log("date_parse_error", error=str(e))
    
    return None

def fetch_feed(feed_url, max_retries=3):
    """Fetch and parse RSS feed with retries"""
    for attempt in range(max_retries):
        try:
            log("feed_fetch_start", feed_url=feed_url, attempt=attempt+1)
            
            feed = feedparser.parse(feed_url)
            
            if feed.bozo and feed.bozo_exception:
                log("feed_parse_warning", 
                    feed_url=feed_url, 
                    error=str(feed.bozo_exception))
            
            log("feed_fetch_success", 
                feed_url=feed_url, 
                entries=len(feed.entries))
            
            return feed
            
        except Exception as e:
            log("feed_fetch_error", 
                feed_url=feed_url, 
                attempt=attempt+1, 
                error=str(e))
            
            if attempt == max_retries - 1:
                return None
    
    return None

def process_feed(conn, feed_url, feed):
    """Process feed entries and insert into database"""
    if not feed or not feed.entries:
        log("feed_empty", feed_url=feed_url)
        return 0
    
    new_items = 0
    
    for entry in feed.entries:
        try:
            # Compute stable event UID
            event_uid = compute_event_uid(entry)
            
            # Extract fields
            published_at = parse_published_date(entry)
            title = entry.get('title', 'No title')
            link = entry.get('link', None)
            summary = entry.get('summary', entry.get('description', None))
            
            # Insert into database (deduplication via UNIQUE constraint)
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO inbound_events_raw 
                        (event_uid, published_at, source, title, link, summary, fetched_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (event_uid) DO NOTHING
                """, (event_uid, published_at, feed_url, title, link, summary))
                
                if cursor.rowcount > 0:
                    new_items += 1
            
        except Exception as e:
            log("entry_insert_error", 
                feed_url=feed_url, 
                event_uid=event_uid if 'event_uid' in locals() else None,
                error=str(e))
    
    conn.commit()
    
    # Update feed state
    try:
        etag = feed.get('etag', None)
        last_modified = feed.get('modified', None)
        
        # Find most recent published date from entries
        published_dates = [parse_published_date(e) for e in feed.entries]
        published_dates = [d for d in published_dates if d is not None]
        last_seen_published = max(published_dates) if published_dates else None
        
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO feed_state (feed_url, etag, last_modified, last_seen_published, updated_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (feed_url) 
                DO UPDATE SET 
                    etag = EXCLUDED.etag,
                    last_modified = EXCLUDED.last_modified,
                    last_seen_published = EXCLUDED.last_seen_published,
                    updated_at = NOW()
            """, (feed_url, etag, last_modified, last_seen_published))
        
        conn.commit()
        
    except Exception as e:
        log("feed_state_update_error", feed_url=feed_url, error=str(e))
    
    return new_items

def lambda_handler(event, context):
    """
    RSS Ingestion Lambda - Polls RSS feeds and stores items
    Runs every 1 minute via EventBridge
    """
    
    log("inbound_dock_start")
    
    try:
        # Load configuration
        config = get_config()
        log("config_loaded", feed_count=len(config['feeds']))
        
        # Connect to database
        conn = psycopg2.connect(**config['db'], connect_timeout=10)
        log("db_connected")
        
        # Process each feed
        total_new_items = 0
        feeds_polled = 0
        errors = 0
        
        for feed_url in config['feeds']:
            try:
                feed = fetch_feed(feed_url)
                
                if feed:
                    new_items = process_feed(conn, feed_url, feed)
                    total_new_items += new_items
                    feeds_polled += 1
                    
                    log("feed_processed", 
                        feed_url=feed_url, 
                        new_items=new_items,
                        total_entries=len(feed.entries))
                else:
                    errors += 1
                    log("feed_failed", feed_url=feed_url)
                    
            except Exception as e:
                errors += 1
                log("feed_error", feed_url=feed_url, error=str(e))
        
        conn.close()
        
        # Final summary
        result = {
            "success": True,
            "feeds_polled": feeds_polled,
            "new_items_inserted": total_new_items,
            "errors": errors,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        log("inbound_dock_complete", **result)
        
        return {
            'statusCode': 200,
            'body': json.dumps(result)
        }
        
    except Exception as e:
        error_msg = str(e)
        log("inbound_dock_failed", error=error_msg, error_type=type(e).__name__)
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'success': False,
                'error': error_msg
            })
        }
