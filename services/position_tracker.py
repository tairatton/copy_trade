"""
Position Tracker - เก็บ mapping ระหว่าง Master ticket กับ Slave ticket
รองรับ backup/restore จาก JSON file เพื่อกู้คืนหลัง restart
"""

import json
from pathlib import Path
from typing import Dict, Optional
from loguru import logger

from models.trade_models import PositionMapping


class PositionTracker:
    """Track mapping between master and slave positions."""

    def __init__(self, backup_file: str = "position_map.json"):
        self._mappings: Dict[int, PositionMapping] = {}  # key = master_ticket
        self._backup_file = backup_file

    @property
    def count(self) -> int:
        return len(self._mappings)

    # ─────────────────────────────────────────────
    # CRUD Operations
    # ─────────────────────────────────────────────

    def add_mapping(self, mapping: PositionMapping):
        """Add a new position mapping."""
        self._mappings[mapping.master_ticket] = mapping
        self.save_to_file()
        logger.debug(
            f"📌 Mapping added: Master #{mapping.master_ticket} → "
            f"Slave #{mapping.slave_ticket} ({mapping.symbol} {mapping.direction})"
        )

    def remove_mapping(self, master_ticket: int):
        """Remove a mapping by master ticket."""
        if master_ticket in self._mappings:
            mapping = self._mappings.pop(master_ticket)
            self.save_to_file()
            logger.debug(
                f"📌 Mapping removed: Master #{master_ticket} → Slave #{mapping.slave_ticket}"
            )

    def get_mapping(self, master_ticket: int) -> Optional[PositionMapping]:
        """Get mapping by master ticket."""
        return self._mappings.get(master_ticket)

    def get_slave_ticket(self, master_ticket: int) -> Optional[int]:
        """Get slave ticket for a master ticket."""
        mapping = self._mappings.get(master_ticket)
        return mapping.slave_ticket if mapping else None

    def get_all_mappings(self) -> Dict[int, PositionMapping]:
        """Get all mappings."""
        return self._mappings.copy()

    def has_mapping(self, master_ticket: int) -> bool:
        """Check if a mapping exists."""
        return master_ticket in self._mappings

    def update_slave_sl_tp(
        self, master_ticket: int, sl: float = None, tp: float = None
    ):
        """Update slave SL/TP in mapping."""
        if master_ticket in self._mappings:
            mapping = self._mappings[master_ticket]
            if sl is not None:
                mapping.slave_sl = sl
                mapping.master_sl = sl  # Master and slave SL are the same
            if tp is not None:
                mapping.slave_tp = tp
                mapping.master_tp = tp
            self.save_to_file()

    def update_slave_volume(self, master_ticket: int, new_slave_volume: float):
        """Update slave volume (after partial close)."""
        if master_ticket in self._mappings:
            self._mappings[master_ticket].slave_volume = new_slave_volume
            self.save_to_file()

    # ─────────────────────────────────────────────
    # Backup & Restore
    # ─────────────────────────────────────────────

    def save_to_file(self):
        """Save current mappings to JSON file."""
        try:
            data = {
                str(ticket): mapping.to_dict()
                for ticket, mapping in self._mappings.items()
            }
            with open(self._backup_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"❌ Failed to save mappings: {e}")

    def load_from_file(self):
        """Load mappings from JSON backup file."""
        path = Path(self._backup_file)
        if not path.exists():
            logger.info("ℹ️ No backup file found, starting fresh")
            return

        try:
            with open(self._backup_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            self._mappings = {}
            for ticket_str, mapping_data in data.items():
                mapping = PositionMapping.from_dict(mapping_data)
                self._mappings[mapping.master_ticket] = mapping

            logger.info(f"✅ Loaded {len(self._mappings)} mappings from backup")

            # Log each mapping
            for m in self._mappings.values():
                logger.debug(
                    f"   Master #{m.master_ticket} → Slave #{m.slave_ticket} "
                    f"({m.symbol} {m.direction} {m.slave_volume} lot)"
                )

        except Exception as e:
            logger.error(f"❌ Failed to load mappings: {e}")
            self._mappings = {}

    def sync_check(
        self,
        master_tickets: set,
        slave_tickets: set,
    ) -> Dict[str, list]:
        """
        Check for orphaned mappings (positions that exist in mapping but not in MT5).
        Returns dict with 'orphaned_master' and 'orphaned_slave' lists.
        """
        orphaned = {"orphaned_master": [], "orphaned_slave": []}

        for master_ticket, mapping in list(self._mappings.items()):
            if master_ticket not in master_tickets:
                orphaned["orphaned_master"].append(master_ticket)
                logger.warning(
                    f"⚠️ Orphaned mapping: Master #{master_ticket} not found in MT5"
                )
            if mapping.slave_ticket not in slave_tickets:
                orphaned["orphaned_slave"].append(master_ticket)
                logger.warning(
                    f"⚠️ Orphaned mapping: Slave #{mapping.slave_ticket} not found in MT5"
                )

        return orphaned

    def cleanup_orphaned(self, orphaned_master_tickets: list):
        """Remove orphaned mappings."""
        for ticket in orphaned_master_tickets:
            self.remove_mapping(ticket)
        if orphaned_master_tickets:
            logger.info(f"🧹 Cleaned up {len(orphaned_master_tickets)} orphaned mappings")
