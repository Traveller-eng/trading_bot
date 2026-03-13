# Binance Futures Testnet Trading Bot

A clean, production-structured Python CLI application for placing orders on the
**Binance USDT-M Futures Testnet**.

---

## Features

| Feature | Details |
|---|---|
| Order types | MARKET, LIMIT, STOP (Stop-Limit) |
| Sides | BUY and SELL |
| CLI | Typer — auto-generated `--help`, type coercion, coloured output |
| Validation | Full cross-field validation before any API call |
| Logging | Rotating file log (`logs/trading_bot.log`) + console warnings |
| Error handling | Binance API errors, network failures, invalid input all caught |
| Dry-run mode | Validate and display without sending to exchange |
| Bonus commands | `account` (balance summary), `price` (mark price lookup) |

---

## Project Structure

```
trading_bot/
├── bot/
│   ├── __init__.py
│   ├── client.py          # Binance testnet client wrapper (auth + init)
│   ├── orders.py          # Order placement logic + OrderResult type
│   ├── validators.py      # Pure input validation — no I/O, no side-effects
│   └── logging_config.py  # Rotating file + console log setup
├── tests/
│   └── test_validators.py # 40 unit tests (stdlib only, no extra deps)
├── logs/                  # Log files created at runtime (git-ignored)
├── cli.py                 # Typer CLI entry point
├── .env.example           # Credential template
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Setup

### 1. Clone / unzip the project

```bash
git clone <repo-url>
cd trading_bot
```

### 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Get Testnet API credentials

1. Go to **[https://testnet.binancefuture.com](https://testnet.binancefuture.com)**
2. Log in (GitHub OAuth works)
3. Navigate to **API Management** (top-right profile menu)
4. Click **Generate** — copy both the API Key and Secret immediately (the secret is shown only once)

### 5. Configure credentials

```bash
cp .env.example .env
# Edit .env and paste your credentials:
#   BINANCE_TESTNET_API_KEY=xxxx
#   BINANCE_TESTNET_API_SECRET=xxxx
```

> ⚠️ **Never commit `.env` to version control.** It is already in `.gitignore`.

---

## Usage

### Place a MARKET order

```bash
# Buy 0.01 BTC at market price
python cli.py place --symbol BTCUSDT --side BUY --type MARKET --quantity 0.01

# Short-form flags
python cli.py place -s BTCUSDT --side BUY -t MARKET -q 0.01
```

### Place a LIMIT order

```bash
# Sell 0.01 BTC at $70,000 (rests on book)
python cli.py place -s BTCUSDT --side SELL -t LIMIT -q 0.01 --price 70000
```

### Place a STOP (Stop-Limit) order

```bash
# Buy 0.01 BTC: triggers when price hits $65,000, fills as limit at $65,100
python cli.py place -s BTCUSDT --side BUY -t STOP -q 0.01 \
    --price 65100 --stop-price 65000
```

### Dry-run (no order sent)

```bash
python cli.py place -s BTCUSDT --side BUY -t MARKET -q 0.01 --dry-run
```

### Interactive mode (prompts for all fields)

```bash
python cli.py place
# You will be prompted for: Symbol, Side, Type, Quantity
# Then shown a summary and asked to confirm before sending
```

### Check account balance

```bash
python cli.py account
```

### Check mark price

```bash
python cli.py price BTCUSDT
```

### Help

```bash
python cli.py --help
python cli.py place --help
```

---

## CLI Options Reference

### `place` command

| Option | Short | Required | Description |
|---|---|---|---|
| `--symbol` | `-s` | Yes | Trading pair (e.g. `BTCUSDT`) |
| `--side` | | Yes | `BUY` or `SELL` |
| `--type` | `-t` | Yes | `MARKET`, `LIMIT`, or `STOP` |
| `--quantity` | `-q` | Yes | Contract quantity (base asset) |
| `--price` | `-p` | LIMIT/STOP | Limit price in USDT |
| `--stop-price` | | STOP only | Trigger price in USDT |
| `--tif` | | No | `GTC` (default), `IOC`, `FOK` |
| `--dry-run` | | No | Validate without sending |
| `--verbose` | `-v` | No | Debug-level log output |

---

## Validation Rules

| Field | Rules |
|---|---|
| Symbol | 3–20 alphanumeric chars; auto-uppercased |
| Side | Must be `BUY` or `SELL` |
| Type | Must be `MARKET`, `LIMIT`, or `STOP` |
| Quantity | Must be a positive number |
| Price | Required for `LIMIT` and `STOP`; must be > 0; must NOT be set for `MARKET` |
| Stop Price | Required only for `STOP`; must be > 0 |
| TimeInForce | `GTC`, `IOC`, or `FOK` only |

---

## Logging

All API activity is logged to `logs/trading_bot.log`:

```
2024-01-15 10:23:01 | INFO     | bot.orders:78  | ORDER REQUEST | type=MARKET | side=BUY | symbol=BTCUSDT | qty=0.01 | price=None | stopPrice=None | tif=GTC
2024-01-15 10:23:02 | INFO     | bot.orders:103 | ORDER SUCCESS | orderId=123456 | status=FILLED | executedQty=0.01 | avgPrice=65432.1
```

- **File handler**: DEBUG level and above, rotating at 5 MB, 3 backups
- **Console handler**: WARNING and above only (keeps terminal clean)
- Use `--verbose` to promote console output to DEBUG

---

## Running Tests

```bash
python tests/test_validators.py
# Expected: Ran 40 tests in ~0.05s — OK
```

No extra packages needed — tests use only `unittest` and `unittest.mock` from stdlib.

---

## Assumptions

1. **USDT-M Futures only** — The bot uses `futures_create_order`. COIN-M futures use a different endpoint and are not supported.
2. **Quantity precision** — You must supply quantities that match the symbol's lot size filter (e.g. for BTCUSDT on testnet, minimum is 0.001). The bot forwards Binance's precision error as a clear API error message rather than silently rounding.
3. **Testnet balances** — The Binance Futures Testnet periodically resets balances. If your balance shows 0, log in to the testnet web UI and claim free testnet funds.
4. **TimeInForce defaults to GTC** — "Good Till Cancelled" is the most common choice and the safest default.
5. **STOP = Stop-Limit on Futures** — Binance Futures uses `type=STOP` for stop-limit orders (not `STOP_MARKET`). `STOP_MARKET` is not implemented but is a trivial extension of the same pattern.

---

## Requirements

```text
python-binance==1.0.19
typer[all]>=0.15.0
python-dotenv==1.0.1
rich>=13.7.1
```

Python 3.8+ required.
