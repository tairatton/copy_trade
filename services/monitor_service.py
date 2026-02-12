"""
Monitor Service - ตรวจจับ positions ของ Master Account
เปรียบเทียบ snapshot เก่ากับใหม่ เพื่อตรวจจับ events:
- เปิด position ใหม่
- ปิด position
- แก้ SL/TP
- Partial close (volume ลดลง)
"""

from typing import Dict, List, Optional
from loguru import logger

from models.trade_models import TradePosition, TradeEvent, TradeEventType


class MonitorService:
    """Monitor master positions and detect changes."""

    def __init__(self):
        # Snapshot: {ticket: TradePosition}
        self._previous_snapshot: Dict[int, TradePosition] = {}
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def detect_changes(
        self, current_positions: List[TradePosition]
    ) -> List[TradeEvent]:
        """
        Compare current positions with previous snapshot.
        Returns a list of TradeEvents.
        """
        events: List[TradeEvent] = []

        # Build current snapshot
        current_snapshot: Dict[int, TradePosition] = {
            pos.ticket: pos for pos in current_positions
        }

        # First run → just save snapshot, no events
        if not self._initialized:
            self._previous_snapshot = current_snapshot
            self._initialized = True
            logger.info(
                f"📸 Initial snapshot: {len(current_snapshot)} positions "
                f"[{', '.join(f'{p.symbol} {p.direction} {p.volume}' for p in current_positions)}]"
            )
            return events

        prev = self._previous_snapshot

        # 1. Detect NEW positions (in current but not in previous)
        for ticket, pos in current_snapshot.items():
            if ticket not in prev:
                events.append(TradeEvent(
                    event_type=TradeEventType.NEW_POSITION,
                    master_ticket=ticket,
                    position=pos,
                ))
                logger.info(
                    f"🆕 New position: #{ticket} {pos.symbol} "
                    f"{pos.direction} {pos.volume} lot @ {pos.price_open}"
                )

        # 2. Detect CLOSED positions (in previous but not in current)
        for ticket, pos in prev.items():
            if ticket not in current_snapshot:
                events.append(TradeEvent(
                    event_type=TradeEventType.CLOSED_POSITION,
                    master_ticket=ticket,
                    previous_position=pos,
                ))
                logger.info(
                    f"🔴 Position closed: #{ticket} {pos.symbol} "
                    f"{pos.direction} {pos.volume} lot"
                )

        # 3. Detect MODIFICATIONS on existing positions
        for ticket, current_pos in current_snapshot.items():
            if ticket in prev:
                prev_pos = prev[ticket]

                # SL changed
                if abs(current_pos.sl - prev_pos.sl) > 1e-6:
                    events.append(TradeEvent(
                        event_type=TradeEventType.MODIFIED_SL,
                        master_ticket=ticket,
                        position=current_pos,
                        previous_position=prev_pos,
                    ))
                    logger.info(
                        f"🟡 SL modified: #{ticket} {current_pos.symbol} "
                        f"SL: {prev_pos.sl} → {current_pos.sl}"
                    )

                # TP changed
                if abs(current_pos.tp - prev_pos.tp) > 1e-6:
                    events.append(TradeEvent(
                        event_type=TradeEventType.MODIFIED_TP,
                        master_ticket=ticket,
                        position=current_pos,
                        previous_position=prev_pos,
                    ))
                    logger.info(
                        f"🟡 TP modified: #{ticket} {current_pos.symbol} "
                        f"TP: {prev_pos.tp} → {current_pos.tp}"
                    )

                # Volume decreased → Partial close
                if current_pos.volume < prev_pos.volume - 1e-6:
                    events.append(TradeEvent(
                        event_type=TradeEventType.PARTIAL_CLOSE,
                        master_ticket=ticket,
                        position=current_pos,
                        previous_position=prev_pos,
                    ))
                    closed_vol = prev_pos.volume - current_pos.volume
                    logger.info(
                        f"📉 Partial close: #{ticket} {current_pos.symbol} "
                        f"volume: {prev_pos.volume} → {current_pos.volume} "
                        f"(closed {closed_vol:.2f})"
                    )

        # Update snapshot
        self._previous_snapshot = current_snapshot

        return events

    def reset(self):
        """Reset monitor state."""
        self._previous_snapshot = {}
        self._initialized = False
        logger.info("🔄 Monitor state reset")

    def get_snapshot(self) -> Dict[int, TradePosition]:
        """Get current snapshot (for debugging)."""
        return self._previous_snapshot.copy()
