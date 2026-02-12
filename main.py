"""
MT5 Copy Trade System — Dual Process Architecture
====================================================
Process 1 (Master): connect MT5 master ค้างไว้ → monitor positions → ส่ง events ผ่าน Queue
Process 2 (Slave):  connect MT5 slave ค้างไว้ → รอรับ events จาก Queue → execute orders

ไม่มี downtime! ไม่พลาด event เลยแม้แต่ตัวเดียว!

ข้อกำหนด: ต้องติดตั้ง MT5 terminal 2 ตัว (master + slave) บน VPS
"""

import sys
import time
import signal
import multiprocessing as mp
from pathlib import Path
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent))

from config.settings import load_settings
from utils.logger import setup_logger


def master_process(settings, event_queue: mp.Queue, stop_event: mp.Event):
    """
    Process 1: Monitor master account — ไม่เคย disconnect
    อ่าน positions ทุก poll_interval → ตรวจจับ event → ส่งเข้า Queue
    """
    # ต้อง import ใน process เพราะ MT5 API เป็น per-process
    from services.mt5_service import MT5Service
    from services.monitor_service import MonitorService

    setup_logger(settings.log_level, settings.log_file)

    mt5 = MT5Service()
    monitor = MonitorService()
    poll_sec = settings.poll_interval_ms / 1000.0

    logger.info("🟢 [Master Process] Starting...")

    # Connect master ค้างไว้
    if not mt5.connect(settings.master):
        logger.error("❌ [Master] Cannot connect!")
        stop_event.set()
        return

    balance = mt5.get_balance()
    logger.info(f"✅ [Master] Connected — Balance=${balance:.2f}")

    while not stop_event.is_set():
        try:
            # Reconnect ถ้าหลุด
            if not mt5.connected:
                logger.warning("⚠️ [Master] Disconnected, reconnecting...")
                if not mt5.connect(settings.master):
                    time.sleep(5)
                    continue

            # อ่าน positions
            positions = mt5.get_positions()

            # ตรวจจับ event
            events = monitor.detect_changes(positions)

            # ส่ง events เข้า Queue ให้ Slave process
            for event in events:
                # แปลง event เป็น dict เพื่อส่งผ่าน Queue (pickle-safe)
                event_data = {
                    "event_type": event.event_type.value,
                    "master_ticket": event.master_ticket,
                    "position": _position_to_dict(event.position) if event.position else None,
                    "previous_position": _position_to_dict(event.previous_position) if event.previous_position else None,
                }
                event_queue.put(event_data)
                logger.info(f"📨 [Master] Event sent → Queue: {event.event_type.value} #{event.master_ticket}")

            time.sleep(poll_sec)

        except Exception as e:
            logger.error(f"❌ [Master] Error: {e}")
            time.sleep(5)

    mt5.disconnect()
    logger.info("⏹️ [Master Process] Stopped")


def slave_process(settings, event_queue: mp.Queue, stop_event: mp.Event):
    """
    Process 2: Execute copy trades on slave — ไม่เคย disconnect
    รอรับ events จาก Queue → ส่ง orders ทันที
    """
    from services.mt5_service import MT5Service
    from services.copier_service import CopierService
    from services.position_tracker import PositionTracker
    from models.trade_models import TradeEvent, TradeEventType, TradePosition

    setup_logger(settings.log_level, settings.log_file)

    mt5 = MT5Service()
    tracker = PositionTracker(backup_file="position_map.json")
    copier = CopierService(
        mt5_service=mt5,
        tracker=tracker,
        max_slippage=settings.max_slippage_points,
    )

    tracker.load_from_file()

    logger.info("🔵 [Slave Process] Starting...")

    # Connect slave ค้างไว้
    if not mt5.connect(settings.slave):
        logger.error("❌ [Slave] Cannot connect!")
        stop_event.set()
        return

    balance = mt5.get_balance()
    logger.info(f"✅ [Slave] Connected — Balance=${balance:.2f}")

    while not stop_event.is_set():
        try:
            # Reconnect ถ้าหลุด
            if not mt5.connected:
                logger.warning("⚠️ [Slave] Disconnected, reconnecting...")
                if not mt5.connect(settings.slave):
                    time.sleep(5)
                    continue

            # รอรับ event จาก Queue (timeout 1 วินาที)
            try:
                event_data = event_queue.get(timeout=1.0)
            except Exception:
                # Queue ว่าง → วนรอต่อ
                continue

            # แปลง dict กลับเป็น TradeEvent
            event = _dict_to_event(event_data)
            if event is None:
                continue

            logger.info(f"📥 [Slave] Event received: {event.event_type.value} #{event.master_ticket}")

            # Execute!
            copier.process_event(event)

        except Exception as e:
            logger.error(f"❌ [Slave] Error: {e}")
            time.sleep(1)

    # Shutdown
    tracker.save_to_file()
    mt5.disconnect()
    logger.info(f"💾 [Slave] Saved {tracker.count} mappings")
    logger.info("⏹️ [Slave Process] Stopped")


