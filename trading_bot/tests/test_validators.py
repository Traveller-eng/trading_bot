"""
tests/test_validators.py
────────────────────────
Unit tests for the validators module.
Uses only stdlib — no third-party packages required.
"""

import sys
import os
import unittest

# Allow importing from project root without installing the package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Stub out the modules that need third-party packages so we can import
# validators.py (which has no external deps) in isolation.
from unittest.mock import MagicMock

# Provide stubs for binance and dotenv so imports don't blow up
for mod_name in ["binance", "binance.client", "binance.exceptions", "dotenv"]:
    sys.modules.setdefault(mod_name, MagicMock())

from bot.validators import (
    validate_symbol,
    validate_side,
    validate_order_type,
    validate_quantity,
    validate_price,
    validate_time_in_force,
    validate_order_params,
)


class TestValidateSymbol(unittest.TestCase):

    def test_valid_symbols(self):
        self.assertEqual(validate_symbol("BTCUSDT"), "BTCUSDT")
        self.assertEqual(validate_symbol("btcusdt"), "BTCUSDT")   # auto-upper
        self.assertEqual(validate_symbol("  ethusdt  "), "ETHUSDT")  # strips

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            validate_symbol("")

    def test_none_raises(self):
        with self.assertRaises(ValueError):
            validate_symbol(None)

    def test_special_chars_raise(self):
        with self.assertRaises(ValueError):
            validate_symbol("BTC-USDT")   # hyphen not allowed

    def test_too_short_raises(self):
        with self.assertRaises(ValueError):
            validate_symbol("BT")  # < 3 chars


class TestValidateSide(unittest.TestCase):

    def test_buy(self):
        self.assertEqual(validate_side("BUY"), "BUY")
        self.assertEqual(validate_side("buy"), "BUY")

    def test_sell(self):
        self.assertEqual(validate_side("SELL"), "SELL")

    def test_invalid(self):
        for bad in ("LONG", "SHORT", "B", "", "buy_sell"):
            with self.assertRaises(ValueError, msg=f"Expected ValueError for '{bad}'"):
                validate_side(bad)


class TestValidateOrderType(unittest.TestCase):

    def test_valid_types(self):
        for t in ("MARKET", "LIMIT", "STOP", "market", "limit", "stop"):
            result = validate_order_type(t)
            self.assertEqual(result, t.upper())

    def test_invalid(self):
        for bad in ("OCO", "TWAP", "", "MKT"):
            with self.assertRaises(ValueError):
                validate_order_type(bad)


class TestValidateQuantity(unittest.TestCase):

    def test_positive_float(self):
        self.assertAlmostEqual(validate_quantity(0.001), 0.001)
        self.assertAlmostEqual(validate_quantity(1), 1.0)
        self.assertAlmostEqual(validate_quantity("0.5"), 0.5)  # string coercion

    def test_zero_raises(self):
        with self.assertRaises(ValueError):
            validate_quantity(0)

    def test_negative_raises(self):
        with self.assertRaises(ValueError):
            validate_quantity(-1)

    def test_non_numeric_raises(self):
        with self.assertRaises(ValueError):
            validate_quantity("abc")

    def test_infinity_raises(self):
        with self.assertRaises(ValueError):
            validate_quantity(float("inf"))

    def test_neg_infinity_raises(self):
        with self.assertRaises(ValueError):
            validate_quantity(float("-inf"))


class TestValidatePrice(unittest.TestCase):

    def test_valid(self):
        self.assertAlmostEqual(validate_price(50000.0), 50000.0)
        self.assertAlmostEqual(validate_price("70000"), 70000.0)

    def test_zero_raises(self):
        with self.assertRaises(ValueError):
            validate_price(0)

    def test_none_raises(self):
        with self.assertRaises(ValueError):
            validate_price(None)

    def test_negative_raises(self):
        with self.assertRaises(ValueError):
            validate_price(-100)


class TestValidateTimeInForce(unittest.TestCase):

    def test_valid(self):
        for tif in ("GTC", "IOC", "FOK", "gtc"):
            self.assertEqual(validate_time_in_force(tif), tif.upper())

    def test_invalid(self):
        with self.assertRaises(ValueError):
            validate_time_in_force("GTX")


