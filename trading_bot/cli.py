"""
cli.py
──────
Command-line interface for the Binance Futures Testnet trading bot.

Built with Typer for automatic --help generation, type coercion, and
rich terminal output.

Commands:
    place   — place a single order (MARKET / LIMIT / STOP)
    account — show futures account balance summary
    price   — show current mark price for a symbol

Run:
    python cli.py --help
    python cli.py place --help
"""

from __future__ import annotations

import logging
import sys
from typing import Optional

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from bot.client import ClientInitError, get_client
from bot.logging_config import setup_logging
from bot.orders import place_order
from binance.exceptions import BinanceAPIException, BinanceRequestException

# ── App setup ─────────────────────────────────────────────────────────────────

app = typer.Typer(
    name="trading-bot",
    help=(
        "[bold cyan]Binance Futures Testnet Trading Bot[/bold cyan]\n\n"
        "Places orders on the USDT-M Futures Testnet.\n"
        "Credentials are read from a [bold].env[/bold] file in the project root."
    ),
    rich_markup_mode="rich",
    add_completion=False,
)

console = Console()
err_console = Console(stderr=True, style="bold red")

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _print_order_summary(
    symbol: str,
    side: str,
    order_type: str,
    quantity: float,
    price: Optional[float],
    stop_price: Optional[float],
    time_in_force: str,
    dry_run: bool,
) -> None:
    """Print a formatted table of what we're about to send."""
    table = Table(title="Order Request", box=box.ROUNDED, show_header=False)
    table.add_column("Field", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")

    rows = [
        ("Symbol", symbol.upper()),
        ("Side", f"[green]{side}[/green]" if side.upper() == "BUY" else f"[red]{side}[/red]"),
        ("Type", order_type.upper()),
        ("Quantity", str(quantity)),
    ]
    if price is not None:
        rows.append(("Limit Price", f"{price:,.4f} USDT"))
    if stop_price is not None:
        rows.append(("Stop/Trigger Price", f"{stop_price:,.4f} USDT"))
    if order_type.upper() != "MARKET":
        rows.append(("Time-in-Force", time_in_force))
    if dry_run:
        rows.append(("Mode", "[yellow]DRY RUN[/yellow]"))

    for field, value in rows:
        table.add_row(field, value)

    console.print()
    console.print(table)


def _print_order_result(result) -> None:
    """Print a formatted table of the exchange's order response."""
    status_colour = {
        "FILLED": "green",
        "NEW": "cyan",
        "PARTIALLY_FILLED": "yellow",
        "CANCELED": "red",
        "REJECTED": "red",
        "DRY_RUN": "yellow",
    }.get(result.status, "white")

    table = Table(title="Order Response", box=box.ROUNDED, show_header=False)
    table.add_column("Field", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")

    table.add_row("Order ID", str(result.order_id))
    table.add_row("Client Order ID", result.client_order_id)
    table.add_row("Symbol", result.symbol)
    table.add_row("Status", f"[{status_colour}]{result.status}[/{status_colour}]")
    table.add_row("Side", result.side)
    table.add_row("Type", result.order_type)
    table.add_row("Orig Qty", result.orig_qty)
    table.add_row("Executed Qty", result.executed_qty)

    avg = float(result.avg_price or 0)
    if avg > 0:
        table.add_row("Avg / Limit Price", f"{avg:,.4f} USDT")

    sp = float(result.stop_price or 0)
    if sp > 0:
        table.add_row("Stop Price", f"{sp:,.4f} USDT")

    if result.time_in_force and result.order_type != "MARKET":
        table.add_row("Time-in-Force", result.time_in_force)

    console.print()
    console.print(table)


# ── Commands ──────────────────────────────────────────────────────────────────


@app.command()
def place(
    symbol: str = typer.Option(
        ...,
        "--symbol", "-s",
        help="Trading pair, e.g. [bold]BTCUSDT[/bold]",
        prompt="Symbol (e.g. BTCUSDT)",
    ),
    side: str = typer.Option(
        ...,
        "--side",
        help="[green]BUY[/green] or [red]SELL[/red]",
        prompt="Side (BUY/SELL)",
    ),
    order_type: str = typer.Option(
        ...,
        "--type", "-t",
        help="MARKET, LIMIT, or STOP (stop-limit)",
        prompt="Order type (MARKET/LIMIT/STOP)",
    ),
    quantity: float = typer.Option(
        ...,
        "--quantity", "-q",
        help="Contract quantity in base asset units",
        prompt="Quantity",
    ),
    price: Optional[float] = typer.Option(
        None,
        "--price", "-p",
        help="Limit price (required for LIMIT and STOP orders)",
    ),
    stop_price: Optional[float] = typer.Option(
        None,
        "--stop-price",
        help="Trigger/stop price (required for STOP orders)",
    ),
    time_in_force: str = typer.Option(
        "GTC",
        "--tif",
        help="Time-in-force: GTC (default), IOC, FOK",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Validate and display the order without sending it to the exchange.",
        is_flag=True,
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="Set log level to DEBUG (very chatty).",
        is_flag=True,
    ),
) -> None:
    """
    Place a MARKET, LIMIT, or STOP order on Binance Futures Testnet.

    [bold]Examples:[/bold]

      # Market buy 0.01 BTC
      python cli.py place -s BTCUSDT --side BUY -t MARKET -q 0.01

      # Limit sell 0.01 BTC at $70,000
      python cli.py place -s BTCUSDT --side SELL -t LIMIT -q 0.01 -p 70000

      # Stop-Limit buy: trigger at $65,000, fill at $65,100
      python cli.py place -s BTCUSDT --side BUY -t STOP -q 0.01 -p 65100 --stop-price 65000

      # Dry-run (no order sent)
      python cli.py place -s BTCUSDT --side BUY -t MARKET -q 0.01 --dry-run
    """
    setup_logging(log_level="DEBUG" if verbose else "INFO")
    logger.info(
        "CLI place command invoked — symbol=%s side=%s type=%s qty=%s price=%s stop_price=%s dry_run=%s",
        symbol, side, order_type, quantity, price, stop_price, dry_run,
    )

    # ── Print request summary ─────────────────────────────────────────────────
    _print_order_summary(
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=quantity,
        price=price,
        stop_price=stop_price,
        time_in_force=time_in_force,
        dry_run=dry_run,
    )

    # ── Confirm (unless dry-run or non-interactive) ───────────────────────────
    if not dry_run and sys.stdin.isatty():
        confirmed = typer.confirm("\nSend this order to the exchange?", default=False)
        if not confirmed:
            console.print("[yellow]Order cancelled by user.[/yellow]")
            raise typer.Exit(0)

    # ── Place the order ───────────────────────────────────────────────────────
    try:
        result = place_order(
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            stop_price=stop_price,
            time_in_force=time_in_force,
            dry_run=dry_run,
        )
    except ValueError as exc:
        err_console.print(f"\n✗ Validation error: {exc}")
        logger.error("Validation error: %s", exc)
        raise typer.Exit(1)
    except ClientInitError as exc:
        err_console.print(f"\n✗ Client init error: {exc}")
        logger.error("Client init error: %s", exc)
        raise typer.Exit(1)
    except BinanceAPIException as exc:
        err_console.print(
            f"\n✗ Binance API error [{exc.status_code}]: {exc.message}"
        )
        logger.error("BinanceAPIException: %s", exc)
        raise typer.Exit(1)
    except BinanceRequestException as exc:
        err_console.print(f"\n✗ Network error: {exc.message}")
        logger.error("BinanceRequestException: %s", exc)
        raise typer.Exit(1)
    except RuntimeError as exc:
        err_console.print(f"\n✗ Unexpected error: {exc}")
        logger.exception("Unexpected runtime error")
        raise typer.Exit(1)

    # ── Print result ──────────────────────────────────────────────────────────
    _print_order_result(result)

    if result.status == "DRY_RUN":
        console.print(
            Panel(
                "[yellow]Dry run complete. Order was NOT sent to the exchange.[/yellow]",
                border_style="yellow",
            )
        )
    elif result.status == "FILLED":
        console.print(
            Panel(
                f"[green]✓ Order FILLED — orderId {result.order_id}[/green]",
                border_style="green",
            )
        )
    elif result.status == "NEW":
        console.print(
            Panel(
                f"[cyan]✓ Order placed — orderId {result.order_id} | Status: NEW (resting on book)[/cyan]",
                border_style="cyan",
            )
        )
    else:
        console.print(
            Panel(
                f"Order submitted — orderId {result.order_id} | Status: {result.status}",
                border_style="white",
            )
        )

    logger.info("CLI place command completed successfully — orderId=%s", result.order_id)


@app.command()
def account(
    verbose: bool = typer.Option(False, "--verbose", "-v", is_flag=True),
) -> None:
    """
    Show your Binance Futures Testnet account balance summary.
    """
    setup_logging(log_level="DEBUG" if verbose else "INFO")

    try:
        client = get_client()
        balances = client.futures_account_balance()
    except ClientInitError as exc:
        err_console.print(f"✗ Client init error: {exc}")
        raise typer.Exit(1)
    except BinanceAPIException as exc:
        err_console.print(f"✗ API error: {exc.message}")
        raise typer.Exit(1)
    except BinanceRequestException as exc:
        err_console.print(f"✗ Network error: {exc.message}")
        raise typer.Exit(1)

    # Filter to assets with non-zero balance
    non_zero = [b for b in balances if float(b.get("balance", 0)) != 0]

    if not non_zero:
        console.print("[yellow]No non-zero balances found on testnet account.[/yellow]")
        return

    table = Table(title="Futures Account Balances", box=box.ROUNDED)
    table.add_column("Asset", style="cyan")
    table.add_column("Balance", style="white", justify="right")
    table.add_column("Available Balance", style="green", justify="right")
    table.add_column("Unrealised PnL", justify="right")

    for b in non_zero:
        pnl = float(b.get("crossUnPnl", 0))
        pnl_str = f"[green]+{pnl:.4f}[/green]" if pnl >= 0 else f"[red]{pnl:.4f}[/red]"
        table.add_row(
            b.get("asset", ""),
            f"{float(b['balance']):.4f}",
            f"{float(b.get('availableBalance', b['balance'])):.4f}",
            pnl_str,
        )

    console.print()
    console.print(table)


@app.command()
def price(
    symbol: str = typer.Argument(..., help="Trading pair, e.g. BTCUSDT"),
    verbose: bool = typer.Option(False, "--verbose", "-v", is_flag=True),
) -> None:
    """
    Show the current mark price for a futures symbol.
    """
    setup_logging(log_level="DEBUG" if verbose else "INFO")

    try:
        client = get_client()
        data = client.futures_mark_price(symbol=symbol.upper())
    except ClientInitError as exc:
        err_console.print(f"✗ Client init error: {exc}")
        raise typer.Exit(1)
    except BinanceAPIException as exc:
        err_console.print(f"✗ API error [{exc.status_code}]: {exc.message}")
        raise typer.Exit(1)
    except BinanceRequestException as exc:
        err_console.print(f"✗ Network error: {exc.message}")
        raise typer.Exit(1)

    mark = float(data.get("markPrice", 0))
    index = float(data.get("indexPrice", 0))
    fr = float(data.get("lastFundingRate", 0)) * 100

    table = Table(title=f"Mark Price — {symbol.upper()}", box=box.ROUNDED, show_header=False)
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Mark Price", f"{mark:,.4f} USDT")
    table.add_row("Index Price", f"{index:,.4f} USDT")
    table.add_row("Last Funding Rate", f"{fr:.4f}%")

    console.print()
    console.print(table)


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app()
