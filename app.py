#!/usr/bin/env python3
"""
Uncle Warren Says - Web Application
Flask backend for stock analysis with Buffett & Graham metrics
Powered by Finnhub API
"""

from flask import Flask, render_template, jsonify, request
import finnhub
import requests as http_requests
import pandas as pd
import numpy as np
import os
import re
import time
import random
from datetime import datetime, timedelta

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Finnhub client + simple cache
# ---------------------------------------------------------------------------
FINNHUB_API_KEY = os.environ.get('FINNHUB_API_KEY', '')
finnhub_client = finnhub.Client(api_key=FINNHUB_API_KEY)


class SimpleCache:
    """Dict-based cache with per-key TTL (default 5 min)."""
    def __init__(self, ttl=300):
        self._store = {}
        self._ttl = ttl

    def get(self, key):
        entry = self._store.get(key)
        if entry and time.time() - entry['ts'] < self._ttl:
            return entry['val']
        return None

    def set(self, key, val):
        self._store[key] = {'val': val, 'ts': time.time()}


cache = SimpleCache(ttl=300)

# Curated list of stocks that typically score well on Buffett metrics
STOCK_OF_DAY_CANDIDATES = [
    {'ticker': 'BRK.B', 'name': 'Berkshire Hathaway'},
    {'ticker': 'GOOGL', 'name': 'Alphabet'},
    {'ticker': 'META', 'name': 'Meta Platforms'},
    {'ticker': 'JNJ', 'name': 'Johnson & Johnson'},
    {'ticker': 'V', 'name': 'Visa'},
    {'ticker': 'MA', 'name': 'Mastercard'},
    {'ticker': 'UNH', 'name': 'UnitedHealth'},
    {'ticker': 'PG', 'name': 'Procter & Gamble'},
    {'ticker': 'KO', 'name': 'Coca-Cola'},
    {'ticker': 'MRK', 'name': 'Merck'},
    {'ticker': 'ABBV', 'name': 'AbbVie'},
    {'ticker': 'JPM', 'name': 'JPMorgan Chase'},
    {'ticker': 'BAC', 'name': 'Bank of America'},
    {'ticker': 'AXP', 'name': 'American Express'},
    {'ticker': 'COST', 'name': 'Costco'},
    {'ticker': 'CAT', 'name': 'Caterpillar'},
    {'ticker': 'AVGO', 'name': 'Broadcom'},
    {'ticker': 'TXN', 'name': 'Texas Instruments'},
    {'ticker': 'MSFT', 'name': 'Microsoft'},
    {'ticker': 'AAPL', 'name': 'Apple'},
]

# ---------------------------------------------------------------------------
# Common name → ticker (instant, no API call)
# ---------------------------------------------------------------------------
COMMON_NAMES = {
    'TESLA': 'TSLA', 'APPLE': 'AAPL', 'GOOGLE': 'GOOGL',
    'ALPHABET': 'GOOGL', 'AMAZON': 'AMZN', 'FACEBOOK': 'META',
    'META': 'META', 'MICROSOFT': 'MSFT', 'NETFLIX': 'NFLX',
    'NVIDIA': 'NVDA', 'BERKSHIRE': 'BRK.B', 'WALMART': 'WMT',
    'DISNEY': 'DIS', 'COCA-COLA': 'KO', 'COCACOLA': 'KO',
    'COKE': 'KO', 'PEPSI': 'PEP', 'PEPSICO': 'PEP',
    'PINTEREST': 'PINS', 'TWITTER': 'X', 'STARBUCKS': 'SBUX',
    'MCDONALDS': 'MCD', 'NIKE': 'NKE', 'BOEING': 'BA',
    'INTEL': 'INTC', 'AMD': 'AMD', 'PAYPAL': 'PYPL',
    'SALESFORCE': 'CRM', 'ORACLE': 'ORCL', 'IBM': 'IBM',
    'CISCO': 'CSCO', 'VISA': 'V', 'MASTERCARD': 'MA',
    'JPMORGAN': 'JPM', 'GOLDMAN': 'GS', 'MORGAN STANLEY': 'MS',
    'WELLS FARGO': 'WFC', 'COSTCO': 'COST', 'TARGET': 'TGT',
    'HOME DEPOT': 'HD', 'LOWES': 'LOW', 'SPOTIFY': 'SPOT',
    'UBER': 'UBER', 'LYFT': 'LYFT', 'AIRBNB': 'ABNB',
    'SNAP': 'SNAP', 'SNAPCHAT': 'SNAP', 'ZOOM': 'ZM',
    'SHOPIFY': 'SHOP', 'SQUARE': 'SQ', 'BLOCK': 'SQ',
    'ROBINHOOD': 'HOOD', 'COINBASE': 'COIN', 'PALANTIR': 'PLTR',
    'SNOWFLAKE': 'SNOW', 'CROWDSTRIKE': 'CRWD', 'DATADOG': 'DDOG',
}


