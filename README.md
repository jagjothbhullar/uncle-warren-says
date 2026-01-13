# Uncle Warren Says

A stock recommendation tool based on Warren Buffett's traditional value investing metrics.

## Overview

This project screens stocks using Buffett's time-tested investment criteria:

- **P/E Ratio < 35** - Reasonable valuation
- **EPS Growth > 10%** - Growing earnings power
- **ROE > 15%** - Efficient capital allocation
- **Strong competitive moat** - Durable business advantage

## Key Metrics

The tool evaluates stocks across multiple Buffett-style dimensions:

| Metric | What It Measures | Buffett's View |
|--------|-----------------|----------------|
| P/E Ratio | Price relative to earnings | Lower = cheaper, but quality matters |
| EPS Growth | Earnings momentum | Consistent growth = compounding machine |
| ROE | Return on equity | High ROE = efficient capital use |
| Debt/Equity | Financial leverage | Lower = more conservative |
| Profit Margin | Pricing power | Higher = stronger moat |

## Installation

```bash
# Clone the repo
git clone https://github.com/jagjothbhullar/uncle-warren-says.git
cd uncle-warren-says

# Install dependencies
pip install pandas requests beautifulsoup4
```

## Usage

```bash
python uncle_warren_says.py
```

This generates:
- `uncle_warren_recommendations.csv` - Full data export
- `uncle_warren_report.txt` - Formatted report with summaries
- `uncle_warren_data.json` - JSON format for integrations

## Sample Output

Top picks based on Buffett Score (out of 100):

1. **BRK.B** (90) - Berkshire Hathaway
2. **JNJ** (80) - Johnson & Johnson
3. **AXP** (75) - American Express
4. **V** (75) - Visa Inc.
5. **UNH** (75) - UnitedHealth Group

## Data Sources

- Market data via [Finviz](https://finviz.com)
- Fundamental metrics from public filings

## Disclaimer

This tool is for educational purposes only. It is not financial advice. Always do your own research and consult with a qualified financial advisor before making investment decisions.

## Author

**Jagjoth Bhullar**
Deputy General Counsel, San Jose Sharks
[Portfolio](https://jagjothbhullar.github.io/personal-blog/)

## License

MIT License
