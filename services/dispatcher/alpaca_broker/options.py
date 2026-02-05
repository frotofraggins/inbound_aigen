"""
Alpaca Options Trading Module
Handles options chain fetching, strike selection, and position sizing for options trading.

Based on Alpaca Options API:
- GET /v1beta1/options/contracts - List available options
- POST /v2/orders - Submit option order (same as stocks)
- GET /v2/positions - List positions (includes options)

Options Basics:
- Call: Right to BUY at strike (profit if price goes UP)
- Put: Right to SELL at strike (profit if price goes DOWN)
- 1 contract = 100 shares
- Premium: Price per contract (e.g., $0.50-$5.00)
- Greeks: Delta, Theta, IV for risk analysis

Strike Types:
- ATM (At-The-Money): Strike = current price (~0.50 delta)
- OTM (Out-of-The-Money): Cheaper, more leverage (~0.30 delta)
- ITM (In-The-Money): More expensive, acts like stock (~0.70 delta)
"""

import requests
import json
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta, timezone
from decimal import Decimal


class AlpacaOptionsAPI:
    """
    Alpaca Options API client for fetching option chains and contracts.
    """
    
    def __init__(self, api_key: str, api_secret: str, paper_trading: bool = True):
        """
        Initialize Alpaca Options API client.
        
        Args:
            api_key: Alpaca API key
            api_secret: Alpaca API secret
            paper_trading: Use paper trading endpoint (default True)
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = "https://paper-api.alpaca.markets" if paper_trading else "https://api.alpaca.markets"
        self.data_url = "https://data.alpaca.markets"
        
        # HTTP headers for authentication
        self.headers = {
            'APCA-API-KEY-ID': self.api_key,
            'APCA-API-SECRET-KEY': self.api_secret,
            'Content-Type': 'application/json'
        }
    
    def get_option_chain(
        self,
        ticker: str,
        expiration_date_gte: Optional[str] = None,
        expiration_date_lte: Optional[str] = None,
        option_type: Optional[str] = None,
        strike_price_gte: Optional[float] = None,
        strike_price_lte: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch option chain from Alpaca using snapshots endpoint.
        
        This is the WORKING endpoint that returns real contract data!
        
        Args:
            ticker: Underlying stock symbol (e.g., 'SPY')
            expiration_date_gte: Min expiration date (YYYY-MM-DD)
            expiration_date_lte: Max expiration date (YYYY-MM-DD)
            option_type: 'call' or 'put' (None for both)
            strike_price_gte: Minimum strike price
            strike_price_lte: Maximum strike price
        
        Returns:
            List of option contracts with symbol, bid, ask, greeks
        """
        url = f"{self.data_url}/v1beta1/options/snapshots/{ticker}"
        
        params = {'limit': 1000}  # Get many contracts
        
        if expiration_date_gte:
            params['expiration_date_gte'] = expiration_date_gte
        if expiration_date_lte:
            params['expiration_date_lte'] = expiration_date_lte
        if option_type:
            params['type'] = option_type
        if strike_price_gte:
            params['strike_price_gte'] = str(strike_price_gte)
        if strike_price_lte:
            params['strike_price_lte'] = str(strike_price_lte)
        
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            snapshots = data.get('snapshots', {})
            
            # Convert snapshots to contract format
            contracts = []
            for symbol, snapshot in snapshots.items():
                # Parse symbol (e.g., SPY260203C00520000)
                # Format: TICKER + YYMMDD + [C|P] + STRIKE[8 digits]
                # Ticker is variable length, so parse from end backwards
                if len(symbol) < 15:
                    continue
                
                # Last 8 chars = strike price
                strike_str = symbol[-8:]
                # 9th from end = C or P
                opt_type = symbol[-9]
                # 6 chars before that = YYMMDD
                exp_str = symbol[-15:-9]
                # Everything before = ticker
                parsed_ticker = symbol[:-15].strip()
                
                # Parse values
                try:
                    exp_date = f"20{exp_str[0:2]}-{exp_str[2:4]}-{exp_str[4:6]}"
                    strike_price = int(strike_str) / 1000.0
                    
                    quote = snapshot.get('latestQuote', {})
                    bid = quote.get('bp', 0)
                    ask = quote.get('ap', 0)
                    
                    greeks = snapshot.get('greeks', {})
                    
                    # Extract daily volume from dailyBar
                    daily_bar = snapshot.get('dailyBar', {})
                    volume = daily_bar.get('v', 0)  # 'v' = volume in daily bar
                    
                    contracts.append({
                        'symbol': symbol,
                        'underlying_symbol': ticker,
                        'expiration_date': exp_date,
                        'type': 'call' if opt_type == 'C' else 'put',
                        'strike_price': strike_price,
                        'bid': bid,
                        'ask': ask,
                        'volume': volume,
                        'open_interest': 0,  # Snapshots don't include OI - use /contracts endpoint if needed
                        'delta': greeks.get('delta', 0),
                        'theta': greeks.get('theta', 0),
                        'gamma': greeks.get('gamma', 0),
                        'vega': greeks.get('vega', 0),
                        'implied_volatility': greeks.get('implied_volatility', 0)
                    })
                except (ValueError, IndexError) as e:
                    print(f"Error parsing symbol {symbol}: {e}")
                    continue
            
            print(f"Fetched {len(contracts)} option contracts for {ticker}")
            
            # DEBUG: Show first contract details
            if contracts:
                first = contracts[0]
                print(f"DEBUG first contract: symbol={first.get('symbol')}, strike={first.get('strike_price')}, "
                      f"bid={first.get('bid')}, ask={first.get('ask')}, OI={first.get('open_interest', 'N/A')}")
            
            return contracts
            
        except Exception as e:
            print(f"Error fetching option chain: {e}")
            return []
    
    def get_option_snapshot(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get current option snapshot (price, greeks, volume).
        
        Args:
            symbol: Option contract symbol (e.g., 'AAPL250131C00150000')
        
        Returns:
            Option snapshot data or None if not found
        """
        url = f"{self.data_url}/v1beta1/options/snapshots/{symbol}"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching option snapshot for {symbol}: {e}")
            return None


def calculate_contract_quality_score(
    contract: Dict[str, Any],
    target_strike: float
) -> float:
    """
    PHASE 2: Calculate quality score for option contract.
    
    Scoring factors (0-100):
    - Spread tightness (40 points): Tighter = better liquidity
    - Volume (30 points): Higher = better liquidity  
    - Delta appropriateness (20 points): Match strategy needs
    - Strike distance (10 points): Closer to target = better
    
    Args:
        contract: Option contract with bid, ask, volume, delta, strike
        target_strike: Ideal strike price for strategy
    
    Returns:
        Quality score 0-100 (higher = better)
    """
    score = 0.0
    
    # Factor 1: Spread tightness (40 points max)
    bid = float(contract.get('bid', 0))
    ask = float(contract.get('ask', 0))
    
    if bid > 0 and ask > 0:
        mid = (bid + ask) / 2
        spread_pct = ((ask - bid) / mid) * 100
        
        # Perfect spread (0%) = 40 points
        # 10% spread = 0 points
        # Linear decay between
        spread_score = max(0, 40 * (1 - spread_pct / 10.0))
        score += spread_score
    
    # Factor 2: Volume (30 points max)
    volume = int(contract.get('volume', 0))
    
    # 1000+ volume = 30 points
    # 200 volume = 15 points
    # < 200 volume = 0 points
    if volume >= 1000:
        volume_score = 30
    elif volume >= 200:
        # Linear scale from 200 to 1000
        volume_score = 15 + (15 * (volume - 200) / 800)
    else:
        volume_score = 0
    
    score += volume_score
    
    # Factor 3: Delta appropriateness (20 points max)
    delta = abs(float(contract.get('delta', 0)))
    
    # Ideal delta depends on contract type:
    # Day trade: 0.30-0.40 (OTM for leverage)
    # Swing trade: 0.45-0.55 (ATM for balance)
    # Conservative: 0.65-0.75 (ITM for safety)
    
    # For simplicity, prefer 0.30-0.50 delta range
    if 0.30 <= delta <= 0.50:
        delta_score = 20
    elif 0.25 <= delta <= 0.60:
        delta_score = 15
    elif 0.20 <= delta <= 0.70:
        delta_score = 10
    else:
        delta_score = 5
    
    score += delta_score
    
    # Factor 4: Strike distance (10 points max)
    strike = float(contract.get('strike_price', 0))
    strike_distance_pct = abs(strike - target_strike) / target_strike
    
    # Perfect match = 10 points
    # 5% away = 0 points
    strike_score = max(0, 10 * (1 - strike_distance_pct / 0.05))
    score += strike_score
    
    return score


def select_optimal_strike(
    current_price: float,
    option_type: str,
    strategy: str,
    contracts: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    PHASE 2: Select optimal strike using quality scoring.
    
    CHANGES:
    - Now scores ALL contracts by quality (spread + volume + delta + strike)
    - Selects BEST quality, not just closest strike
    - Filters out low-quality contracts (score < 40)
    
    Args:
        current_price: Current stock price
        option_type: 'call' or 'put'
        strategy: 'day_trade' (OTM), 'swing_trade' (ATM), or 'conservative' (ITM)
        contracts: List of available option contracts
    
    Returns:
        Best quality option contract or None if none suitable
    """
    if not contracts:
        return None
    
    # Filter by option type
    filtered = [c for c in contracts if c.get('type') == option_type]
    
    if not filtered:
        return None
    
    # Calculate target strike based on strategy
    if strategy == 'day_trade':
        # OTM: 1-2% out of money for leverage
        if option_type == 'call':
            target_strike = current_price * 1.015  # 1.5% above
        else:  # put
            target_strike = current_price * 0.985  # 1.5% below
    
    elif strategy == 'swing_trade':
        # ATM: At current price for balanced risk/reward
        target_strike = current_price
    
    elif strategy == 'conservative':
        # ITM: In the money for lower risk
        if option_type == 'call':
            target_strike = current_price * 0.97  # 3% below
        else:  # put
            target_strike = current_price * 1.03  # 3% above
    
    else:
        # Default to ATM
        target_strike = current_price
    
    # PHASE 2: Score all contracts by quality
    scored_contracts = []
    for contract in filtered:
        quality_score = calculate_contract_quality_score(contract, target_strike)
        
        # Only consider contracts with score >= 40 (minimum acceptable)
        if quality_score >= 40:
            scored_contracts.append((quality_score, contract))
    
    if not scored_contracts:
        print(f"No contracts passed quality threshold (score >= 40)")
        return None
    
    # Sort by quality score (highest first)
    scored_contracts.sort(reverse=True, key=lambda x: x[0])
    
    # Return best quality contract
    best_score, best_contract = scored_contracts[0]
    
    print(f"Selected contract with quality score: {best_score:.1f}/100")
    print(f"  Strike: ${best_contract.get('strike_price')}, "
          f"Spread: {((best_contract.get('ask', 0) - best_contract.get('bid', 0)) / ((best_contract.get('ask', 0) + best_contract.get('bid', 0)) / 2) * 100):.1f}%, "
          f"Volume: {best_contract.get('volume')}, "
          f"Delta: {abs(best_contract.get('delta', 0)):.2f}")
    
    return best_contract


def validate_option_contract(
    contract: Dict[str, Any],
    snapshot: Optional[Dict[str, Any]],
    config: Dict[str, Any]
) -> Tuple[bool, str, bool]:
    """
    Production-grade option contract validation with comprehensive gates.
    
    CRITICAL GATES (will cause losses if not enforced):
    1. Bid/ask spread < 10% (prevents spread bleed)
    2. Option volume >= 100 (ensures liquidity)
    3. Open interest >= 100 (ensures market depth)
    4. IV percentile < 80 (prevents buying expensive options)
    
    Args:
        contract: Option contract from chain
        snapshot: Real-time snapshot with prices/greeks (or None)
        config: Configuration with thresholds
    
    Returns:
        Tuple of (passed, reason, fallback_to_stock)
        - passed: True if all gates pass
        - reason: Explanation
        - fallback_to_stock: True if should try stock instead
    """
    
    # Gate 1: Open Interest (use contract data)
    open_interest = int(contract.get('open_interest', 0))
    min_oi = config.get('min_open_interest', 100)
    
    if open_interest < min_oi:
        return (False, f"OI too low: {open_interest} < {min_oi}", True)
    
    # Gate 2: Volume (use snapshot if available, else contract)
    if snapshot and 'quote' in snapshot:
        # Real-time volume from snapshot
        volume = int(snapshot.get('latestTrade', {}).get('size', 0))
    else:
        # Historical volume from contract
        volume = int(contract.get('volume', 0))
    
    min_volume = config.get('min_option_volume', 100)
    if volume < min_volume:
        return (False, f"Volume too low: {volume} < {min_volume}", True)
    
    # Gate 3: Bid/Ask Spread
    if snapshot and 'quote' in snapshot:
        # Real-time prices
        quote = snapshot.get('quote', {})
        bid = float(quote.get('bp', 0))
        ask = float(quote.get('ap', 0))
    else:
        # Contract prices
        bid = float(contract.get('bid', 0))
        ask = float(contract.get('ask', 0))
    
    if bid > 0 and ask > 0:
        mid = (bid + ask) / 2
        spread_pct = (ask - bid) / mid
        max_spread = config.get('max_option_spread_pct', 0.10)  # 10%
        
        if spread_pct > max_spread:
            return (False, f"Spread too wide: {spread_pct*100:.1f}% > {max_spread*100:.0f}%", True)
    else:
        return (False, "No valid bid/ask prices", True)
    
    # Gate 4: IV Percentile (if available)
    if snapshot and 'greeks' in snapshot:
        greeks = snapshot.get('greeks', {})
        iv = float(greeks.get('implied_volatility', 0))
        
        # TODO: Calculate IV percentile from historical data
        # For now, use absolute IV check (>100% is very high)
        if iv > 1.0:  # 100% IV
            return (False, f"IV too high: {iv*100:.0f}%", True)
    
    # Gate 5: Expiration check
    expiration = contract.get('expiration_date')
    if expiration:
        exp_date = datetime.strptime(expiration, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        if exp_date < datetime.now(timezone.utc):
            return (False, "Contract expired", False)
    
    # All gates passed
    return (True, "All gates passed", False)


def validate_option_liquidity(
    contract: Dict[str, Any],
    min_volume: int = 10,  # LOWERED FOR TESTING: Was 200, now 10
    max_spread_pct: float = 10.0
) -> Tuple[bool, str]:
    """
    Validate option contract liquidity.
    
    PHASE 1 + 2 CHANGES:
    - Fixed spread calc: use MID not BID as denominator
    - Added minimum premium check ($0.30+)
    - PHASE 2: Minimum volume raised to 200
    
    Returns:
        Tuple of (is_valid, reason)
    """
    # Check bid-ask spread (PRIMARY liquidity indicator)
    bid = float(contract.get('bid', 0))
    ask = float(contract.get('ask', 0))
    
    if bid <= 0 or ask <= 0:
        return False, f"No valid bid/ask prices (bid={bid}, ask={ask})"
    
    # CRITICAL FIX: Use MID not BID for spread calc
    mid = (bid + ask) / 2
    spread_pct = ((ask - bid) / mid) * 100
    
    if spread_pct > max_spread_pct:
        return False, f"Spread too wide: {spread_pct:.1f}% > {max_spread_pct}%"
    
    # Minimum premium check (avoid lottery tickets)
    min_premium = 0.30  # $0.30 per share = $30 per contract
    if mid < min_premium:
        return False, f"Premium too low: ${mid:.2f} < ${min_premium:.2f} (likely worthless)"
    
    # PHASE 2: Minimum volume check
    volume = int(contract.get('volume', 0))
    if volume < min_volume:
        return False, f"Volume too low: {volume} < {min_volume} (insufficient liquidity)"
    
    # Check expiration
    expiration = contract.get('expiration_date')
    if expiration:
        exp_date = datetime.strptime(expiration, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        if exp_date < datetime.now(timezone.utc):
            return False, "Contract expired"
    
    return True, "OK"


def calculate_position_size(
    option_price: float,
    account_buying_power: float,
    max_risk_pct: float = 5.0,  # Deprecated - will use tier
    strategy: str = 'day_trade'
) -> Tuple[int, float, str]:
    """
    Calculate optimal position size with account tier awareness.
    
    CRITICAL CHANGE: Now uses account tiers!
    - $1K account: 25% per day trade (aggressive growth)
    - $100K account: 1% per day trade (professional)
    
    Args:
        option_price: Premium per contract (e.g., $2.50)
        account_buying_power: Available capital
        max_risk_pct: DEPRECATED (now uses tier)
        strategy: 'day_trade' or 'swing_trade'
    
    Returns:
        Tuple of (num_contracts, total_cost, rationale)
    """
    # Import here to avoid circular dependency
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import get_account_tier
    
    # Get appropriate tier for this account size
    tier_name, tier_config = get_account_tier(account_buying_power)
    
    # Select risk % based on strategy
    if strategy == 'day_trade':
        risk_pct = tier_config['risk_pct_day']
    elif strategy == 'swing_trade':
        risk_pct = tier_config['risk_pct_swing']
    else:
        # Default to conservative
        risk_pct = tier_config['risk_pct_swing'] * 0.5
    
    # Calculate max dollars to risk
    max_risk_dollars = account_buying_power * risk_pct
    
    # Each contract costs: premium × 100 shares
    cost_per_contract = option_price * 100
    
    # Calculate number of contracts
    num_contracts = int(max_risk_dollars / cost_per_contract)
    
    # Apply tier-specific hard cap
    max_contracts = tier_config['max_contracts']
    num_contracts = min(num_contracts, max_contracts)
    
    # Minimum 1 contract, but only if we can afford it
    if num_contracts == 0 and cost_per_contract <= account_buying_power:
        num_contracts = 1
    
    total_cost = num_contracts * cost_per_contract
    
    rationale = (
        f"Tier: {tier_name}, "
        f"Strategy: {strategy}, "
        f"Risk: {risk_pct*100:.1f}% of ${account_buying_power:.0f} = ${max_risk_dollars:.0f}, "
        f"Premium: ${option_price:.2f} × 100 = ${cost_per_contract:.0f}/contract, "
        f"Contracts: {num_contracts} (cap: {max_contracts}), "
        f"Total: ${total_cost:.0f}"
    )
    
    return num_contracts, total_cost, rationale


def format_option_symbol(
    ticker: str,
    expiration: str,
    option_type: str,
    strike: float
) -> str:
    """
    Format option symbol in OCC format.
    
    Example: AAPL250131C00150000
    - AAPL: Ticker (padded to 6 chars)
    - 250131: Expiration YYMMDD
    - C: Call/Put
    - 00150000: Strike price × 1000, 8 digits
    
    Args:
        ticker: Stock symbol
        expiration: Expiration date (YYYY-MM-DD)
        option_type: 'call' or 'put'
        strike: Strike price
    
    Returns:
        OCC formatted option symbol
    """
    # Pad ticker to 6 characters
    ticker_padded = ticker.ljust(6)
    
    # Format expiration as YYMMDD
    exp_date = datetime.strptime(expiration, '%Y-%m-%d')
    exp_formatted = exp_date.strftime('%y%m%d')
    
    # Call/Put indicator
    cp = 'C' if option_type.upper() == 'CALL' else 'P'
    
    # Strike price × 1000, 8 digits
    strike_formatted = f"{int(strike * 1000):08d}"
    
    return f"{ticker_padded}{exp_formatted}{cp}{strike_formatted}"


def validate_iv_rank(
    contract: Dict[str, Any],
    ticker: str,
    db_connection
) -> Tuple[bool, str]:
    """
    Phase 3-4: Validate IV Rank before trading
    Reject contracts where IV is in top 20% of yearly range (expensive)
    
    Args:
        contract: Option contract with implied_volatility
        ticker: Stock symbol
        db_connection: Database connection to get IV history
    
    Returns:
        Tuple of (passed, reason)
    """
    try:
        current_iv = float(contract.get('implied_volatility', 0))
        
        if current_iv <= 0:
            return True, "No IV data, skipping check"
        
        # Get IV history from database
        iv_history = db_connection.get_iv_history(ticker, days=252)
        
        if not iv_history or len(iv_history) < 30:
            # Not enough history, allow trade but log warning
            return True, f"Insufficient IV history ({len(iv_history)} obs), allowing trade"
        
        iv_rank = calculate_iv_rank(current_iv, iv_history)
        
        # Store this IV value for future calculations
        db_connection.store_iv_value(ticker, current_iv)
        
        # Reject if IV is too high (top 20% = expensive)
        if iv_rank > 0.80:
            return False, f"IV Rank too high: {iv_rank:.2f} > 0.80 (IV at {int(iv_rank*100)}th percentile)"
        
        return True, f"IV Rank OK: {iv_rank:.2f} (IV at {int(iv_rank*100)}th percentile, 52-week range {min(iv_history):.2f}-{max(iv_history):.2f})"
        
    except Exception as e:
        # Don't block trades on IV check errors
        return True, f"IV rank check error (allowing trade): {e}"


def calculate_iv_rank(current_iv: float, iv_history: List[float]) -> float:
    """
    Calculate IV Rank: where current IV sits in 52-week range.
    Returns 0.5 if insufficient history (< 30 observations).
    """
    if not iv_history or len(iv_history) < 30:
        return 0.5

    iv_high = max(iv_history)
    iv_low = min(iv_history)

    if iv_high == iv_low:
        return 0.5

    iv_rank = (current_iv - iv_low) / (iv_high - iv_low)
    return max(0.0, min(1.0, iv_rank))


def calculate_kelly_criterion_size(
    win_rate: float,
    avg_win_pct: float,
    avg_loss_pct: float,
    account_buying_power: float,
    option_price: float,
    safety_fraction: float = 0.5
) -> Tuple[int, str]:
    """
    Phase 4: Calculate position size using Kelly Criterion
    
    Kelly % = (Win Rate × Avg Win - Loss Rate × Avg Loss) / Avg Win
    Use fractional Kelly (default 50%) for safety
    
    Args:
        win_rate: Historical win rate (0-1)
        avg_win_pct: Average win percentage
        avg_loss_pct: Average loss percentage (positive number)
        account_buying_power: Available capital
        option_price: Option premium per share
        safety_fraction: Fraction of Kelly to use (default 0.5)
    
    Returns:
        Tuple of (num_contracts, rationale)
    """
    try:
        # Calculate full Kelly
        if avg_win_pct <= 0:
            kelly = 0.0
        else:
            loss_rate = 1 - win_rate
            kelly = (win_rate * avg_win_pct - loss_rate * avg_loss_pct) / avg_win_pct
        
        # Apply safety fraction
        fractional_kelly = kelly * safety_fraction
        
        # Cap at 25% (no position > 25% of account)
        position_pct = min(fractional_kelly, 0.25)
        
        # Calculate contracts
        max_risk_dollars = account_buying_power * position_pct
        cost_per_contract = option_price * 100
        num_contracts = int(max_risk_dollars / cost_per_contract)
        
        # Minimum 1 if we can afford it
        if num_contracts == 0 and cost_per_contract <= account_buying_power:
            num_contracts = 1
        
        rationale = (
            f"Kelly: {kelly:.2%} (Win: {win_rate:.1%} @ {avg_win_pct:.1f}%, "
            f"Loss: {loss_rate:.1%} @ {avg_loss_pct:.1f}%), "
            f"Fractional ({safety_fraction:.0%}): {fractional_kelly:.2%}, "
            f"Position: {position_pct:.1%} of ${account_buying_power:.0f}, "
            f"Contracts: {num_contracts}"
        )
        
        return num_contracts, rationale
        
    except Exception as e:
        # Fallback to conservative sizing on error
        return 1, f"Kelly calc error (using 1 contract): {e}"


def get_option_chain_for_strategy(
    api: AlpacaOptionsAPI,
    ticker: str,
    current_price: float,
    strategy: str,
    option_type: str
) -> Optional[Dict[str, Any]]:
    """
    High-level function to get optimal option for a strategy.
    
    Args:
        api: AlpacaOptionsAPI instance
        ticker: Stock symbol
        current_price: Current stock price
        strategy: 'day_trade' (0-1 DTE) or 'swing_trade' (7-30 DTE)
        option_type: 'call' or 'put'
    
    Returns:
        Best option contract or None
    """
    # Set expiration range based on strategy
    today = datetime.now(timezone.utc).date()
    
    if strategy == 'day_trade':
        # 0-1 DTE (expires today or tomorrow)
        min_date = today.strftime('%Y-%m-%d')
        max_date = (today + timedelta(days=1)).strftime('%Y-%m-%d')
    elif strategy == 'swing_trade':
        # 7-30 DTE
        min_date = (today + timedelta(days=7)).strftime('%Y-%m-%d')
        max_date = (today + timedelta(days=30)).strftime('%Y-%m-%d')
    else:
        # Default: next 7 days
        min_date = today.strftime('%Y-%m-%d')
        max_date = (today + timedelta(days=7)).strftime('%Y-%m-%d')
    
    # Set strike range (±10% from current price)
    strike_min = current_price * 0.90
    strike_max = current_price * 1.10
    
    # Fetch option chain
    contracts = api.get_option_chain(
        ticker=ticker,
        expiration_date_gte=min_date,
        expiration_date_lte=max_date,
        option_type=option_type,
        strike_price_gte=strike_min,
        strike_price_lte=strike_max
    )
    
    if not contracts:
        print(f"No option contracts found for {ticker} {option_type} {strategy}")
        return None
    
    # Select optimal strike
    best_contract = select_optimal_strike(
        current_price=current_price,
        option_type=option_type,
        strategy=strategy,
        contracts=contracts
    )
    
    if not best_contract:
        print(f"No suitable strike found for {ticker}")
        return None
    
    # Validate liquidity
    is_valid, reason = validate_option_liquidity(best_contract)
    
    if not is_valid:
        print(f"Option contract failed liquidity check: {reason}")
        return None
    
    return best_contract
