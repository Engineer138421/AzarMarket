# Azar Market

**Azar Market** is an open-source Python-based financial market monitoring,
intelligence, and Telegram automation platform.

The project is being developed as a modular market-information hub that
collects market data, monitors financial news, stores historical snapshots,
analyzes selected events with AI, and delivers interactive reports and alerts
through Telegram.

> **Project status:** Active development. APIs, data sources, commands, and
> internal architecture may change as the project evolves.

---

## Overview

Azar Market brings together several market-information and automation
capabilities in a single Telegram-based platform:

- Tehran Stock Exchange (TSE) monitoring
- Gold and currency price monitoring
- Oil and cryptocurrency price monitoring
- Order-book and queue analysis for supported TSE symbols
- Financial news aggregation
- IPO detection and reminder workflows
- AI-assisted market and news analysis
- Interactive Telegram market queries
- Personal price alerts
- Gold calculation and invoice workflow
- Automated market cards and channel reports
- SQLite-based historical market snapshots
- Daily performance reporting
- 24-hour market prediction polls

---

## Architecture

Azar Market is organized into modular Python components:

| Module | Responsibility |
|---|---|
| `bot.py` | Telegram application, command handlers, scheduled jobs, AI pipeline, and user interactions |
| `market_data.py` | Market data collection, normalization, and price calculations |
| `bourse_service.py` | Tehran Stock Exchange index and symbol/board data |
| `news_service.py` | Multi-source financial news aggregation and filtering |
| `database.py` | SQLite database, market history, alerts, polls, and IPO records |
| `image_generator.py` | Market-card generation using Pillow |
| `template.png` | Visual template used by the market-card generator |

The architecture is designed to allow individual services and data providers to
evolve independently as the project grows.

---

## Market Data

The current implementation uses public web and API endpoints for market
information. Data sources and integrations may change over time depending on
availability, reliability, and project requirements.

Current market coverage includes:

- USD / Iranian toman
- EUR / Iranian toman
- Gold 18K
- Gold 24K
- Emami coin
- Half coin
- Quarter coin
- Global gold ounce
- Brent oil
- Bitcoin
- Tehran Stock Exchange index
- Supported Tehran Stock Exchange symbols

`market_data.py` normalizes incoming numeric values and calculates percentage
changes for supported assets.

---

## Tehran Stock Exchange Engine

The TSE component provides interactive market information for supported symbols
and market indices.

The current implementation can expose information such as:

- Last traded price
- Closing price
- Previous-day price
- Permitted daily range
- Trading volume
- Trading value
- Number of trades
- Buy/sell queue status
- Calculated price-change percentage

The service also includes resilience mechanisms for accessing TSE-related web
data and supports market-index information for reports and market cards.

---

## News and IPO Engine

`news_service.py` aggregates financial news from Iranian and international
sources.

The current source configuration includes feeds such as:

- Sana
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

The news engine can be used for:

- News collection
- Filtering
- Deduplication
- Market-impact analysis
- Asset and direction classification
- IPO-related workflows

### IPO Radar

The project also includes an IPO-oriented workflow that can extract structured
information from relevant announcements, including fields such as:

- Symbol
- Offering price
- Share quantity
- Capital-related information
- Liquidity or participation information

Relevant IPO records are stored in the local SQLite database to support
deduplication and reminder workflows.

---

## AI Analysis

The current AI layer uses the **Groq Python client** and supports a fallback
list of models configured in `bot.py`.

AI-assisted functionality includes:

- Market analysis
- News-impact interpretation
- Structured financial explanations
- IPO information extraction workflows
- User-facing analytical responses

AI-generated results are based on available market and news information and
should not be interpreted as guarantees of future market behavior.

---

## Telegram User Features

The Telegram interface currently includes workflows such as:

| Command | Function |
|---|---|
| `/price` | Market price information |
| `/tse` | TSE symbol lookup |
| `/bourse` | TSE symbol lookup |
| `/calc` | Gold calculation workflow |
| `/alert` | Create a price alert |
| `/myalerts` | View user alerts |
| `/news` | Market news |
| AI workflows | Market and news analysis |