def search_ticker(query):
    """Search for a stock by company name or ticker via Finnhub."""
    original_query = query.strip()
    query_upper = original_query.upper()

    if query_upper.startswith('$'):
        query_upper = query_upper[1:]
        original_query = original_query[1:]

    # 1. Common names (instant)
    if query_upper in COMMON_NAMES:
        return COMMON_NAMES[query_upper]

    # 2. Looks like a ticker? Validate via company_profile2
    if re.match(r'^[A-Z]{1,5}(\.[A-Z])?$', query_upper):
        cached = cache.get(f'profile:{query_upper}')
        if cached:
            return query_upper
        try:
            profile = finnhub_client.company_profile2(symbol=query_upper)
            if profile and profile.get('ticker'):
                cache.set(f'profile:{query_upper}', profile)
                return query_upper
        except Exception:
            pass

    # 3. Symbol lookup via Finnhub
    try:
        results = finnhub_client.symbol_lookup(original_query)
        if results and results.get('result'):
            for item in results['result']:
                symbol = item.get('symbol', '')
                item_type = item.get('type', '')
                # Prefer common stock on US exchanges
                if item_type == 'Common Stock' and '.' not in symbol:
                    return symbol
            # Fallback to first result
            return results['result'][0].get('symbol', query_upper)
    except Exception as e:
        print(f"Finnhub symbol_lookup error: {e}")

    return query_upper


def _format_market_cap(cap_millions):
    """Format market cap from millions to human-readable string."""
    if cap_millions is None:
        return 'N/A'
    if cap_millions >= 1_000_000:
        return f"{cap_millions / 1_000_000:.1f}T"
    if cap_millions >= 1_000:
        return f"{cap_millions / 1_000:.1f}B"
    return f"{cap_millions:.0f}M"


def fetch_stock_data(ticker):
    """Fetch stock metrics from Finnhub (profile + basic financials + quote)."""
    ticker = ticker.upper()
    cached = cache.get(f'data:{ticker}')
    if cached:
        return cached

    try:
        # 1. Company profile
        profile = cache.get(f'profile:{ticker}')
        if not profile:
            profile = finnhub_client.company_profile2(symbol=ticker)
            if profile and profile.get('ticker'):
                cache.set(f'profile:{ticker}', profile)

        if not profile or not profile.get('ticker'):
            return None

        # 2. Basic financials (annual metrics)
        financials = finnhub_client.company_basic_financials(ticker, 'all')
        metric = financials.get('metric', {}) if financials else {}

        # 3. Real-time quote
        quote = finnhub_client.quote(ticker)

        current_price = quote.get('c') if quote else None

        metrics = {
            'ticker': ticker,
            'company': profile.get('name', ticker),
            'price': current_price,
            'market_cap': _format_market_cap(profile.get('marketCapitalization')),
            # Pre-parsed floats with _ prefix
            '_pe': metric.get('peBasicExclExtraTTM'),
            '_forward_pe': metric.get('peTTM'),
            '_eps_growth': metric.get('epsGrowthTTMYoy'),
            '_eps_growth_5y': metric.get('epsGrowth5Y'),
            '_roe': metric.get('roeTTM'),
            '_roi': metric.get('roiTTM'),
            '_debt_equity': metric.get('totalDebt/totalEquityQuarterly'),
            '_profit_margin': metric.get('netProfitMarginTTM'),
            '_oper_margin': metric.get('operatingMarginTTM'),
            '_pb': metric.get('pbQuarterly'),
            '_ps': metric.get('psTTM'),
            '_current_ratio': metric.get('currentRatioQuarterly'),
            '_quick_ratio': metric.get('quickRatioQuarterly'),
            '_dividend_yield': metric.get('dividendYieldIndicatedAnnual'),
            '_payout_ratio': metric.get('payoutRatioTTM'),
            '_beta': metric.get('beta'),
            '_perf_ytd': metric.get('yearToDatePriceReturnDaily'),
            '_perf_year': metric.get('52WeekPriceReturnDaily'),
            '_52w_high': metric.get('52WeekHighDate'),
            '_52w_low': metric.get('52WeekLowDate'),
            # These are unavailable from Finnhub free tier
            '_short_float': None,
            '_insider_own': None,
            '_inst_own': None,
        }

        cache.set(f'data:{ticker}', metrics)
        return metrics

    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return None