class TestValidateOrderParams(unittest.TestCase):
    """Integration-style tests for cross-field validation logic."""

    def _market(self, **kwargs):
        defaults = dict(symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=0.01)
        defaults.update(kwargs)
        return validate_order_params(**defaults)

    def _limit(self, **kwargs):
        defaults = dict(symbol="BTCUSDT", side="SELL", order_type="LIMIT",
                        quantity=0.01, price=70000.0)
        defaults.update(kwargs)
        return validate_order_params(**defaults)

    def _stop(self, **kwargs):
        defaults = dict(symbol="BTCUSDT", side="BUY", order_type="STOP",
                        quantity=0.01, price=65100.0, stop_price=65000.0)
        defaults.update(kwargs)
        return validate_order_params(**defaults)

    # ── MARKET ────────────────────────────────────────────────────────────────

    def test_market_valid(self):
        result = self._market()
        self.assertEqual(result["order_type"], "MARKET")
        self.assertIsNone(result["price"])
        self.assertIsNone(result["stop_price"])

    def test_market_rejects_price(self):
        with self.assertRaises(ValueError):
            self._market(price=50000)

    # ── LIMIT ─────────────────────────────────────────────────────────────────

    def test_limit_valid(self):
        result = self._limit()
        self.assertEqual(result["order_type"], "LIMIT")
        self.assertAlmostEqual(result["price"], 70000.0)
        self.assertIsNone(result["stop_price"])

    def test_limit_requires_price(self):
        with self.assertRaises(ValueError):
            validate_order_params(
                symbol="BTCUSDT", side="BUY", order_type="LIMIT", quantity=0.01
            )

    # ── STOP ──────────────────────────────────────────────────────────────────

    def test_stop_valid(self):
        result = self._stop()
        self.assertEqual(result["order_type"], "STOP")
        self.assertAlmostEqual(result["price"], 65100.0)
        self.assertAlmostEqual(result["stop_price"], 65000.0)

    def test_stop_requires_price(self):
        with self.assertRaises(ValueError):
            validate_order_params(
                symbol="BTCUSDT", side="BUY", order_type="STOP",
                quantity=0.01, stop_price=65000.0  # missing price
            )

    def test_stop_requires_stop_price(self):
        with self.assertRaises(ValueError):
            validate_order_params(
                symbol="BTCUSDT", side="BUY", order_type="STOP",
                quantity=0.01, price=65100.0  # missing stop_price
            )

    # ── Symbol normalisation ──────────────────────────────────────────────────

    def test_symbol_is_normalised(self):
        result = self._market(symbol="btcusdt")
        self.assertEqual(result["symbol"], "BTCUSDT")

    def test_side_is_normalised(self):
        result = self._market(side="buy")
        self.assertEqual(result["side"], "BUY")


class TestOrdersModule(unittest.TestCase):
    """
    Tests for orders.place_order using a mocked Binance client.
    Uses unittest.mock.patch to replace bot.orders.get_client AFTER import,
    which correctly intercepts the already-bound reference in that module.
    """

    @classmethod
    def setUpClass(cls):
        """Import bot.orders once; it uses our stubbed binance modules."""
        # binance stubs were already added at the top of the file
        if "bot.orders" in sys.modules:
            del sys.modules["bot.orders"]
        import bot.orders as orders_mod
        cls.orders_mod = orders_mod

    def _make_response(self, status="FILLED", order_type="MARKET"):
        return {
            "orderId": 12345,
            "symbol": "BTCUSDT",
            "status": status,
            "side": "BUY",
            "type": order_type,
            "origQty": "0.01",
            "executedQty": "0.01",
            "avgPrice": "65000.0",
            "stopPrice": "0",
            "timeInForce": "GTC",
            "clientOrderId": "test_order_123",
            "updateTime": 1700000000000,
        }

    def _mock_client(self, response):
        """Return a MagicMock client pre-loaded with a futures_create_order response."""
        client = MagicMock()
        client.futures_create_order.return_value = response
        return client

    # ── Market order ──────────────────────────────────────────────────────────

    def test_market_order_calls_api_correctly(self):
        client = self._mock_client(self._make_response())
        from unittest.mock import patch
        with patch.object(self.orders_mod, "get_client", return_value=client):
            result = self.orders_mod.place_order(
                symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=0.01
            )
        client.futures_create_order.assert_called_once_with(
            symbol="BTCUSDT", side="BUY", type="MARKET", quantity=0.01
        )
        self.assertEqual(result.status, "FILLED")
        self.assertEqual(result.order_id, 12345)

    # ── Limit order ───────────────────────────────────────────────────────────

    def test_limit_order_includes_price_and_tif(self):
        client = self._mock_client(self._make_response(status="NEW", order_type="LIMIT"))
        from unittest.mock import patch
        with patch.object(self.orders_mod, "get_client", return_value=client):
            result = self.orders_mod.place_order(
                symbol="BTCUSDT", side="SELL", order_type="LIMIT",
                quantity=0.01, price=70000.0
            )
        call_kwargs = client.futures_create_order.call_args.kwargs
        self.assertEqual(call_kwargs["type"], "LIMIT")
        self.assertAlmostEqual(call_kwargs["price"], 70000.0)
        self.assertEqual(call_kwargs["timeInForce"], "GTC")
        self.assertEqual(result.status, "NEW")

    # ── Stop-Limit order ──────────────────────────────────────────────────────

    def test_stop_order_includes_stop_price(self):
        resp = self._make_response(status="NEW", order_type="STOP")
        resp["stopPrice"] = "65000.0"
        client = self._mock_client(resp)
        from unittest.mock import patch
        with patch.object(self.orders_mod, "get_client", return_value=client):
            result = self.orders_mod.place_order(
                symbol="BTCUSDT", side="BUY", order_type="STOP",
                quantity=0.01, price=65100.0, stop_price=65000.0
            )
        call_kwargs = client.futures_create_order.call_args.kwargs
        self.assertAlmostEqual(call_kwargs["stopPrice"], 65000.0)
        self.assertAlmostEqual(call_kwargs["price"], 65100.0)
        self.assertEqual(result.status, "NEW")

    # ── Dry run ───────────────────────────────────────────────────────────────

    def test_dry_run_does_not_call_api(self):
        client = MagicMock()
        from unittest.mock import patch
        with patch.object(self.orders_mod, "get_client", return_value=client):
            result = self.orders_mod.place_order(
                symbol="BTCUSDT", side="BUY", order_type="MARKET",
                quantity=0.01, dry_run=True
            )
        client.futures_create_order.assert_not_called()
        self.assertEqual(result.status, "DRY_RUN")

    # ── Validation error ──────────────────────────────────────────────────────

    def test_missing_limit_price_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.orders_mod.place_order(
                symbol="BTCUSDT", side="BUY", order_type="LIMIT", quantity=0.01
            )

    def test_negative_quantity_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.orders_mod.place_order(
                symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity=-1
            )


