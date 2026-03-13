"""
orders.py
─────────
Order placement logic for Binance Futures USDT-M Testnet.

Responsibilities:
  • Build the correct parameter dict for each order type.
  • Call futures_create_order via the client wrapper.
  • Log request parameters BEFORE the call and the full response AFTER.
  • Catch and re-raise Binance-specific exceptions with context.
  • Return a normalised OrderResult dict so the CLI layer never has to
    parse raw Binance response keys.

Supported order types:
  MARKET   — fills immediately at best price
  LIMIT    — rests on the book at a specified price
  STOP     — Stop-Limit: triggers at stopPrice, fills as LIMIT at price
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from binance.exceptions import BinanceAPIException, BinanceRequestException

from bot.client import get_client
from bot.validators import validate_order_params

logger = logging.getLogger(__name__)


# ── Result type ───────────────────────────────────────────────────────────────


class OrderResult:
    """
    Normalised view of a Binance futures order response.
    Shields the CLI from raw Binance key names.
    """

    def __init__(self, raw: dict[str, Any]) -> None:
        self.raw = raw
        self.order_id: int = raw.get("orderId", 0)
        self.symbol: str = raw.get("symbol", "")
        self.status: str = raw.get("status", "")
        self.side: str = raw.get("side", "")
        self.order_type: str = raw.get("type", "")
        self.orig_qty: str = raw.get("origQty", "0")
        self.executed_qty: str = raw.get("executedQty", "0")
        # avgPrice is present for MARKET fills; price for LIMIT/STOP
        self.avg_price: str = raw.get("avgPrice") or raw.get("price") or "0"
        self.stop_price: str = raw.get("stopPrice", "0")
        self.time_in_force: str = raw.get("timeInForce", "")
        self.client_order_id: str = raw.get("clientOrderId", "")
        self.update_time: int = raw.get("updateTime", 0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "orderId": self.order_id,
            "symbol": self.symbol,
            "status": self.status,
            "side": self.side,
            "type": self.order_type,
            "origQty": self.orig_qty,
            "executedQty": self.executed_qty,
            "avgPrice": self.avg_price,
            "stopPrice": self.stop_price,
            "timeInForce": self.time_in_force,
            "clientOrderId": self.client_order_id,
            "updateTime": self.update_time,
        }


# ── Public API ────────────────────────────────────────────────────────────────


def place_order(
    symbol: str,
    side: str,
    order_type: str,
    quantity: float,
    price: Optional[float] = None,
    stop_price: Optional[float] = None,
    time_in_force: str = "GTC",
    dry_run: bool = False,
) -> OrderResult:
    """
    Validate parameters and place a futures order on the Binance Testnet.

    Args:
        symbol:         Trading pair, e.g. 'BTCUSDT'
        side:           'BUY' or 'SELL'
        order_type:     'MARKET', 'LIMIT', or 'STOP'
        quantity:       Contract quantity (base asset units)
        price:          Limit price (required for LIMIT and STOP)
        stop_price:     Trigger price (required for STOP only)
        time_in_force:  'GTC' (default), 'IOC', or 'FOK'
        dry_run:        If True, build and log the params but do NOT send.

    Returns:
        OrderResult with normalised response fields.

    Raises:
        ValueError:              On invalid / inconsistent input parameters.
        BinanceAPIException:     On API-level errors (wrong symbol, insufficient
                                 margin, invalid price precision, etc.)
        BinanceRequestException: On network / connectivity failures.
        RuntimeError:            On unexpected errors.
    """

    # ── 1. Validate ───────────────────────────────────────────────────────────
    params = validate_order_params(
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=quantity,
        price=price,
        stop_price=stop_price,
        time_in_force=time_in_force,
    )

    # ── 2. Build Binance API payload ──────────────────────────────────────────
    api_params: dict[str, Any] = {
        "symbol": params["symbol"],
        "side": params["side"],
        "type": params["order_type"],
        "quantity": params["quantity"],
    }

    ot = params["order_type"]

    if ot == "LIMIT":
        api_params["price"] = params["price"]
        api_params["timeInForce"] = params["time_in_force"]

    elif ot == "STOP":
        # Binance Futures: STOP type = Stop-Limit
        api_params["price"] = params["price"]          # limit price (fill price)
        api_params["stopPrice"] = params["stop_price"] # trigger price
        api_params["timeInForce"] = params["time_in_force"]

    # ── 3. Log the outgoing request ───────────────────────────────────────────
    logger.info(
        "ORDER REQUEST | type=%s | side=%s | symbol=%s | qty=%s | price=%s | stopPrice=%s | tif=%s",
        ot,
        params["side"],
        params["symbol"],
        params["quantity"],
        params.get("price"),
        params.get("stop_price"),
        params["time_in_force"],
    )
    logger.debug("Full API params: %s", api_params)

    # ── 4. Dry-run short-circuit ──────────────────────────────────────────────
    if dry_run:
        logger.info("DRY RUN — order NOT sent to exchange.")
        # Return a synthetic result for display purposes
        synthetic_raw = {
            "orderId": 0,
            "symbol": params["symbol"],
            "status": "DRY_RUN",
            "side": params["side"],
            "type": ot,
            "origQty": str(params["quantity"]),
            "executedQty": "0",
            "avgPrice": str(params.get("price") or 0),
            "stopPrice": str(params.get("stop_price") or 0),
            "timeInForce": params["time_in_force"],
            "clientOrderId": "dry_run",
        }
        return OrderResult(synthetic_raw)

    # ── 5. Place the order ────────────────────────────────────────────────────
    client = get_client()

    try:
        response: dict = client.futures_create_order(**api_params)
    except BinanceAPIException as exc:
        logger.error(
            "ORDER FAILED | BinanceAPIException | code=%s | msg=%s | params=%s",
            exc.status_code,
            exc.message,
            api_params,
        )
        raise  # re-raise so CLI layer can format the message
    except BinanceRequestException as exc:
        logger.error(
            "ORDER FAILED | BinanceRequestException | msg=%s", exc.message
        )
        raise
    except Exception as exc:
        logger.error(
            "ORDER FAILED | Unexpected exception: %s", exc, exc_info=True
        )
        raise RuntimeError(f"Unexpected error placing order: {exc}") from exc

    # ── 6. Log the response ───────────────────────────────────────────────────
    logger.info(
        "ORDER SUCCESS | orderId=%s | status=%s | executedQty=%s | avgPrice=%s",
        response.get("orderId"),
        response.get("status"),
        response.get("executedQty"),
        response.get("avgPrice") or response.get("price"),
    )
    logger.debug("Full API response: %s", response)

    return OrderResult(response)
