"""
MT5 Service - handles all MetaTrader 5 operations.
Connect, read positions, send orders, modify, close.
"""

import MetaTrader5 as mt5
from datetime import datetime
from typing import List, Optional, Tuple
from loguru import logger

from config.settings import MT5Account
from models.trade_models import TradePosition, OrderResult


class MT5Service:
    """Service for interacting with MetaTrader 5 terminal."""

    def __init__(self):
        self._connected = False
        self._current_account: Optional[MT5Account] = None

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def current_label(self) -> str:
        return self._current_account.label if self._current_account else "Unknown"

    # ─────────────────────────────────────────────
    # Connection
    # ─────────────────────────────────────────────

    def connect(self, account: MT5Account) -> bool:
        """Connect to MT5 terminal with given account."""
        try:
            # Shutdown any existing connection
            if self._connected:
                self.disconnect()

            # Initialize MT5
            init_kwargs = {
                "login": account.login,
                "password": account.password,
                "server": account.server,
            }
            if account.mt5_path:
                init_kwargs["path"] = account.mt5_path

            if not mt5.initialize(**init_kwargs):
                error = mt5.last_error()
                logger.error(f"❌ MT5 init failed [{account.label}]: {error}")
                return False

            # Verify login
            info = mt5.account_info()
            if info is None:
                logger.error(f"❌ Cannot get account info [{account.label}]")
                mt5.shutdown()
                return False

            self._connected = True
            self._current_account = account
            logger.debug(
                f"✅ Connected [{account.label}] "
                f"Login:{info.login} Balance:{info.balance:.2f} "
                f"Equity:{info.equity:.2f} Server:{info.server}"
            )
            return True

        except Exception as e:
            logger.error(f"❌ MT5 connect exception [{account.label}]: {e}")
            return False

    def disconnect(self):
        """Disconnect from MT5 terminal."""
        try:
            mt5.shutdown()
        except Exception:
            pass
        self._connected = False
        self._current_account = None

    # ─────────────────────────────────────────────
    # Account Info
    # ─────────────────────────────────────────────

    def get_balance(self) -> float:
        """Get current account balance."""
        info = mt5.account_info()
        if info is None:
            logger.error("❌ Cannot get account balance")
            return 0.0
        return info.balance

    def get_equity(self) -> float:
        """Get current account equity."""
        info = mt5.account_info()
        if info is None:
            return 0.0
        return info.equity

    def get_account_info(self) -> Optional[dict]:
        """Get full account information."""
        info = mt5.account_info()
        if info is None:
            return None
        return {
            "login": info.login,
            "balance": info.balance,
            "equity": info.equity,
            "margin": info.margin,
            "margin_free": info.margin_free,
            "margin_level": info.margin_level,
            "profit": info.profit,
            "server": info.server,
            "currency": info.currency,
            "leverage": info.leverage,
        }

    # ─────────────────────────────────────────────
    # Positions
    # ─────────────────────────────────────────────

    def get_positions(self, symbol: str = None) -> List[TradePosition]:
        """Get all open positions, optionally filtered by symbol."""
        if symbol:
            positions = mt5.positions_get(symbol=symbol)
        else:
            positions = mt5.positions_get()

        if positions is None:
            return []

        result = []
        for pos in positions:
            result.append(TradePosition(
                ticket=pos.ticket,
                symbol=pos.symbol,
                type=pos.type,
                volume=pos.volume,
                price_open=pos.price_open,
                price_current=pos.price_current,
                sl=pos.sl,
                tp=pos.tp,
                profit=pos.profit,
                swap=pos.swap,
                time=datetime.fromtimestamp(pos.time),
                time_update=datetime.fromtimestamp(pos.time_update),
                magic=pos.magic,
                comment=pos.comment if pos.comment else "",
            ))

        return result

    # ─────────────────────────────────────────────
    # Symbol Info
    # ─────────────────────────────────────────────

    def get_symbol_info(self, symbol: str) -> Optional[dict]:
        """Get symbol trading info (tick_value, tick_size, volume_step, etc.)."""
        info = mt5.symbol_info(symbol)
        if info is None:
            logger.error(f"❌ Symbol not found: {symbol}")
            return None

        # Make sure symbol is visible
        if not info.visible:
            mt5.symbol_select(symbol, True)
            info = mt5.symbol_info(symbol)

        return {
            "symbol": info.name,
            "point": info.point,
            "digits": info.digits,
            "tick_value": info.trade_tick_value,
            "tick_size": info.trade_tick_size,
            "contract_size": info.trade_contract_size,
            "volume_min": info.volume_min,
            "volume_max": info.volume_max,
            "volume_step": info.volume_step,
            "spread": info.spread,
            "ask": info.ask,
            "bid": info.bid,
        }

    def get_tick(self, symbol: str) -> Optional[dict]:
        """Get current tick for a symbol."""
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None
        return {
            "ask": tick.ask,
            "bid": tick.bid,
            "last": tick.last,
            "time": tick.time,
        }

    # ─────────────────────────────────────────────
    # Order Operations
    # ─────────────────────────────────────────────

    def _get_filling_mode(self, symbol: str) -> int:
        """
        Determine the correct filling mode for a symbol.
        Checks symbol_info.filling_mode flags to return valid mode:
        IOC > FOK > RETURN
        """
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return mt5.ORDER_FILLING_FOK  # Default assumption

        filling = symbol_info.filling_mode

        # Define constants manually if not in mt5 module
        _SYMBOL_FILLING_FOK = 1
        _SYMBOL_FILLING_IOC = 2
        
        if filling & _SYMBOL_FILLING_IOC:
            return mt5.ORDER_FILLING_IOC
        
        if filling & _SYMBOL_FILLING_FOK:
            return mt5.ORDER_FILLING_FOK
            
        return mt5.ORDER_FILLING_RETURN

    def place_market_order(
        self,
        symbol: str,
        order_type: int,
        volume: float,
        sl: float = 0.0,
        tp: float = 0.0,
        deviation: int = 20,
        magic: int = 888888,
        comment: str = "CopyTrade",
    ) -> OrderResult:
        """
        Place a market order.
        order_type: 0 = BUY, 1 = SELL
        """
        # Ensure symbol is selected and visible
        if not mt5.symbol_select(symbol, True):
            return OrderResult(
                success=False,
                error_message=f"Cannot select symbol {symbol}"
            )
        
        # Get current price
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return OrderResult(
                success=False,
                error_message=f"Cannot get tick for {symbol}"
            )

        # Determine price based on direction
        if order_type == 0:  # BUY
            price = tick.ask
            mt5_type = mt5.ORDER_TYPE_BUY
        else:  # SELL
            price = tick.bid
            mt5_type = mt5.ORDER_TYPE_SELL

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": deviation,
            "magic": magic,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._get_filling_mode(symbol),
        }

        result = mt5.order_send(request)

        if result is None:
            error = mt5.last_error()
            return OrderResult(
                success=False,
                error_message=f"order_send returned None: {error}"
            )

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            # Provide helpful message for common errors
            error_msg = f"Order failed: retcode={result.retcode}, comment={result.comment}"
            if result.retcode == 10027:  # TRADE_RETCODE_CLIENT_DISABLE_AUTOTRADE
                error_msg = f"❌ AutoTrading disabled! Enable it in MT5: Tools → Options → Expert Advisors → Allow automated trading"
            elif result.retcode == 10030:  # TRADE_RETCODE_INVALID_FILLING
                error_msg = f"❌ Unsupported filling mode. Check MT5 account settings."
            
            return OrderResult(
                success=False,
                error_code=result.retcode,
                error_message=error_msg,
                retcode=result.retcode,
            )

        logger.info(
            f"✅ Order OK: {symbol} {'BUY' if order_type == 0 else 'SELL'} "
            f"{volume} lot @ {result.price} | Ticket: {result.order}"
        )

        return OrderResult(
            success=True,
            ticket=result.order,
            volume=volume,
            price=result.price,
            retcode=result.retcode,
        )

    def close_position(self, ticket: int, deviation: int = 20) -> OrderResult:
        """Close a position by ticket."""
        # Find the position
        position = mt5.positions_get(ticket=ticket)
        if not position:
            return OrderResult(
                success=False,
                error_message=f"Position {ticket} not found"
            )

        pos = position[0]

        # Reverse direction to close
        if pos.type == 0:  # BUY → close with SELL
            close_type = mt5.ORDER_TYPE_SELL
            price = mt5.symbol_info_tick(pos.symbol).bid
        else:  # SELL → close with BUY
            close_type = mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info_tick(pos.symbol).ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "type": close_type,
            "position": ticket,
            "price": price,
            "deviation": deviation,
            "magic": pos.magic,
            "comment": "CopyTrade Close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._get_filling_mode(pos.symbol),
        }

        result = mt5.order_send(request)

        if result is None:
            error = mt5.last_error()
            return OrderResult(success=False, error_message=f"Close failed: {error}")

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return OrderResult(
                success=False,
                error_code=result.retcode,
                error_message=f"Close failed: retcode={result.retcode}",
                retcode=result.retcode,
            )

        logger.info(f"✅ Closed position {ticket}: {pos.symbol} {pos.volume} lot")
        return OrderResult(success=True, ticket=ticket, retcode=result.retcode)

    def partial_close(
        self, ticket: int, volume_to_close: float, deviation: int = 20
    ) -> OrderResult:
        """Partially close a position."""
        position = mt5.positions_get(ticket=ticket)
        if not position:
            return OrderResult(
                success=False,
                error_message=f"Position {ticket} not found"
            )

        pos = position[0]

        if volume_to_close >= pos.volume:
            return self.close_position(ticket, deviation)

        # Reverse direction
        if pos.type == 0:
            close_type = mt5.ORDER_TYPE_SELL
            price = mt5.symbol_info_tick(pos.symbol).bid
        else:
            close_type = mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info_tick(pos.symbol).ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": volume_to_close,
            "type": close_type,
            "position": ticket,
            "price": price,
            "deviation": deviation,
            "magic": pos.magic,
            "comment": "CopyTrade Partial",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._get_filling_mode(pos.symbol),
        }

        result = mt5.order_send(request)

        if result is None:
            return OrderResult(success=False, error_message="Partial close failed")

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return OrderResult(
                success=False,
                error_code=result.retcode,
                error_message=f"Partial close failed: retcode={result.retcode}",
                retcode=result.retcode,
            )

        logger.info(
            f"✅ Partial close {ticket}: {volume_to_close} lot "
            f"(remaining: {pos.volume - volume_to_close:.2f})"
        )
        return OrderResult(success=True, ticket=ticket, volume=volume_to_close, retcode=result.retcode)

    def modify_position(
        self, ticket: int, sl: float = None, tp: float = None
    ) -> OrderResult:
        """Modify SL/TP of an existing position."""
        position = mt5.positions_get(ticket=ticket)
        if not position:
            return OrderResult(
                success=False,
                error_message=f"Position {ticket} not found"
            )

        pos = position[0]

        # Use existing values if not provided
        new_sl = sl if sl is not None else pos.sl
        new_tp = tp if tp is not None else pos.tp

        # Skip if nothing changed
        if abs(new_sl - pos.sl) < 1e-6 and abs(new_tp - pos.tp) < 1e-6:
            return OrderResult(success=True, ticket=ticket)

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": pos.symbol,
            "position": ticket,
            "sl": new_sl,
            "tp": new_tp,
        }

        result = mt5.order_send(request)

        if result is None:
            return OrderResult(success=False, error_message="Modify failed")

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return OrderResult(
                success=False,
                error_code=result.retcode,
                error_message=f"Modify failed: retcode={result.retcode}, comment={result.comment}",
                retcode=result.retcode,
            )

        logger.info(f"✅ Modified {ticket}: SL={new_sl}, TP={new_tp}")
        return OrderResult(success=True, ticket=ticket, retcode=result.retcode)
