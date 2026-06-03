# DumbMoney

Real time stock screener powered by Alpaca data. Live prices, ATR trailing stops, portfolio tracking, AI analysis, options chains, and full technical fundamentals. All data downloads automatically so you can browse completely offline.

## Features

Live stock screener with real time price updates via Alpaca WebSocket. Filter thousands of stocks by price, volume, weighted alpha, ATR status, profit status, streaks, exchange, and more. Every column is sortable and searchable. Date filter lets you see the exact market state on any past date.

ATR trailing stop indicator built on 14 period Wilder smoothing with Supertrend logic. Green when price is above the stop, red when below. Cross signals show exactly when the trend flips. Change timeframes from 1 day to 1 week to 1 month and ATR recalculates automatically for that period.

Portfolio manager with nested groups. Create portfolios, add symbols with quantity and average price, see live P&L updating in real time. Group multiple portfolios together for combined tracking. Each symbol opens a full stock detail page with chart, AI analysis, corporate events, volume profile, and options chain. Copy symbols between portfolios with one click.

AI analysis scores every stock on momentum, volume, technicals, trendlines, sentiment, and events. Overall score from 0 to 100 with clear buy, hold, sell signals. All computed automatically during refresh.

Pre market and post market prices for every stock. Profitability estimates from real financial data via yfinance. Weighted alpha calculated from historical bars with split aware lookback optimization.

Designed to feel like a professional trading platform without the complexity. Everything runs locally. No subscriptions to external screener services needed. Your data, your machine, your analysis.

## Requirements

Python 3.9+ with the packages in requirements.txt. An Alpaca Markets API key (free paper trading account works). That is it.

## Quick Start

Install requirements, set your API keys in the .env file or directly in app.py, then run:

```
python dumbmoney/app.py
```

Open http://localhost:2957 in your browser. The initial data download grabs everything automatically. After that every refresh keeps all your data up to date with the latest prices, bars, financials, and technicals.

Or double click start_dumbmoney.bat on Windows.

## Contact

Built by Mohit. For questions, access, or custom work reach out at mohitmagaldesign@gmail.com

Premium access available. This is years of research packed into one clean tool.
