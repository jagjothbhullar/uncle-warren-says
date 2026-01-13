#!/usr/bin/env python3
"""
Uncle Warren Says - Web Application
Flask backend for stock analysis with Buffett & Graham metrics
"""

from flask import Flask, render_template, jsonify, request
import requests
from bs4 import BeautifulSoup
import re
import json

app = Flask(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
}

def search_ticker(query):
    """Search for a stock by company name or ticker"""
    query = query.strip().upper()

    # If it looks like a ticker (short, no spaces), try it directly
    if len(query) <= 5 and ' ' not in query:
        return query

    # Otherwise, search by company name using Yahoo Finance
    try:
        search_url = f"https://query1.finance.yahoo.com/v1/finance/search"
        params = {
            'q': query,
            'quotesCount': 5,
            'newsCount': 0,
            'enableFuzzyQuery': True,
            'quotesQueryId': 'tss_match_phrase_query'
        }
        response = requests.get(search_url, params=params, headers=HEADERS, timeout=5)
        data = response.json()

        if data.get('quotes') and len(data['quotes']) > 0:
            # Return the first matching stock ticker
            for quote in data['quotes']:
                if quote.get('quoteType') == 'EQUITY':
                    return quote.get('symbol')
            # If no equity found, return first result
            return data['quotes'][0].get('symbol')
    except Exception as e:
        print(f"Search error: {e}")

    # Fallback: return the query as-is
    return query.replace(' ', '')

def fetch_stock_data(ticker):
    """Fetch stock metrics from Finviz"""
    url = f"https://finviz.com/quote.ashx?t={ticker.upper()}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, 'html.parser')

        # Check if stock exists
        if 'not found' in response.text.lower():
            return None

        # Get company name
        title = soup.find('a', {'class': 'tab-link'})
        company_name = title.text.strip() if title else ticker.upper()

        # Get current price
        price_elem = soup.find('strong', {'class': 'quote-price_wrapper_price'})
        if not price_elem:
            # Try alternative selector
            price_elem = soup.find('strong', class_=lambda x: x and 'price' in x.lower() if x else False)

        current_price = None
        if price_elem:
            try:
                current_price = float(price_elem.text.strip().replace(',', ''))
            except:
                pass

        # Find the snapshot table with all metrics
        table = soup.find('table', {'class': 'snapshot-table2'})
        if not table:
            return None

        metrics = {'ticker': ticker.upper(), 'company': company_name, 'price': current_price}
        rows = table.find_all('tr')

        for row in rows:
            cells = row.find_all('td')
            for i in range(0, len(cells) - 1, 2):
                key = cells[i].text.strip()
                value = cells[i + 1].text.strip()
                metrics[key] = value

        return metrics

    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return None

