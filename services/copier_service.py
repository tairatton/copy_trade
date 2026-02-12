"""
Copier Service - Copy ทุกอย่างจาก Master ไป Slave 100%
Lot เท่า Master, SL/TP เท่า Master, ปิดเหมือน Master
"""

from datetime import datetime
from loguru import logger

from models.trade_models import (
    TradeEvent,
    TradeEventType,
    PositionMapping,
)
from services.mt5_service import MT5Service
from services.position_tracker import PositionTracker


class CopierService:
    """Copy trades from master to slave 1:1."""

    def __init__(
        self,
        mt5_service: MT5Service,
        tracker: PositionTracker,
        max_slippage: int = 20,
    ):
        self.mt5 = mt5_service
        self.tracker = tracker
        self.max_slippage = max_slippage

    def process_event(self, event: TradeEvent):
        """Process a single trade event."""
        try:
            if event.event_type == TradeEventType.NEW_POSITION:
                self._handle_new(event)
            elif event.event_type == TradeEventType.CLOSED_POSITION:
                self._handle_close(event)
            elif event.event_type == TradeEventType.MODIFIED_SL:
                self._handle_modify_sl(event)
            elif event.event_type == TradeEventType.MODIFIED_TP:
                self._handle_modify_tp(event)
            elif event.event_type == TradeEventType.PARTIAL_CLOSE:
                self._handle_partial_close(event)
        except Exception as e:
            logger.error(f"❌ Error processing {event.event_type.value} #{event.master_ticket}: {e}")

    # ─── เปิด Position ใหม่ (lot เท่า master) ───

    def _handle_new(self, event: TradeEvent):
        pos = event.position
        if not pos:
            return

        # ป้องกัน duplicate
        if self.tracker.has_mapping(pos.ticket):
            logger.warning(f"⚠️ #{pos.ticket} already mapped, skip")
            return

        # เปิด order เท่า master เลย
        result = self.mt5.place_market_order(
            symbol=pos.symbol,
            order_type=pos.type,       # BUY/SELL เหมือน master
            volume=pos.volume,         # lot เท่า master
            sl=pos.sl,                 # SL เท่า master
            tp=pos.tp,                 # TP เท่า master
            deviation=self.max_slippage,
            comment=f"CT#{pos.ticket}",
        )

        if not result.success:
            logger.error(f"❌ Copy failed #{pos.ticket}: {result.error_message}")
            return

        # บันทึก mapping
        self.tracker.add_mapping(PositionMapping(
            master_ticket=pos.ticket,
            slave_ticket=result.ticket,
            symbol=pos.symbol,
            direction=pos.direction,
            master_volume=pos.volume,
            slave_volume=pos.volume,    # เท่ากัน!
            master_open_price=pos.price_open,
            slave_open_price=result.price or 0.0,
            master_sl=pos.sl,
            master_tp=pos.tp,
            slave_sl=pos.sl,
            slave_tp=pos.tp,
            opened_at=datetime.now().isoformat(),
        ))

        logger.info(
            f"✅ Copied: {pos.symbol} {pos.direction} {pos.volume} lot | "
            f"Master #{pos.ticket} → Slave #{result.ticket}"
        )

    # ─── ปิด Position ───

    def _handle_close(self, event: TradeEvent):
        mapping = self.tracker.get_mapping(event.master_ticket)
        if not mapping:
            logger.warning(f"⚠️ No mapping for #{event.master_ticket}")
            return

        result = self.mt5.close_position(
            ticket=mapping.slave_ticket,
            deviation=self.max_slippage,
        )

        if not result.success:
            logger.error(f"❌ Close failed Slave #{mapping.slave_ticket}: {result.error_message}")
            return

        self.tracker.remove_mapping(event.master_ticket)
        logger.info(f"✅ Closed: {mapping.symbol} | Slave #{mapping.slave_ticket}")

    # ─── แก้ SL ───

    def _handle_modify_sl(self, event: TradeEvent):
        mapping = self.tracker.get_mapping(event.master_ticket)
        if not mapping:
            return

        result = self.mt5.modify_position(ticket=mapping.slave_ticket, sl=event.position.sl)

        if result.success:
            self.tracker.update_slave_sl_tp(event.master_ticket, sl=event.position.sl)
            logger.info(f"✅ SL updated: {mapping.symbol} → {event.position.sl}")
        else:
            logger.error(f"❌ SL modify failed #{mapping.slave_ticket}: {result.error_message}")

    # ─── แก้ TP ───

    def _handle_modify_tp(self, event: TradeEvent):
        mapping = self.tracker.get_mapping(event.master_ticket)
        if not mapping:
            return

        result = self.mt5.modify_position(ticket=mapping.slave_ticket, tp=event.position.tp)

        if result.success:
            self.tracker.update_slave_sl_tp(event.master_ticket, tp=event.position.tp)
            logger.info(f"✅ TP updated: {mapping.symbol} → {event.position.tp}")
        else:
            logger.error(f"❌ TP modify failed #{mapping.slave_ticket}: {result.error_message}")

    # ─── Partial Close (ปิดบางส่วนตามสัดส่วน) ───

    def _handle_partial_close(self, event: TradeEvent):
        mapping = self.tracker.get_mapping(event.master_ticket)
        if not mapping:
            return

        pos = event.position
        prev = event.previous_position

        # คำนวณ volume ที่ต้องปิด (เท่า master)
        volume_to_close = prev.volume - pos.volume

        # Round to volume step
        symbol_info = self.mt5.get_symbol_info(pos.symbol)
        if symbol_info:
            import math
            step = symbol_info.get("volume_step", 0.01)
            v_min = symbol_info.get("volume_min", 0.01)
            volume_to_close = math.floor(volume_to_close / step) * step
            volume_to_close = max(volume_to_close, v_min)
            volume_to_close = round(volume_to_close, 8)

        result = self.mt5.partial_close(
            ticket=mapping.slave_ticket,
            volume_to_close=volume_to_close,
            deviation=self.max_slippage,
        )

        if result.success:
            new_vol = mapping.slave_volume - volume_to_close
            self.tracker.update_slave_volume(event.master_ticket, new_vol)
            logger.info(
                f"✅ Partial close: {mapping.symbol} closed {volume_to_close} lot, "
                f"remaining {new_vol:.2f} lot"
            )
        else:
            logger.error(f"❌ Partial close failed #{mapping.slave_ticket}: {result.error_message}")
