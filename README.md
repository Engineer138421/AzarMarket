# Azar Market

**Azar Market** is an open-source Python-based financial market monitoring,
intelligence, and Telegram automation platform.

The project is being developed as a modular market-information hub that
collects market data, monitors financial news, stores historical snapshots,
analyzes selected events with AI, and delivers interactive reports and alerts
through Telegram.

> **Project status:** Active development. APIs, data sources, commands, and
> internal architecture may change as the project evolves.

## Overview

Azar Market currently brings together several market-information functions:

- Tehran Stock Exchange (TSE) monitoring
- Gold, currency, oil, and cryptocurrency price monitoring
- Order-book / queue analysis for supported TSE symbols
- Financial news aggregation
- IPO detection and reminder workflow
- AI-assisted news impact analysis
- Market analysis dashboard
- Interactive Telegram price queries
- Personal price alerts
- Gold invoice calculator
- Automated market cards and channel reports
- SQLite-based historical market snapshots
- Daily performance reporting and 24-hour market polls

## Architecture

The current project is intentionally modular:

| Module | Responsibility |
|---|---|
| `bot.py` | Telegram application, handlers, scheduled jobs, AI pipeline, user interactions |
| `market_data.py` | Market data collection and normalization |
| `bourse_service.py` | Tehran Stock Exchange index and symbol/board data |
| `news_service.py` | Multi-source financial news aggregation and filtering |
| `database.py` | SQLite database, market history, alerts, polls, and IPO records |
| `image_generator.py` | Market-card generation using Pillow |
| `template.png` | Visual template used by the market-card generator |

## Market data

The current implementation uses public web/API endpoints for market information.
The exact sources and integrations may evolve over time.

Current market coverage includes, depending on source availability:

- USD / Iranian toman
- EUR / Iranian toman
- Gold 18K
- Gold 24K
- Emami coin
- Half coin
- Quarter coin
- Global gold ounce
- Brent oil
- Tether
- Bitcoin
- Tehran Stock Exchange index and supported symbols

`market_data.py` normalizes incoming numeric data and calculates percentage
changes for the supported assets.

## Tehran Stock Exchange engine

The TSE component supports interactive symbol lookup and market-board
information.

The current bot can expose information such as:

- Last traded price
- Closing price
- Previous-day price
- Permitted daily range
- Trading volume
- Trading value
- Number of trades
- Buy/sell queue status
- Calculated price change percentage

The bot also supports a continuously available market-index value for use in
reports and market cards.

## News and IPO engine

`news_service.py` aggregates financial RSS sources from Iranian and international
markets.

The current source configuration includes feeds such as:

- Sena
- Bourse Press
- Bourse News
- Nabz-e Bourse
- Eghtesad Online
- Tasnim
- Fars
- ISNA
- CoinDesk
- MarketWatch
- CNBC Commodities

The bot can use these news items for filtering, deduplication, market-impact
analysis, and IPO-related workflows.

## AI analysis

The current AI layer uses the Groq Python client and supports a fallback list of
models configured in `bot.py`.

AI-assisted functionality includes:

- Market analysis
- News impact interpretation
- Structured financial explanations
- IPO information extraction workflows
- User-facing analytical responses

AI output should be treated as analysis generated from available data, not as a
guarantee of future market behavior.

## User features

The Telegram interface currently includes workflows such as:

- `/price` — market prices
- `/tse` — TSE symbol lookup
- `/bourse` — TSE symbol lookup
- `/calc` — gold calculation workflow
- `/alert` — create a price alert
- `/myalerts` — view user alerts
- `/news` — market news
- AI-assisted analysis workflows

Additional commands and UI flows are part of ongoing development.

## Automated channel operations

The bot includes scheduled workflows for:

- Periodic market snapshots
- Automated market-card generation
- Channel price reports
- Round-level gold price alerts
- Daily IPO reminders
- Daily performance summaries
- 24-hour prediction polls

The exact schedule is controlled by the current implementation in `bot.py`.

## Historical data

Azar Market uses SQLite for local runtime storage.

The current database includes structures for:

- Market-history snapshots
- User price alerts
- Daily polls
- IPO records

The runtime database file is:

```text
market_history.db
```

It is intentionally excluded from GitHub. The database schema is created and
updated by `database.py` when the application initializes.

This means the public repository contains the database logic, not the private
historical dataset accumulated by a particular deployment.

## Installation

### 1. Clone the repository

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd AzarMarket
```

### 2. Create a virtual environment

Windows:

```bash
python -m venv venv
venv\Scripts\activate
```

macOS/Linux:

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure credentials

Copy:

```text
.env.example
```

to:

```text
gemini-code.env
```

Then set:

```env
BOT_TOKEN=your_telegram_bot_token
GROQ_API_KEY=your_groq_api_key
```

**Never publish `gemini-code.env`.**

### 5. Run

```bash
python bot.py
```

The application initializes the SQLite database automatically when it starts.

## Repository safety

The following are intentionally excluded from Git:

```text
gemini-code.env
*.env
venv/
__pycache__/
market_history.db
*.db
```

Do not remove these protections just to make the project easier to upload.

## Project roadmap

Azar Market is under active development. Planned areas may include:

- More market-data providers
- More TSE analytics
- Improved historical analytics
- More configurable alerts
- Better news classification
- Expanded AI analysis
- Modular provider architecture
- Automated testing
- Improved deployment configuration
- Docker / cloud deployment support
- Public API interfaces
- Better documentation and contributor workflows

The roadmap is expected to evolve with the project.

## Contributing

Contributions are welcome.

Before submitting a Pull Request:

1. Explain the problem being solved.
2. Keep changes focused.
3. Avoid committing secrets or local runtime databases.
4. Test the affected functionality.
5. Update documentation when behavior changes.

## Disclaimer

Azar Market is an informational and software-automation project. Market prices,
news, calculations, AI analyses, and other outputs may contain errors,
interruptions, delays, or inaccuracies.

Nothing in this project constitutes financial, investment, legal, accounting,
or tax advice. Users should independently verify important information before
making financial decisions.

## License

Azar Market is released under the MIT License. See `LICENSE` for details.
