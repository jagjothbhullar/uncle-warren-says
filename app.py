#!/usr/bin/env python3
"""
Uncle Warren Says - Web Application
Flask backend for stock analysis
"""

from flask import Flask, render_template, jsonify, request
import requests
from bs4 import BeautifulSoup
import re

app = Flask(__name__)

def fetch_stock_data(ticker):
    """Fetch stock metrics from Finviz"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }
    url = f"https://finviz.com/quote.ashx?t={ticker.upper()}"

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, 'html.parser')

        # Check if stock exists
        error = soup.find('div', {'class': 'content'})
        if error and 'not found' in error.text.lower():
            return None

        # Get company name
        title = soup.find('a', {'class': 'tab-link'})
        company_name = title.text.strip() if title else ticker.upper()

        # Find the snapshot table with all metrics
        table = soup.find('table', {'class': 'snapshot-table2'})
        if not table:
            return None

        metrics = {'ticker': ticker.upper(), 'company': company_name}
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

def parse_metric(value):
    """Parse a metric value to float"""
    if not value or value == '-':
        return None
    try:
        # Remove % and other characters
        clean = re.sub(r'[%,]', '', value)
        return float(clean)
    except:
        return None

def analyze_stock(metrics):
    """Analyze stock against Buffett's criteria"""
    if not metrics:
        return None

    # Extract key metrics
    pe = parse_metric(metrics.get('P/E'))
    forward_pe = parse_metric(metrics.get('Forward P/E'))
    eps_growth = parse_metric(metrics.get('EPS next 5Y'))
    eps_past = parse_metric(metrics.get('EPS past 5Y'))
    roe = parse_metric(metrics.get('ROE'))
    debt_equity = parse_metric(metrics.get('Debt/Eq'))
    profit_margin = parse_metric(metrics.get('Profit Margin'))
    current_ratio = parse_metric(metrics.get('Current Ratio'))

    # Use forward P/E if regular P/E not available
    if pe is None:
        pe = forward_pe

    # Use past EPS growth if future not available
    if eps_growth is None:
        eps_growth = eps_past

    analysis = {
        'ticker': metrics['ticker'],
        'company': metrics['company'],
        'metrics': {
            'pe': pe,
            'eps_growth': eps_growth,
            'roe': roe,
            'debt_equity': debt_equity,
            'profit_margin': profit_margin
        },
        'checks': {
            'pe_ok': pe is not None and pe < 35 and pe > 0,
            'eps_ok': eps_growth is not None and eps_growth > 10,
            'roe_ok': roe is not None and roe > 15
        }
    }

    # Calculate Buffett score
    score = 0
    reasons_for = []
    reasons_against = []

    # P/E Analysis
    if pe is not None and pe > 0:
        if pe < 15:
            score += 25
            reasons_for.append(f"Attractively valued at {pe:.1f}x earnings")
        elif pe < 20:
            score += 20
            reasons_for.append(f"Reasonably priced at {pe:.1f}x earnings")
        elif pe < 25:
            score += 15
            reasons_for.append(f"Fairly valued at {pe:.1f}x earnings")
        elif pe < 35:
            score += 10
            reasons_against.append(f"P/E of {pe:.1f} is on the higher side")
        else:
            score += 0
            reasons_against.append(f"P/E of {pe:.1f} exceeds Buffett's threshold of 35")
    else:
        reasons_against.append("No P/E ratio available (may be unprofitable)")

    # EPS Growth Analysis
    if eps_growth is not None:
        if eps_growth > 20:
            score += 25
            reasons_for.append(f"Excellent earnings growth of {eps_growth:.1f}%")
        elif eps_growth > 15:
            score += 20
            reasons_for.append(f"Strong earnings growth of {eps_growth:.1f}%")
        elif eps_growth > 10:
            score += 15
            reasons_for.append(f"Solid earnings growth of {eps_growth:.1f}%")
        else:
            score += 5
            reasons_against.append(f"EPS growth of {eps_growth:.1f}% is below 10% threshold")
    else:
        reasons_against.append("Earnings growth data not available")

    # ROE Analysis
    if roe is not None:
        if roe > 30:
            score += 25
            reasons_for.append(f"Exceptional return on equity of {roe:.1f}%")
        elif roe > 20:
            score += 20
            reasons_for.append(f"Strong return on equity of {roe:.1f}%")
        elif roe > 15:
            score += 15
            reasons_for.append(f"Solid return on equity of {roe:.1f}%")
        else:
            score += 5
            reasons_against.append(f"ROE of {roe:.1f}% is below 15% threshold")
    else:
        reasons_against.append("ROE data not available")

    # Debt/Equity Analysis
    if debt_equity is not None:
        if debt_equity < 0.5:
            score += 25
            reasons_for.append(f"Very low debt (D/E: {debt_equity:.2f})")
        elif debt_equity < 1.0:
            score += 20
            reasons_for.append(f"Conservative debt levels (D/E: {debt_equity:.2f})")
        elif debt_equity < 1.5:
            score += 15
        elif debt_equity < 2.0:
            score += 10
            reasons_against.append(f"Moderate debt levels (D/E: {debt_equity:.2f})")
        else:
            score += 0
            reasons_against.append(f"High debt (D/E: {debt_equity:.2f}) adds risk")

    analysis['score'] = score
    analysis['reasons_for'] = reasons_for
    analysis['reasons_against'] = reasons_against

    # Generate Warren's verdict
    if score >= 80:
        verdict = "BUY"
        emoji = "✅"
        summary = f"Warren would likely approve of {metrics['company']}. "
    elif score >= 60:
        verdict = "CONSIDER"
        emoji = "🤔"
        summary = f"{metrics['company']} has some Buffett-worthy qualities. "
    elif score >= 40:
        verdict = "CAUTION"
        emoji = "⚠️"
        summary = f"{metrics['company']} doesn't fully meet Buffett's criteria. "
    else:
        verdict = "PASS"
        emoji = "❌"
        summary = f"Warren would likely pass on {metrics['company']}. "

    # Build the 2-3 sentence explanation
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

@app.route('/analyze/<ticker>')
def analyze(ticker):
    """API endpoint to analyze a stock"""
    metrics = fetch_stock_data(ticker)

    if not metrics:
        return jsonify({
            'error': True,
            'message': f"Could not find stock '{ticker.upper()}'. Please check the ticker symbol."
        })

    analysis = analyze_stock(metrics)
    return jsonify(analysis)

if __name__ == '__main__':
    app.run(debug=True, port=5050)