# ─────────────────────────────────────────────
# Helpers: แปลง data ข้าม process (pickle-safe)
# ─────────────────────────────────────────────

def _position_to_dict(pos) -> dict:
    """Convert TradePosition to dict for queue transfer."""
    return {
        "ticket": pos.ticket,
        "symbol": pos.symbol,
        "type": pos.type,
        "volume": pos.volume,
        "price_open": pos.price_open,
        "price_current": pos.price_current,
        "sl": pos.sl,
        "tp": pos.tp,
        "profit": pos.profit,
        "swap": pos.swap,
        "time": pos.time.isoformat() if pos.time else "",
        "time_update": pos.time_update.isoformat() if pos.time_update else "",
        "magic": pos.magic,
        "comment": pos.comment,
    }


def _dict_to_event(data: dict):
    """Convert dict back to TradeEvent."""
    from models.trade_models import TradeEvent, TradeEventType, TradePosition
    from datetime import datetime

    try:
        event_type = TradeEventType(data["event_type"])

        position = None
        if data.get("position"):
            p = data["position"]
            position = TradePosition(
                ticket=p["ticket"],
                symbol=p["symbol"],
                type=p["type"],
                volume=p["volume"],
                price_open=p["price_open"],
                price_current=p["price_current"],
                sl=p["sl"],
                tp=p["tp"],
                profit=p["profit"],
                swap=p["swap"],
                time=datetime.fromisoformat(p["time"]) if p["time"] else datetime.now(),
                time_update=datetime.fromisoformat(p["time_update"]) if p["time_update"] else datetime.now(),
                magic=p["magic"],
                comment=p["comment"],
            )

        previous_position = None
        if data.get("previous_position"):
            p = data["previous_position"]
            previous_position = TradePosition(
                ticket=p["ticket"],
                symbol=p["symbol"],
                type=p["type"],
                volume=p["volume"],
                price_open=p["price_open"],
                price_current=p["price_current"],
                sl=p["sl"],
                tp=p["tp"],
                profit=p["profit"],
                swap=p["swap"],
                time=datetime.fromisoformat(p["time"]) if p["time"] else datetime.now(),
                time_update=datetime.fromisoformat(p["time_update"]) if p["time_update"] else datetime.now(),
                magic=p["magic"],
                comment=p["comment"],
            )

        return TradeEvent(
            event_type=event_type,
            master_ticket=data["master_ticket"],
            position=position,
            previous_position=previous_position,
        )
    except Exception as e:
        logger.error(f"❌ Failed to parse event: {e}")
        return None


# ─────────────────────────────────────────────
# Main Entry Point
# ─────────────────────────────────────────────

def main():
    logger.info("=" * 50)
    logger.info("🚀 MT5 Copy Trade — Dual Process Mode")
    logger.info("=" * 50)

    settings = load_settings()
    setup_logger(settings.log_level, settings.log_file)

    # Shared objects
    event_queue = mp.Queue()
    stop_event = mp.Event()

    # Start 2 processes
    p_master = mp.Process(
        target=master_process,
        args=(settings, event_queue, stop_event),
        name="CopyTrade-Master",
    )
    p_slave = mp.Process(
        target=slave_process,
        args=(settings, event_queue, stop_event),
        name="CopyTrade-Slave",
    )

    p_master.start()
    p_slave.start()

    logger.info("✅ Both processes started")

    # Handle Ctrl+C
    def signal_handler(sig, frame):
        logger.info("⏹️ Stopping...")
        stop_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Wait for processes
    try:
        while p_master.is_alive() and p_slave.is_alive():
            time.sleep(1)
            if stop_event.is_set():
                break
    except KeyboardInterrupt:
        stop_event.set()

    # Cleanup
    logger.info("⏹️ Waiting for processes to finish...")
    stop_event.set()
    p_master.join(timeout=10)
    p_slave.join(timeout=10)

    if p_master.is_alive():
        p_master.terminate()
    if p_slave.is_alive():
        p_slave.terminate()

    logger.info("✅ Shutdown complete")


if __name__ == "__main__":
    main()
