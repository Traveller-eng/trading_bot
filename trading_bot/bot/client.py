"""
client.py
─────────
Thin wrapper that initialises a python-binance Client pointed at the
Binance Futures USDT-M Testnet.

Design decisions:
  • Credentials are read from environment variables (never hard-coded).
    python-dotenv loads them from a .env file in the project root.
  • testnet=True in python-binance routes futures endpoints to
    https://testnet.binancefuture.com automatically.
  • The wrapper exposes a single get_client() factory so the rest of the
    application never imports binance.Client directly — making it easy to
    swap implementations or mock in tests.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Optional

from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env from the project root (two levels up from this file)
_ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
load_dotenv(dotenv_path=_ENV_PATH)


class ClientInitError(RuntimeError):
    """Raised when the Binance client cannot be initialised."""


@lru_cache(maxsize=1)
def get_client() -> Client:
    """
    Create (or return the cached) Binance testnet client.

    Environment variables required:
        BINANCE_TESTNET_API_KEY     — your testnet API key
        BINANCE_TESTNET_API_SECRET  — your testnet API secret

    Raises:
        ClientInitError: if credentials are missing or the exchange
                         is unreachable at startup.
    """
    api_key = os.getenv("BINANCE_TESTNET_API_KEY", "").strip()
    api_secret = os.getenv("BINANCE_TESTNET_API_SECRET", "").strip()

    if not api_key or not api_secret:
        raise ClientInitError(
            "Missing Binance Testnet credentials. "
            "Set BINANCE_TESTNET_API_KEY and BINANCE_TESTNET_API_SECRET "
            "in your .env file (see .env.example)."
        )

    logger.debug("Initialising Binance Futures Testnet client (testnet=True).")

    try:
        client = Client(
            api_key=api_key,
            api_secret=api_secret,
            testnet=True,
            requests_params={"timeout": 10},
        )
        # Quick connectivity check — fetches server time, no auth needed
        server_time = client.futures_time()
        logger.debug(
            "Testnet connection OK — server time: %s ms",
            server_time.get("serverTime"),
        )
    except BinanceAPIException as exc:
        logger.error("Binance API error during client init: %s", exc)
        raise ClientInitError(f"API error: {exc}") from exc
    except BinanceRequestException as exc:
        logger.error("Network error during client init: %s", exc)
        raise ClientInitError(
            f"Network error connecting to testnet: {exc}"
        ) from exc
    except Exception as exc:
        logger.error("Unexpected error during client init: %s", exc)
        raise ClientInitError(f"Unexpected error: {exc}") from exc

    return client