Additional commands, interfaces, and workflows are part of ongoing development.

---

## Gold Calculation

Azar Market includes a gold calculation workflow designed to provide
informational purchase and pricing calculations.

The current workflow supports calculations involving:

- 18K gold
- Wage / making charges
- Seller profit
- VAT
- Melted gold / bullion-style calculations
- Gold trading calculations

The exact calculation logic is implemented in `bot.py` and may evolve as the
project develops.

---

## Automated Channel Operations

The bot includes scheduled workflows for automated market monitoring and
reporting.

These workflows include:

- Periodic market snapshots
- Automated market-card generation
- Channel price reports
- Round-level gold price alerts
- Daily IPO reminders
- Daily performance summaries
- 24-hour market prediction polls

The exact schedule is controlled by the current implementation in `bot.py`.

---

## Historical Data

Azar Market uses SQLite for local runtime storage.

The database currently supports structures for:

- Market-history snapshots
- User price alerts
- Daily polls
- IPO records

The runtime database file is:

```text
market_history.db
```

The database file is intentionally excluded from the public Git repository.

The database schema is created and updated by `database.py` when the application
initializes.

This means the public repository contains the database logic, while the private
historical dataset accumulated by a particular deployment remains local.

---

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/Engineer138421/AzarMarket.git
cd AzarMarket
```

### 2. Create a Virtual Environment

#### Windows

```bash
python -m venv venv
venv\Scripts\activate
```

#### macOS / Linux

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Credentials

The project uses a local environment file for private credentials.

Copy:

```text
.env.example
```

to:

```text
gemini-code.env
```

Then configure the required credentials:

```env
BOT_TOKEN=your_telegram_bot_token
GROQ_API_KEY=your_groq_api_key
```

**Never publish `gemini-code.env`.**

### 5. Run the Bot

```bash
python bot.py
```

The application initializes the SQLite database automatically when it starts.

---

## Configuration and Security

Private credentials and local runtime data must never be committed to Git.

The following files and directories are intentionally excluded from Git:

```text
gemini-code.env
*.env
venv/
__pycache__/
market_history.db
*.db
*.sqlite
*.sqlite3
```

Never commit:

- Telegram bot tokens
- API keys
- Passwords
- Private credentials
- Local runtime databases
- Other sensitive configuration files

If a secret is accidentally exposed, revoke or rotate it immediately.

For additional security guidance, see:

[`SECURITY.md`](SECURITY.md)

---

## Development

Azar Market is currently under active development.

The project is being developed with a focus on:

- Modular market-data services
- Financial information aggregation
- Telegram automation
- AI-assisted analysis
- Historical market data
- Automated reporting
- Extensible provider architecture

APIs, commands, data providers, and internal implementation details may change
during development.

---

## Project Roadmap

Planned development areas may include:

- Additional market-data providers
- Expanded TSE analytics
- Improved historical analytics
- More configurable alerts
- Improved news classification
- Expanded AI analysis
- Modular provider architecture
- Automated testing
- Improved deployment configuration
- Docker and cloud deployment support
- Public API interfaces
- Better documentation
- Improved contributor workflows

The roadmap is expected to evolve as the project develops.

---

## Contributing

Contributions are welcome.

Before submitting a Pull Request:

1. Explain the problem being solved.
2. Keep changes focused and reviewable.
3. Avoid committing secrets or local runtime databases.
4. Test the affected functionality.
5. Update documentation when behavior changes.
6. Follow the existing project structure and coding conventions.

For larger changes, opening an issue before implementation is recommended so the
proposed direction can be discussed.

---

## Security

If you discover a security issue, please avoid publishing sensitive credentials
or exploit details in a public issue.

See [`SECURITY.md`](SECURITY.md) for security-related guidance.

---

## Disclaimer

Azar Market is an informational and software-automation project.

Market prices, financial news, calculations, AI analyses, and other outputs may
contain errors, interruptions, delays, or inaccuracies.

Nothing in this project constitutes financial, investment, legal, accounting,
or tax advice.

Users should independently verify important information before making financial
decisions.

---

## License

Azar Market is released under the MIT License.

See [`LICENSE`](LICENSE) for details.