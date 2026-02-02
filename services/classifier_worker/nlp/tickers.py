"""
Ticker symbol extraction from financial text
Uses regex patterns and whitelist validation
"""

import re
from typing import List, Set

# Regex patterns for ticker extraction
DOLLAR_TICKER_PATTERN = re.compile(r'\$([A-Z]{1,5})\b')  # Matches $AAPL, $TSLA
PLAIN_TICKER_PATTERN = re.compile(r'\b([A-Z]{2,5})\b')   # Matches plain AAPL, TSLA

def extract_tickers(text: str, ticker_whitelist: List[str]) -> List[str]:
    """
    Extract ticker symbols from text using regex patterns
    
    Args:
        text: Input text (title + summary)
        ticker_whitelist: List of valid ticker symbols
        
    Returns:
        List of unique ticker symbols found (validated against whitelist)
    """
    if not text:
        return []
    
    # Convert whitelist to set for O(1) lookups
    valid_tickers = set(ticker_whitelist)
    found_tickers: Set[str] = set()
    
    # Extract tickers with $ prefix (high confidence)
    dollar_matches = DOLLAR_TICKER_PATTERN.findall(text)
    for ticker in dollar_matches:
        if ticker in valid_tickers:
            found_tickers.add(ticker)
    
    # Extract plain uppercase words (potential tickers)
    # Only add if they're in the whitelist to avoid false positives
    plain_matches = PLAIN_TICKER_PATTERN.findall(text)
    for ticker in plain_matches:
        if ticker in valid_tickers:
            found_tickers.add(ticker)
    
    # Return sorted list for consistency
    return sorted(list(found_tickers))

def format_text_for_classification(title: str, summary: str) -> str:
    """
    Combine title and summary into single text for classification
    
    Args:
        title: Event title
        summary: Event summary (may be None)
        
    Returns:
        Combined text string
    """
    if summary:
        return f"{title} {summary}"
    return title