class TestOrderResult(unittest.TestCase):
    """Verify OrderResult normalises raw API response fields."""

    def setUp(self):
        if "bot.orders" in sys.modules:
            del sys.modules["bot.orders"]
        from bot.orders import OrderResult
        self.OrderResult = OrderResult

    def test_fields_parsed_correctly(self):
        raw = {
            "orderId": 99,
            "symbol": "ETHUSDT",
            "status": "FILLED",
            "side": "SELL",
            "type": "MARKET",
            "origQty": "1.5",
            "executedQty": "1.5",
            "avgPrice": "3200.00",
            "stopPrice": "0",
            "timeInForce": "GTC",
            "clientOrderId": "abc123",
            "updateTime": 999,
        }
        r = self.OrderResult(raw)
        self.assertEqual(r.order_id, 99)
        self.assertEqual(r.symbol, "ETHUSDT")
        self.assertEqual(r.status, "FILLED")
        self.assertEqual(r.executed_qty, "1.5")
        self.assertEqual(r.avg_price, "3200.00")

    def test_to_dict_round_trip(self):
        raw = {
            "orderId": 1, "symbol": "X", "status": "NEW", "side": "BUY",
            "type": "LIMIT", "origQty": "1", "executedQty": "0",
            "avgPrice": "0", "stopPrice": "0", "timeInForce": "GTC",
            "clientOrderId": "x", "updateTime": 0,
        }
        r = self.OrderResult(raw)
        d = r.to_dict()
        self.assertEqual(d["orderId"], 1)
        self.assertEqual(d["symbol"], "X")


class TestLoggingConfig(unittest.TestCase):
    """Verify setup_logging doesn't error and creates the file handler."""

    def test_idempotent_setup(self):
        import logging
        from bot.logging_config import setup_logging
        setup_logging("WARNING")
        setup_logging("WARNING")  # calling twice must not double-add handlers
        root = logging.getLogger()
        # Should have exactly 2 handlers (file + console)
        self.assertEqual(len(root.handlers), 2)


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestValidateSymbol))
    suite.addTests(loader.loadTestsFromTestCase(TestValidateSide))
    suite.addTests(loader.loadTestsFromTestCase(TestValidateOrderType))
    suite.addTests(loader.loadTestsFromTestCase(TestValidateQuantity))
    suite.addTests(loader.loadTestsFromTestCase(TestValidatePrice))
    suite.addTests(loader.loadTestsFromTestCase(TestValidateTimeInForce))
    suite.addTests(loader.loadTestsFromTestCase(TestValidateOrderParams))
    suite.addTests(loader.loadTestsFromTestCase(TestOrdersModule))
    suite.addTests(loader.loadTestsFromTestCase(TestOrderResult))
    suite.addTests(loader.loadTestsFromTestCase(TestLoggingConfig))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