def _fetch_candles_yahoo(ticker):
    """Fetch ~14 months of daily closes from Yahoo Finance chart API."""
    # Yahoo uses dashes for share classes (BRK.B -> BRK-B)
    yahoo_ticker = ticker.replace('.', '-')
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_ticker}"
    params = {'interval': '1d', 'range': '1y'}
    headers = {'User-Agent': 'Mozilla/5.0'}
    resp = http_requests.get(url, params=params, headers=headers, timeout=10)
    data = resp.json()
    result = data.get('chart', {}).get('result', [])
    if not result:
        return None
    closes = result[0].get('indicators', {}).get('quote', [{}])[0].get('close', [])
    return [c for c in closes if c is not None] or None


def fetch_price_history(ticker):
    """Fetch ~14 months of daily candles, compute technicals."""
    ticker = ticker.upper()
    cached = cache.get(f'history:{ticker}')
    if cached:
        return cached

    try:
        closes_raw = None

        # Try Finnhub candles first (works for crypto/forex/some stocks)
        try:
            now = int(time.time())
            start = now - (14 * 30 * 86400)
            candles = finnhub_client.stock_candles(ticker, 'D', start, now)
            if candles and candles.get('s') == 'ok':
                closes_raw = candles.get('c', [])
        except Exception:
            pass

        # Fall back to Yahoo Finance chart API
        if not closes_raw or len(closes_raw) < 2:
            closes_raw = _fetch_candles_yahoo(ticker)

        if not closes_raw or len(closes_raw) < 2:
            return None

        closes = pd.Series(closes_raw, dtype=float)

        # --- 3-month performance (last ~63 trading days) ---
        n_3m = min(63, len(closes))
        closes_3m = closes.iloc[-n_3m:]
        start_price = closes_3m.iloc[0]
        end_price = closes_3m.iloc[-1]
        return_3m = ((end_price - start_price) / start_price) * 100
        high_3m = closes_3m.max()
        low_3m = closes_3m.min()

        step = max(1, len(closes_3m) // 30)
        sparkline = closes_3m.iloc[::step].tolist()

        # --- Technical Indicators ---
        sma_200 = closes.rolling(200).mean().iloc[-1] if len(closes) >= 200 else None
        sma_50 = closes.rolling(50).mean().iloc[-1] if len(closes) >= 50 else None

        # RSI (14-day)
        rsi = None
        if len(closes) >= 15:
            delta = closes.diff()
            gain = delta.clip(lower=0)
            loss = (-delta.clip(upper=0))
            avg_gain = gain.rolling(14).mean().iloc[-1]
            avg_loss = loss.rolling(14).mean().iloc[-1]
            if avg_loss > 0:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
            else:
                rsi = 100.0

        # Golden / Death cross
        golden_cross = None
        if sma_50 is not None and sma_200 is not None:
            if not (np.isnan(sma_50) or np.isnan(sma_200)):
                golden_cross = bool(sma_50 > sma_200)

        # Price vs 200-day SMA
        price_vs_sma200 = None
        if sma_200 is not None and not np.isnan(sma_200) and sma_200 > 0:
            price_vs_sma200 = ((end_price - sma_200) / sma_200) * 100

        result = {
            'return_3m': round(float(return_3m), 2),
            'start_price': round(float(start_price), 2),
            'end_price': round(float(end_price), 2),
            'high_3m': round(float(high_3m), 2),
            'low_3m': round(float(low_3m), 2),
            'sparkline': [round(float(p), 2) for p in sparkline],
            # Technical indicators
            'sma_200': round(float(sma_200), 2) if sma_200 is not None and not np.isnan(sma_200) else None,
            'sma_50': round(float(sma_50), 2) if sma_50 is not None and not np.isnan(sma_50) else None,
            'rsi': round(float(rsi), 1) if rsi is not None else None,
            'golden_cross': golden_cross,
            'price_vs_sma200': round(float(price_vs_sma200), 2) if price_vs_sma200 is not None else None,
        }

        cache.set(f'history:{ticker}', result)
        return result

    except Exception as e:
        print(f"Error fetching price history for {ticker}: {e}")
        return None


def fetch_news_summary(ticker, company_name):
    """Fetch recent company news from Finnhub (last 7 days)."""
    try:
        today = datetime.now()
        week_ago = today - timedelta(days=7)
        news = finnhub_client.company_news(
            ticker,
            _from=week_ago.strftime('%Y-%m-%d'),
            to=today.strftime('%Y-%m-%d')
        )
        if not news:
            return []
        headlines = [item.get('headline', '') for item in news[:5] if item.get('headline')]
        return headlines[:3]
    except Exception as e:
        print(f"Error fetching news for {ticker}: {e}")
        return []


def generate_extended_analysis(metrics, analysis, news_headlines):
    """Generate extended investment thesis with 2-3 additional sentences."""
    company = metrics.get('company', '')

    pe = analysis['metrics'].get('pe')
    roe = analysis['metrics'].get('roe')
    profit_margin = analysis['metrics'].get('profit_margin')
    debt_equity = analysis['metrics'].get('debt_equity')
    dividend = analysis['metrics'].get('dividend_yield')
    eps_growth = analysis['metrics'].get('eps_growth')

    extended = []

    if pe and pe < 20:
        extended.append(f"At {pe:.1f}x earnings, {company} trades at a significant discount to the S&P 500 average of ~23x, suggesting the market may be undervaluing its earnings power.")
    elif pe and pe < 30:
        extended.append(f"The current P/E of {pe:.1f}x reflects reasonable expectations for future growth while not requiring heroic assumptions to justify the valuation.")

    if roe and roe > 20 and profit_margin and profit_margin > 15:
        extended.append(f"The combination of {roe:.0f}% return on equity and {profit_margin:.0f}% profit margins demonstrates the durable competitive advantages that Buffett seeks - pricing power and efficient capital allocation.")
    elif roe and roe > 15:
        extended.append(f"Management has demonstrated solid capital allocation with {roe:.0f}% return on equity, reinvesting profits effectively to compound shareholder value.")

    if debt_equity and debt_equity < 0.5:
        extended.append(f"The conservative balance sheet (D/E: {debt_equity:.2f}) provides flexibility to weather economic downturns and pursue opportunistic acquisitions - a hallmark of Buffett's fortress-like businesses.")

    if eps_growth and eps_growth > 10 and dividend and dividend > 1:
        extended.append(f"Investors get the best of both worlds: {eps_growth:.0f}% earnings growth for capital appreciation plus a {dividend:.1f}% dividend yield for current income.")
    elif eps_growth and eps_growth > 15:
        extended.append(f"With {eps_growth:.0f}% projected earnings growth, the company is compounding intrinsic value at a rate that should translate to strong long-term returns.")

    if news_headlines:
        extended.append(f"Recent headlines: \"{news_headlines[0]}\" - staying informed on company developments helps investors maintain conviction through volatility.")

    return ' '.join(extended[:3])


def parse_metric(value):
    """Parse a metric value string to float (backward compat)."""
    if not value or value == '-':
        return None
    try:
        clean = re.sub(r'[%,]', '', str(value))
        return float(clean)
    except Exception:
        return None


def _get_metric(metrics, key, raw_key=None):
    """Read _-prefixed float first, fall back to parse_metric for strings."""
    prefixed = metrics.get(f'_{key}')
    if prefixed is not None:
        return prefixed
    if raw_key:
        return parse_metric(metrics.get(raw_key))
    return None


def analyze_stock(metrics, price_history=None, extended=False):
    """Analyze stock against Buffett's and Graham's criteria + technical score."""
    if not metrics:
        return None

    # Extract key metrics via helper
    pe = _get_metric(metrics, 'pe', 'P/E')
    forward_pe = _get_metric(metrics, 'forward_pe', 'Forward P/E')
    eps_growth = _get_metric(metrics, 'eps_growth', 'EPS next 5Y')
    if eps_growth is None:
        eps_growth = _get_metric(metrics, 'eps_growth_5y', 'EPS past 5Y')
    roe = _get_metric(metrics, 'roe', 'ROE')
    roi = _get_metric(metrics, 'roi', 'ROI')
    debt_equity = _get_metric(metrics, 'debt_equity', 'Debt/Eq')
    profit_margin = _get_metric(metrics, 'profit_margin', 'Profit Margin')
    oper_margin = _get_metric(metrics, 'oper_margin', 'Oper. Margin')
    pb = _get_metric(metrics, 'pb', 'P/B')
    ps = _get_metric(metrics, 'ps', 'P/S')
    current_ratio = _get_metric(metrics, 'current_ratio', 'Current Ratio')
    quick_ratio = _get_metric(metrics, 'quick_ratio', 'Quick Ratio')
    dividend_yield = _get_metric(metrics, 'dividend_yield', 'Dividend %')
    payout_ratio = _get_metric(metrics, 'payout_ratio', 'Payout')
    beta = _get_metric(metrics, 'beta', 'Beta')
    short_float = _get_metric(metrics, 'short_float', 'Short Float')
    insider_own = _get_metric(metrics, 'insider_own', 'Insider Own')
    inst_own = _get_metric(metrics, 'inst_own', 'Inst Own')
    perf_ytd = _get_metric(metrics, 'perf_ytd', 'Perf YTD')
    perf_year = _get_metric(metrics, 'perf_year', 'Perf Year')

    market_cap = metrics.get('market_cap', 'N/A')

    if pe is None:
        pe = forward_pe

    analysis = {
        'ticker': metrics['ticker'],
        'company': metrics['company'],
        'price': metrics.get('price'),
        'market_cap': market_cap,
        'metrics': {
            'pe': pe,
            'forward_pe': forward_pe,
            'eps_growth': eps_growth,
            'roe': roe,
            'roi': roi,
            'debt_equity': debt_equity,
            'profit_margin': profit_margin,
            'oper_margin': oper_margin,
            'pb': pb,
            'ps': ps,
            'current_ratio': current_ratio,
            'quick_ratio': quick_ratio,
            'dividend_yield': dividend_yield,
            'payout_ratio': payout_ratio,
            'beta': beta,
            'short_float': short_float,
            'insider_own': insider_own,
            'inst_own': inst_own,
            'perf_ytd': perf_ytd,
            'perf_year': perf_year,
        },
        'price_history': price_history
    }

    # -----------------------------------------------------------------------
    # Fundamental Score (100 points max, same as before)
    # -----------------------------------------------------------------------
    score = 0
    max_score = 0
    reasons_for = []
    reasons_against = []

    # P/E Analysis (25 points)
    max_score += 25
    if pe is not None and pe > 0:
        if pe < 15:
            score += 25
            reasons_for.append(f"Attractively valued at {pe:.1f}x earnings")
        elif pe < 20:
            score += 20
            reasons_for.append(f"Reasonably priced at {pe:.1f}x earnings")
        elif pe < 25:
            score += 15
        elif pe < 35:
            score += 10
            reasons_against.append(f"P/E of {pe:.1f} is on the higher side")
        else:
            reasons_against.append(f"P/E of {pe:.1f} exceeds value threshold of 35")
    else:
        reasons_against.append("No P/E ratio (may be unprofitable)")

    # EPS Growth (20 points)
    max_score += 20
    if eps_growth is not None:
        if eps_growth > 20:
            score += 20
            reasons_for.append(f"Excellent earnings growth of {eps_growth:.1f}%")
        elif eps_growth > 15:
            score += 16
            reasons_for.append(f"Strong earnings growth of {eps_growth:.1f}%")
        elif eps_growth > 10:
            score += 12
            reasons_for.append(f"Solid earnings growth of {eps_growth:.1f}%")
        elif eps_growth > 5:
            score += 8
        else:
            reasons_against.append(f"Weak earnings growth of {eps_growth:.1f}%")

    # ROE (15 points)
    max_score += 15
    if roe is not None:
        if roe > 25:
            score += 15
            reasons_for.append(f"Exceptional return on equity ({roe:.1f}%)")
        elif roe > 20:
            score += 12
        elif roe > 15:
            score += 9
        elif roe > 10:
            score += 6
        else:
            reasons_against.append(f"Low ROE of {roe:.1f}% suggests poor capital efficiency")

    # Profit Margin (10 points)
    max_score += 10
    if profit_margin is not None:
        if profit_margin > 20:
            score += 10
            reasons_for.append(f"Strong profit margins ({profit_margin:.1f}%) indicate pricing power")
        elif profit_margin > 15:
            score += 8
        elif profit_margin > 10:
            score += 6
        elif profit_margin > 5:
            score += 4

    # Price to Book (10 points)
    max_score += 10
    if pb is not None:
        if pb < 1.5:
            score += 10
            reasons_for.append(f"Trading below book value (P/B: {pb:.2f}) - Graham would approve")
        elif pb < 2.5:
            score += 7
        elif pb < 4:
            score += 4
        else:
            reasons_against.append(f"High P/B of {pb:.1f} - paying premium over assets")

    # Current Ratio (10 points)
    max_score += 10
    if current_ratio is not None:
        if current_ratio > 2.0:
            score += 10
            reasons_for.append(f"Strong balance sheet (Current Ratio: {current_ratio:.1f})")
        elif current_ratio > 1.5:
            score += 7
        elif current_ratio > 1.0:
            score += 4
        else:
            reasons_against.append(f"Weak liquidity (Current Ratio: {current_ratio:.1f})")

    # Debt/Equity (10 points)
    max_score += 10
    if debt_equity is not None:
        if debt_equity < 0.3:
            score += 10
            reasons_for.append(f"Very conservative debt levels (D/E: {debt_equity:.2f})")
        elif debt_equity < 0.5:
            score += 8
            reasons_for.append(f"Low debt (D/E: {debt_equity:.2f})")
        elif debt_equity < 1.0:
            score += 6
        elif debt_equity < 1.5:
            score += 4
        else:
            reasons_against.append(f"High debt levels (D/E: {debt_equity:.2f})")

    # Dividend bonus (no max_score contribution)
    if dividend_yield is not None and dividend_yield > 0:
        if dividend_yield > 3:
            reasons_for.append(f"Attractive {dividend_yield:.1f}% dividend yield")
        elif dividend_yield > 1.5:
            reasons_for.append(f"Pays {dividend_yield:.1f}% dividend")

    # Insider ownership
    if insider_own is not None and insider_own > 10:
        reasons_for.append(f"High insider ownership ({insider_own:.1f}%)")

    fundamental_score = score
    fundamental_max = max_score

    # -----------------------------------------------------------------------
    # Technical Score (20 points)
    # -----------------------------------------------------------------------
    tech_score = 0
    tech_max = 20
    tech_signals = []

    if price_history:
        rsi = price_history.get('rsi')
        golden = price_history.get('golden_cross')
        pv200 = price_history.get('price_vs_sma200')
        ret3m = price_history.get('return_3m')

        # RSI position (5 pts)
        if rsi is not None:
            if 30 <= rsi <= 70:
                tech_score += 5
                tech_signals.append({'label': f'RSI {rsi:.0f} — neutral range', 'type': 'bullish'})
            elif rsi < 30:
                tech_score += 3
                tech_signals.append({'label': f'RSI {rsi:.0f} — oversold', 'type': 'neutral'})
            else:
                tech_signals.append({'label': f'RSI {rsi:.0f} — overbought', 'type': 'bearish'})

        # Golden / Death cross (5 pts)
        if golden is not None:
            if golden:
                tech_score += 5
                tech_signals.append({'label': 'Golden Cross (50 > 200 SMA)', 'type': 'bullish'})
            else:
                tech_signals.append({'label': 'Death Cross (50 < 200 SMA)', 'type': 'bearish'})

        # Price vs 200-day SMA (5 pts)
        if pv200 is not None:
            if pv200 > 0:
                tech_score += 5
                tech_signals.append({'label': f'{pv200:+.1f}% above 200-day SMA', 'type': 'bullish'})
            else:
                tech_score += 2
                tech_signals.append({'label': f'{pv200:+.1f}% below 200-day SMA', 'type': 'bearish'})

        # 3-month momentum (5 pts)
        if ret3m is not None:
            if ret3m > 10:
                tech_score += 5
                tech_signals.append({'label': f'Strong 3-mo momentum ({ret3m:+.1f}%)', 'type': 'bullish'})
            elif ret3m > 0:
                tech_score += 3
                tech_signals.append({'label': f'Positive 3-mo momentum ({ret3m:+.1f}%)', 'type': 'neutral'})
            else:
                tech_score += 1
                tech_signals.append({'label': f'Negative 3-mo momentum ({ret3m:+.1f}%)', 'type': 'bearish'})

    # -----------------------------------------------------------------------
    # Blended score
    # -----------------------------------------------------------------------
    total_score = fundamental_score + tech_score
    total_max = fundamental_max + tech_max
    final_score = int((total_score / total_max) * 100) if total_max > 0 else 0

    analysis['score'] = final_score
    analysis['fundamental_score'] = int((fundamental_score / fundamental_max) * 100) if fundamental_max > 0 else 0
    analysis['technical'] = {
        'score': tech_score,
        'max': tech_max,
        'signals': tech_signals,
        'rsi': price_history.get('rsi') if price_history else None,
        'sma_50': price_history.get('sma_50') if price_history else None,
        'sma_200': price_history.get('sma_200') if price_history else None,
        'golden_cross': price_history.get('golden_cross') if price_history else None,
        'price_vs_sma200': price_history.get('price_vs_sma200') if price_history else None,
    }
    analysis['reasons_for'] = reasons_for[:4]
    analysis['reasons_against'] = reasons_against[:3]

    # Generate verdict
    if final_score >= 75:
        verdict = "BUY"
        emoji = "\u2705"
        summary = f"Warren would likely approve of {metrics['company']}. "
    elif final_score >= 55:
        verdict = "CONSIDER"
        emoji = "\U0001f914"
        summary = f"{metrics['company']} has some value characteristics. "
    elif final_score >= 35:
        verdict = "CAUTION"
        emoji = "\u26a0\ufe0f"
        summary = f"{metrics['company']} doesn't fully meet value criteria. "
    else:
        verdict = "PASS"
        emoji = "\u274c"
        summary = f"Warren would likely pass on {metrics['company']}. "

    if reasons_for:
        summary += reasons_for[0] + ". "
    if reasons_against:
        summary += "However, " + reasons_against[0].lower() + "."
    elif len(reasons_for) > 1:
        summary += reasons_for[1] + "."

    analysis['verdict'] = verdict
    analysis['emoji'] = emoji
    analysis['summary'] = summary

    if extended:
        news = fetch_news_summary(metrics['ticker'], metrics['company'])
        analysis['extended_analysis'] = generate_extended_analysis(metrics, analysis, news)
        analysis['news_headlines'] = news

    return analysis


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/search/<query>')
def search(query):
    """Search for a ticker by company name."""
    ticker = search_ticker(query)
    return jsonify({'ticker': ticker})


@app.route('/analyze/<query>')
def analyze(query):
    """API endpoint to analyze a stock."""
    ticker = search_ticker(query)
    metrics = fetch_stock_data(ticker)

    if not metrics:
        return jsonify({
            'error': True,
            'message': f"Could not find '{query}'. Try a ticker symbol (e.g., AAPL) or company name (e.g., Apple)."
        })

    price_history = fetch_price_history(ticker)
    analysis = analyze_stock(metrics, price_history)
    return jsonify(analysis)


@app.route('/stock-of-the-day')
def stock_of_the_day():
    """Return a curated stock pick with extended analysis."""
    today = datetime.now().strftime('%Y-%m-%d')
    random.seed(today)

    candidates = STOCK_OF_DAY_CANDIDATES.copy()
    random.shuffle(candidates)

    for candidate in candidates:
        ticker = candidate['ticker']
        metrics = fetch_stock_data(ticker)

        if not metrics:
            continue

        price_history = fetch_price_history(ticker)
        analysis = analyze_stock(metrics, price_history, extended=True)

        if analysis and analysis.get('score', 0) >= 55:
            analysis['is_stock_of_day'] = True
            analysis['pick_date'] = today
            return jsonify(analysis)

    # Fallback to Berkshire
    metrics = fetch_stock_data('BRK.B')
    price_history = fetch_price_history('BRK.B')
    analysis = analyze_stock(metrics, price_history, extended=True)
    analysis['is_stock_of_day'] = True
    analysis['pick_date'] = today
    return jsonify(analysis)


if __name__ == '__main__':
    app.run(debug=True, port=5050)