def fetch_price_history(ticker):
    """Fetch 3-month price history from Yahoo Finance"""
    try:
        # Get 3 months of daily data
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        params = {
            'interval': '1d',
            'range': '3mo'
        }
        response = requests.get(url, params=params, headers=HEADERS, timeout=10)
        data = response.json()

        result = data.get('chart', {}).get('result', [])
        if not result:
            return None

        quotes = result[0]
        timestamps = quotes.get('timestamp', [])
        closes = quotes.get('indicators', {}).get('quote', [{}])[0].get('close', [])

        if not timestamps or not closes:
            return None

        # Calculate returns
        valid_closes = [c for c in closes if c is not None]
        if len(valid_closes) < 2:
            return None

        start_price = valid_closes[0]
        end_price = valid_closes[-1]
        return_3m = ((end_price - start_price) / start_price) * 100

        # Get sparkline data (sample every few days for performance)
        step = max(1, len(valid_closes) // 30)
        sparkline = valid_closes[::step]

        # Find 52-week high/low from the data we have
        high_3m = max(valid_closes)
        low_3m = min(valid_closes)

        return {
            'return_3m': round(return_3m, 2),
            'start_price': round(start_price, 2),
            'end_price': round(end_price, 2),
            'high_3m': round(high_3m, 2),
            'low_3m': round(low_3m, 2),
            'sparkline': [round(p, 2) if p else None for p in sparkline]
        }

    except Exception as e:
        print(f"Error fetching price history for {ticker}: {e}")
        return None

def parse_metric(value):
    """Parse a metric value to float"""
    if not value or value == '-':
        return None
    try:
        clean = re.sub(r'[%,]', '', value)
        return float(clean)
    except:
        return None

def analyze_stock(metrics, price_history=None):
    """Analyze stock against Buffett's and Graham's criteria"""
    if not metrics:
        return None

    # Extract key metrics - Buffett favorites
    pe = parse_metric(metrics.get('P/E'))
    forward_pe = parse_metric(metrics.get('Forward P/E'))
    eps_growth = parse_metric(metrics.get('EPS next 5Y'))
    eps_past = parse_metric(metrics.get('EPS past 5Y'))
    roe = parse_metric(metrics.get('ROE'))
    roi = parse_metric(metrics.get('ROI'))
    debt_equity = parse_metric(metrics.get('Debt/Eq'))
    profit_margin = parse_metric(metrics.get('Profit Margin'))
    oper_margin = parse_metric(metrics.get('Oper. Margin'))

    # Graham favorites
    pb = parse_metric(metrics.get('P/B'))
    ps = parse_metric(metrics.get('P/S'))
    current_ratio = parse_metric(metrics.get('Current Ratio'))
    quick_ratio = parse_metric(metrics.get('Quick Ratio'))
    dividend_yield = parse_metric(metrics.get('Dividend %'))
    payout_ratio = parse_metric(metrics.get('Payout'))

    # Additional metrics
    beta = parse_metric(metrics.get('Beta'))
    short_float = parse_metric(metrics.get('Short Float'))
    insider_own = parse_metric(metrics.get('Insider Own'))
    inst_own = parse_metric(metrics.get('Inst Own'))
    perf_ytd = parse_metric(metrics.get('Perf YTD'))
    perf_year = parse_metric(metrics.get('Perf Year'))
    volatility_w = metrics.get('Volatility', '').split()[0] if metrics.get('Volatility') else None
    volatility = parse_metric(volatility_w)

    # 52-week range
    week_52_high = parse_metric(metrics.get('52W High'))
    week_52_low = parse_metric(metrics.get('52W Low'))

    # Market cap & shares
    market_cap = metrics.get('Market Cap', 'N/A')

    # Use fallbacks
    if pe is None:
        pe = forward_pe
    if eps_growth is None:
        eps_growth = eps_past

    analysis = {
        'ticker': metrics['ticker'],
        'company': metrics['company'],
        'price': metrics.get('price'),
        'market_cap': market_cap,
        'metrics': {
            # Buffett metrics
            'pe': pe,
            'forward_pe': forward_pe,
            'eps_growth': eps_growth,
            'roe': roe,
            'roi': roi,
            'debt_equity': debt_equity,
            'profit_margin': profit_margin,
            'oper_margin': oper_margin,
            # Graham metrics
            'pb': pb,
            'ps': ps,
            'current_ratio': current_ratio,
            'quick_ratio': quick_ratio,
            'dividend_yield': dividend_yield,
            'payout_ratio': payout_ratio,
            # Risk metrics
            'beta': beta,
            'short_float': short_float,
            # Ownership
            'insider_own': insider_own,
            'inst_own': inst_own,
            # Performance
            'perf_ytd': perf_ytd,
            'perf_year': perf_year,
            '52w_high': week_52_high,
            '52w_low': week_52_low
        },
        'price_history': price_history
    }

    # Calculate Buffett/Graham score
    score = 0
    max_score = 0
    reasons_for = []
    reasons_against = []

    # === BUFFETT CRITERIA ===

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

    # ROE (15 points) - Buffett loves high ROE
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

    # Profit Margin (10 points) - indicates pricing power/moat
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

    # === GRAHAM CRITERIA ===

    # Price to Book (10 points) - Graham's favorite
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

    # Current Ratio (10 points) - Graham's safety test
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

    # Dividend (bonus points for income investors)
    if dividend_yield is not None and dividend_yield > 0:
        if dividend_yield > 3:
            reasons_for.append(f"Attractive {dividend_yield:.1f}% dividend yield")
        elif dividend_yield > 1.5:
            reasons_for.append(f"Pays {dividend_yield:.1f}% dividend")

    # Insider ownership (Buffett likes skin in the game)
    if insider_own is not None and insider_own > 10:
        reasons_for.append(f"High insider ownership ({insider_own:.1f}%)")

    # Normalize score to 100
    final_score = int((score / max_score) * 100) if max_score > 0 else 0

    analysis['score'] = final_score
    analysis['reasons_for'] = reasons_for[:4]  # Top 4 reasons
    analysis['reasons_against'] = reasons_against[:3]  # Top 3 concerns

    # Generate Warren's verdict
    if final_score >= 75:
        verdict = "BUY"
        emoji = "✅"
        summary = f"Warren would likely approve of {metrics['company']}. "
    elif final_score >= 55:
        verdict = "CONSIDER"
        emoji = "🤔"
        summary = f"{metrics['company']} has some value characteristics. "
    elif final_score >= 35:
        verdict = "CAUTION"
        emoji = "⚠️"
        summary = f"{metrics['company']} doesn't fully meet value criteria. "
    else:
        verdict = "PASS"
        emoji = "❌"
        summary = f"Warren would likely pass on {metrics['company']}. "

    # Build the summary
    if reasons_for:
        summary += reasons_for[0] + ". "
    if reasons_against:
        summary += "However, " + reasons_against[0].lower() + "."
    elif len(reasons_for) > 1:
        summary += reasons_for[1] + "."

    analysis['verdict'] = verdict
    analysis['emoji'] = emoji
    analysis['summary'] = summary

    return analysis

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search/<query>')
def search(query):
    """Search for a ticker by company name"""
    ticker = search_ticker(query)
    return jsonify({'ticker': ticker})

@app.route('/analyze/<query>')
def analyze(query):
    """API endpoint to analyze a stock"""
    # First, resolve the query to a ticker
    ticker = search_ticker(query)

    # Fetch stock data
    metrics = fetch_stock_data(ticker)

    if not metrics:
        return jsonify({
            'error': True,
            'message': f"Could not find '{query}'. Try a ticker symbol (e.g., AAPL) or company name."
        })

    # Fetch price history
    price_history = fetch_price_history(ticker)

    # Analyze
    analysis = analyze_stock(metrics, price_history)
    return jsonify(analysis)

if __name__ == '__main__':
    app.run(debug=True, port=5050)
