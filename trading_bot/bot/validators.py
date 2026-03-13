"""
validators.py
─────────────
Pure validation functions — no I/O, no side-effects.
Each function raises ValueError with a descriptive message on failure,
or returns the cleaned/normalised value on success.

Design rationale:
  • Keeping validation in its own module makes it trivially unit-testable.
  • The CLI layer catches ValueError and displays user-friendly messages.
  • The orders layer also calls these so programmatic callers are protected.
"""

from __future__ import annotations

import math
import re
from typing import Optional


# ── Allowed enumerations ──────────────────────────────────────────────────────

VALID_SIDES = {"BUY", "SELL"}
VALID_ORDER_TYPES = {"MARKET", "LIMIT", "STOP"}  # STOP = Stop-Limit on futures
VALID_TIME_IN_FORCE = {"GTC", "IOC", "FOK"}


# ── Individual field validators ───────────────────────────────────────────────


def validate_symbol(symbol: str) -> str:
    """
    Normalise and validate a futures trading symbol.

    Rules:
      - Non-empty string
      - Only alphanumeric characters (Binance symbols are like BTCUSDT, ETHUSDT)
      - Automatically upper-cased

    Returns the upper-cased symbol.
    """
    if not symbol or not isinstance(symbol, str):
        raise ValueError("Symbol must be a non-empty string.")

    symbol = symbol.strip().upper()

    if not re.match(r"^[A-Z0-9]{3,20}$", symbol):
        raise ValueError(
            f"Invalid symbol '{symbol}'. "
            "Expected 3–20 alphanumeric characters (e.g. BTCUSDT, ETHUSDT)."
        )

    return symbol


def validate_side(side: str) -> str:
    """
    Validate order side.  Returns upper-cased side.
    """
    if not side or not isinstance(side, str):
        raise ValueError("Side must be a non-empty string.")

    side = side.strip().upper()

    if side not in VALID_SIDES:
        raise ValueError(
            f"Invalid side '{side}'. Must be one of: {', '.join(sorted(VALID_SIDES))}."
        )

    return side


def validate_order_type(order_type: str) -> str:
    """
    Validate order type.  Returns upper-cased type.
    """
    if not order_type or not isinstance(order_type, str):
        raise ValueError("Order type must be a non-empty string.")

    order_type = order_type.strip().upper()

    if order_type not in VALID_ORDER_TYPES:
        raise ValueError(
            f"Invalid order type '{order_type}'. "
            f"Must be one of: {', '.join(sorted(VALID_ORDER_TYPES))}."
        )

    return order_type


def validate_quantity(quantity: float) -> float:
    """
    Validate order quantity.

    Rules:
      - Must be a positive finite number
      - Quantity = 0 is rejected (would be silently ignored by exchange otherwise)
    """
    try:
        qty = float(quantity)
    except (TypeError, ValueError):
        raise ValueError(f"Quantity must be a number, got: {quantity!r}.")

    if not math.isfinite(qty):
        raise ValueError(
            f"Quantity must be a finite number, got: {qty}."
        )

    if qty <= 0:
        raise ValueError(
            f"Quantity must be greater than 0, got: {qty}. "
            "Check Binance minimum notional / lot size for this symbol."
        )

    return qty


def validate_price(price: Optional[float], label: str = "Price") -> float:
    """
    Validate a price field (limit price or stop price).

    Args:
        price: The price value to validate.
        label: Human-readable label used in error messages ("Price" / "Stop price").
    """
    if price is None:
        raise ValueError(f"{label} is required but was not provided.")

    try:
        p = float(price)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a number, got: {price!r}.")

    if not math.isfinite(p):
        raise ValueError(f"{label} must be a finite number, got: {p}.")

    if p <= 0:
        raise ValueError(f"{label} must be greater than 0, got: {p}.")

    return p


def validate_time_in_force(tif: str) -> str:
    """
    Validate time-in-force parameter.  Returns upper-cased value.
    """
    if not tif or not isinstance(tif, str):
        raise ValueError("TimeInForce must be a non-empty string.")

    tif = tif.strip().upper()

    if tif not in VALID_TIME_IN_FORCE:
        raise ValueError(
            f"Invalid timeInForce '{tif}'. "
            f"Must be one of: {', '.join(sorted(VALID_TIME_IN_FORCE))}."
        )

    return tif


# ── Composite validator ───────────────────────────────────────────────────────


def validate_order_params(
    symbol: str,
    side: str,
    order_type: str,
    quantity: float,
    price: Optional[float] = None,
    stop_price: Optional[float] = None,
    time_in_force: str = "GTC",
) -> dict:
    """
    Validate all order parameters as a coherent unit.

    Returns a dict of cleaned/normalised values ready to pass to the
    orders layer.  Raises ValueError with a descriptive message on the
    *first* validation failure encountered.

    Cross-field rules enforced here (cannot be done per-field):
      • LIMIT orders require a price.
      • STOP  orders require both price (limit price) and stop_price.
      • MARKET orders must NOT supply a price (prevents user confusion).
    """
    cleaned: dict = {}

    cleaned["symbol"] = validate_symbol(symbol)
    cleaned["side"] = validate_side(side)
    cleaned["order_type"] = validate_order_type(order_type)
    cleaned["quantity"] = validate_quantity(quantity)
    cleaned["time_in_force"] = validate_time_in_force(time_in_force)

    ot = cleaned["order_type"]

    if ot == "MARKET":
        if price is not None:
            raise ValueError(
                "Price must not be supplied for MARKET orders "
                "(the exchange fills at best available price)."
            )
        cleaned["price"] = None
        cleaned["stop_price"] = None

    elif ot == "LIMIT":
        if price is None:
            raise ValueError("Price is required for LIMIT orders.")
        cleaned["price"] = validate_price(price, "Limit price")
        cleaned["stop_price"] = None

    elif ot == "STOP":
        if price is None:
            raise ValueError("Limit price (--price) is required for STOP orders.")
        if stop_price is None:
            raise ValueError("Stop/trigger price (--stop-price) is required for STOP orders.")
        cleaned["price"] = validate_price(price, "Limit price")
        cleaned["stop_price"] = validate_price(stop_price, "Stop price")

    return cleaned
