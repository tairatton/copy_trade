# 📋 MT5 Copy Trade System - Implementation Plan

## 🎯 Overview

โปรแกรม Copy Trade สำหรับ MetaTrader 5 (MT5) ที่ทำงานบน VPS
- **วัตถุประสงค์**: Copy ออเดอร์จาก Master Account ไปยัง Slave Account(s) แบบ 1:1
- **ภาษา**: Python 3.10+
- **Platform**: MetaTrader 5
- **Deployment**: Windows VPS

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      VPS Server                         │
│                                                         │
│  ┌──────────────┐    ┌──────────────┐                   │
│  │  MT5 Terminal │    │  MT5 Terminal │                   │
│  │  (Master)     │    │  (Slave)      │                   │
│  │  Login: xxx   │    │  Login: yyy   │                   │
│  └──────┬───────┘    └──────▲───────┘                   │
│         │                    │                           │
│         ▼                    │                           │
│  ┌──────────────────────────────────────┐               │
│  │         Python Copy Trade App         │               │
│  │                                       │               │
│  │  ┌─────────┐  ┌──────────┐           │               │
│  │  │ Monitor  │→│  Copier   │           │               │
│  │  │ (Master) │  │  (Slave)  │           │               │
│  │  └─────────┘  └──────────┘           │               │
│  │       │              │                │               │
│  │       ▼              ▼                │               │
│  │  ┌──────────────────────┐            │               │
│  │  │   Position Tracker   │            │               │
│  │  │   (SQLite / Memory)  │            │               │
│  │  └──────────────────────┘            │               │
│  │       │                               │               │
│  │       ▼                               │               │
│  │  ┌──────────────────────┐            │               │
│  │  │   Notification       │            │               │
│  │  │   (Telegram/Line)    │            │               │
│  │  └──────────────────────┘            │               │
│  └──────────────────────────────────────┘               │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 📁 Project Structure

```
copy/
├── main.py                    # Entry point - เริ่มต้นโปรแกรม
├── config/
│   ├── __init__.py
│   └── settings.py            # Configuration settings (จาก .env files)
├── services/
│   ├── __init__.py
│   ├── mt5_service.py         # MT5 connection & operations
│   ├── monitor_service.py     # Monitor master positions
│   ├── copier_service.py      # Execute copy trades on slave
│   ├── lot_calculator.py      # คำนวณ lot size (RISK_PERCENT/RATIO/...)
│   ├── position_tracker.py    # Track position mapping master↔slave
│   └── notification_service.py # Telegram/Line notifications
├── models/
│   ├── __init__.py
│   └── trade_models.py        # Data models (Position, TradeAction)
├── utils/
│   ├── __init__.py
│   ├── logger.py              # Logging configuration
│   └── helpers.py             # Utility functions
├── .env                       # Global settings (copy mode, risk, Telegram, logging)
├── .env.master                # Master MT5 account credentials
├── .env.slave                 # Slave MT5 account credentials
├── requirements.txt           # Python dependencies
├── README.md                  # Documentation
├── position_map.json          # Position mapping backup (auto-generated)
└── logs/                      # Log files directory
    └── .gitkeep
```

---

## 📦 Dependencies (requirements.txt)

```
MetaTrader5>=5.0.45
python-dotenv>=1.0.0
requests>=2.31.0          # สำหรับ Telegram API
schedule>=1.2.0            # Job scheduling (optional)
loguru>=0.7.0              # Advanced logging
```

---

## ⚙️ Configuration Design (แยก 3 ไฟล์)

แยก config เป็น 3 ไฟล์เพื่อความปลอดภัยและจัดการง่าย:

### `.env.master` - Master Account Credentials
```env
# ===================================
# Master Account Configuration
# ===================================
MT5_LOGIN=12345678
MT5_PASSWORD=your_master_password
MT5_SERVER=YourBroker-Live
MT5_PATH=C:\Program Files\MetaTrader 5 Master\terminal64.exe
ACCOUNT_LABEL=Master
```

### `.env.slave` - Slave Account Credentials
```env
# ===================================
# Slave Account Configuration
# ===================================
MT5_LOGIN=87654321
MT5_PASSWORD=your_slave_password
MT5_SERVER=YourBroker-Live
MT5_PATH=C:\Program Files\MetaTrader 5 Slave\terminal64.exe
ACCOUNT_LABEL=Slave
```

### `.env` - Global Settings
```env
# ===================================
# Copy Trade - Global Settings
# ===================================
COPY_MODE=RISK_PERCENT               # RISK_PERCENT | SAME_LOT | FIXED_LOT | RATIO

# RISK_PERCENT Settings
DEFAULT_SL_POINTS=500               # SL สำรอง (points) ถ้า Master ไม่ตั้ง SL
MAX_RISK_PERCENT=5.0                 # จำกัด risk สูงสุดต่อออเดอร์ (%)
MIN_LOT=0.01
MAX_LOT=10.0

# Other Copy Mode Settings
FIXED_LOT_SIZE=0.01                  # ใช้ถ้า COPY_MODE=FIXED_LOT
LOT_RATIO=1.0                        # ใช้ถ้า COPY_MODE=RATIO

SYMBOLS_WHITELIST=
SYMBOLS_BLACKLIST=
MAX_SLAVE_POSITIONS=10
MAX_SLIPPAGE_POINTS=20
POLL_INTERVAL_MS=500
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
TELEGRAM_ENABLED=true
LOG_LEVEL=INFO
LOG_FILE=logs/copytrade.log
```

---

## 🧩 Module Design (แต่ละไฟล์)

### 1. `config/settings.py` - Configuration Manager

```python
# หน้าที่: โหลด config จาก .env, .env.master, .env.slave แล้ว validate
#
# Classes:
#   - MT5Account (dataclass)
#       - login, password, server, mt5_path, label
#
#   - Settings (dataclass)
#       - master: MT5Account      ← จาก .env.master
#       - slave: MT5Account       ← จาก .env.slave
#       - copy_mode, lot_size, lot_ratio
#       - symbols_whitelist, symbols_blacklist
#       - poll_interval_ms
#       - telegram_bot_token, telegram_chat_id
#       - telegram_enabled
#       - log_level, log_file
#
# Functions:
#   - load_account(env_file) -> MT5Account     # โหลดจาก .env.master / .env.slave
#   - load_settings() -> Settings              # โหลดทั้ง 3 ไฟล์ รวมกัน
#   - validate_settings(settings) -> bool
```

### 2. `services/mt5_service.py` - MT5 Connection Service

```python
# หน้าที่: จัดการการเชื่อมต่อกับ MT5 Terminal
#
# ⚠️ ข้อจำกัดสำคัญ: 
#   Python MT5 library สามารถเชื่อมต่อได้ทีละ 1 terminal เท่านั้น!
#   ดังนั้นต้องใช้วิธี "switch connection" ระหว่าง master กับ slave
#   หรือใช้ multiprocessing (แนะนำ)
#
# Approach A: Single Process - Switch Connection
#   - connect_master() -> bool
#   - connect_slave() -> bool
#   - disconnect() -> None
#   - get_positions(account_type) -> List[Position]
#   - send_order(order_request) -> OrderResult
#
# Approach B: Multi-Process (แนะนำ ✅)
#   - ใช้ 2 processes แยกกัน
#   - Process 1: Monitor Master (อ่าน positions)
#   - Process 2: Execute on Slave (ส่ง orders)
#   - สื่อสารผ่าน multiprocessing.Queue
#
# Functions:
#   - initialize_mt5(path, login, password, server) -> bool
#   - get_open_positions() -> List[TradePosition]
#   - place_market_order(symbol, order_type, volume, sl, tp, comment) -> OrderResult
#   - close_position(ticket) -> OrderResult  
#   - modify_position(ticket, sl, tp) -> OrderResult
#   - get_symbol_info(symbol) -> SymbolInfo
```

### 3. `services/monitor_service.py` - Master Monitor

```python
# หน้าที่: ตรวจสอบ positions ของ Master Account อย่างต่อเนื่อง
#
# Logic Flow:
#   1. Poll master positions ทุก X ms
#   2. เปรียบเทียบกับ snapshot ก่อนหน้า
#   3. ตรวจจับ events:
#      - NEW_POSITION: มี position ใหม่ที่ไม่เคยเห็น
#      - CLOSED_POSITION: position เก่าหายไป
#      - MODIFIED_POSITION: SL/TP เปลี่ยน
#      - PARTIAL_CLOSE: volume ลดลง
#   4. ส่ง event ไปยัง Copier Service
#
# Classes:
#   - MasterMonitor
#       - __init__(mt5_service, queue)
#       - start_monitoring() -> None (loop)
#       - _detect_changes(old_positions, new_positions) -> List[TradeEvent]
#       - _snapshot_positions() -> Dict[int, Position]
```

### 4. `services/copier_service.py` - Trade Copier

```python
# หน้าที่: รับ events จาก Monitor แล้วดำเนินการใน Slave Account
#
# Logic Flow:
#   สำหรับแต่ละ TradeEvent:
#
#   NEW_POSITION:
#     1. ตรวจสอบ symbol whitelist/blacklist
#     2. คำนวณ lot size ตาม copy_mode (ใช้ LotCalculator)
#     3. ส่ง market order ไปยัง slave
#     4. บันทึก mapping: master_ticket -> slave_ticket
#     5. Copy SL/TP ตาม master (ถ้ามี)
#
#   U0e41ละอื่นๆ เหมือนเดิม...
#
# Classes:
#   - TradeCopier
#       - __init__(mt5_service, tracker, settings, notifier, lot_calculator)
#       - process_event(event: TradeEvent) -> None
#       - _copy_new_position(event) -> None
#       - _copy_close_position(event) -> None
#       - _copy_modify_position(event) -> None
#       - _copy_partial_close(event) -> None
```

### 4.1 `services/lot_calculator.py` - Lot Size Calculator (ใหม่!)

```python
# หน้าที่: คำนวณ lot size ตามโหมดที่เลือก
#
# ===== RISK_PERCENT Mode (แนะนำ ✅) =====
#
# แนวคิด: คำนวณ % ความเสี่ยงของ Master แล้วใช้ % เดียวกันกับ Slave
#
# สูตรคำนวณ:
# ──────────────────────────────────────────────────────
#
# Step 1: คำนวณ Risk $ ของ Master
#   risk_amount_master = master_lot * sl_points * tick_value / tick_size
#
# Step 2: คำนวณ Risk % ของ Master
#   risk_percent = (risk_amount_master / master_balance) * 100
#
# Step 3: ใช้ Risk % เดียวกันคำนวณ Lot ของ Slave
#   risk_amount_slave = slave_balance * risk_percent / 100
#   slave_lot = risk_amount_slave / (sl_points * tick_value / tick_size)
#
# Step 4: ปรับให้อยู่ในขอบเขต
#   slave_lot = max(min_lot, min(slave_lot, max_lot))
#   slave_lot = round_to_lot_step(slave_lot, symbol_info.volume_step)
#
# ──────────────────────────────────────────────────────
#
# ตัวอย่าง:
#   Master: balance=$10,000 | BUY XAUUSD 0.5 lot | SL=100 points
#     → tick_value=1.0, tick_size=0.01
#     → risk$ = 0.5 * 100 * 1.0 / 0.01 = $5,000
#     → risk% = 5000 / 10000 * 100 = 50%   ← แต่ถ้าเกิน MAX_RISK_PERCENT จะ cap ไว้
#
#   Slave: balance=$5,000 | ใช้ risk%=50% (หรือ cap ที่ 5%)
#     → risk$ = 5000 * 5% / 100 = $250
#     → slave_lot = 250 / (100 * 1.0 / 0.01) = 0.025 → ปัดเป็น 0.03
#
# Classes:
#   - LotCalculator
#       - __init__(settings)
#       - calculate(copy_mode, master_position, master_balance,
#                  slave_balance, symbol_info) -> float
#       - _calculate_risk_percent(master_position, master_balance,
#                                 slave_balance, symbol_info) -> float
#       - _calculate_same_lot(master_volume) -> float
#       - _calculate_fixed_lot() -> float
#       - _calculate_ratio(master_volume) -> float
#       - _round_lot(lot, volume_step, volume_min, volume_max) -> float
```

### 5. `services/position_tracker.py` - Position Mapping Tracker

```python
# หน้าที่: เก็บ mapping ระหว่าง Master ticket กับ Slave ticket
#
# Storage: In-memory dict + JSON file backup
#
# Data Structure:
#   {
#     master_ticket: {
#       "slave_ticket": int,
#       "symbol": str,
#       "master_volume": float,
#       "slave_volume": float,
#       "direction": str,  # "BUY" | "SELL"
#       "opened_at": datetime,
#       "master_sl": float,
#       "master_tp": float,
#     }
#   }
#
# Classes:
#   - PositionTracker
#       - __init__(backup_file="position_map.json")
#       - add_mapping(master_ticket, slave_ticket, details) -> None
#       - remove_mapping(master_ticket) -> None
#       - get_slave_ticket(master_ticket) -> Optional[int]
#       - get_all_mappings() -> Dict
#       - save_to_file() -> None   # backup
#       - load_from_file() -> None  # restore on startup
#       - sync_with_mt5(master_positions, slave_positions) -> None  # reconciliation
```

### 6. `services/notification_service.py` - Notifications

```python
# หน้าที่: ส่งการแจ้งเตือนผ่าน Telegram
#
# Notifications:
#   - 🟢 เปิด Position ใหม่สำเร็จ
#   - 🔴 ปิด Position สำเร็จ
#   - 🟡 แก้ไข SL/TP
#   - ❌ Error / Copy ล้มเหลว
#   - ℹ️ System startup/shutdown
#   - 📊 สรุปรายวัน (optional)
#
# Classes:
#   - TelegramNotifier
#       - __init__(bot_token, chat_id)
#       - send_message(text) -> bool
#       - notify_new_trade(symbol, direction, volume, price) -> None
#       - notify_close_trade(symbol, direction, profit) -> None
#       - notify_modify_trade(symbol, new_sl, new_tp) -> None
#       - notify_error(error_message) -> None
#       - notify_system_status(status) -> None
```

### 7. `models/trade_models.py` - Data Models

```python
# Data Classes:
#
# @dataclass
# class TradePosition:
#     ticket: int
#     symbol: str
#     type: int          # 0=BUY, 1=SELL
#     volume: float
#     price_open: float
#     sl: float
#     tp: float
#     profit: float
#     time: datetime
#     comment: str
#
# class TradeEventType(Enum):
#     NEW_POSITION = "NEW"
#     CLOSED_POSITION = "CLOSED"
#     MODIFIED_POSITION = "MODIFIED"
#     PARTIAL_CLOSE = "PARTIAL_CLOSE"
#
# @dataclass
# class TradeEvent:
#     event_type: TradeEventType
#     master_ticket: int
#     position: Optional[TradePosition]
#     previous_position: Optional[TradePosition]  # สำหรับ detect changes
#     timestamp: datetime
#
# @dataclass
# class OrderResult:
#     success: bool
#     ticket: Optional[int]
#     error_code: Optional[int]
#     error_message: Optional[str]
```

### 8. `main.py` - Entry Point

```python
# หน้าที่: Entry point ของโปรแกรม
#
# Flow:
#   1. Load settings from .env
#   2. Initialize logging
#   3. Send startup notification
#   4. Restore position mappings from backup
#   5. Start monitoring loop:
#      
#      Option A: Single Process (ง่ายกว่า)
#      ─────────────────────────────────
#      while True:
#        a. connect_master()
#        b. snapshot = get_positions()
#        c. events = detect_changes(prev_snapshot, snapshot)
#        d. disconnect()
#        e. connect_slave()
#        f. for event in events: process_event(event)
#        g. disconnect()
#        h. sleep(poll_interval)
#
#      Option B: Multi-Process (เร็วกว่า ✅ แนะนำ)
#      ─────────────────────────────────────────
#      Process 1 (Master Monitor):
#        - connect ไปยัง Master MT5
#        - วนลูป poll positions
#        - ส่ง events เข้า Queue
#
#      Process 2 (Slave Copier):
#        - connect ไปยัง Slave MT5
#        - รอ events จาก Queue
#        - execute orders
#
#   6. Handle graceful shutdown (Ctrl+C)
#   7. Save position mappings to backup
#   8. Send shutdown notification
```

---

## 🔄 Core Logic Flow (Copy 1:1)

```
Master Account                    Python App                      Slave Account
─────────────                    ──────────                      ─────────────
เปิด BUY XAUUSD 0.1             
  │                               
  ├──→ Monitor ตรวจพบ ────────→  Copier สั่ง BUY                
  │    position ใหม่              XAUUSD 0.1 ─────────────────→  เปิด BUY XAUUSD 0.1
  │                               บันทึก mapping                 
  │                               master#123 → slave#456         
  │                                                              
เซต SL = 2000                    
  │                               
  ├──→ Monitor ตรวจพบ ────────→  Copier modify SL               
  │    SL เปลี่ยน                  slave#456 SL=2000 ──────────→  แก้ SL = 2000
  │                                                              
เซต TP = 2100                    
  │                               
  ├──→ Monitor ตรวจพบ ────────→  Copier modify TP               
  │    TP เปลี่ยน                  slave#456 TP=2100 ──────────→  แก้ TP = 2100
  │                                                              
ปิด Position                     
  │                               
  └──→ Monitor ตรวจพบ ────────→  Copier ปิด position            
       position หายไป             slave#456 ────────────────────→  ปิด position
                                  ลบ mapping                     
```

---

## ⚠️ Critical Considerations

### 1. MT5 Python Library Limitation
```
❗ MetaTrader5 Python library สามารถ connect กับ MT5 terminal 
   ได้ทีละ 1 ตัวเท่านั้นใน 1 process!

✅ วิธีแก้ (เลือก 1):
   A) Single Process: สลับ connect ระหว่าง master/slave
      - ง่ายกว่า
      - Delay สูงกว่า (~1-2 วินาที)
   
   B) Multi-Process: แยก 2 processes
      - เร็วกว่า (parallel connection)
      - ซับซ้อนกว่า
      - ต้องติดตั้ง MT5 terminal 2 ตัว

   C) ใช้ MT5 portable mode
      - ติดตั้ง MT5 1 ตัว แต่รันในโหมด portable 2 instances
      - terminal64.exe /portable /path1 , terminal64.exe /portable /path2
```

### 2. VPS Setup Requirements
```
- Windows VPS (MT5 ทำงานบน Windows เท่านั้น)
- RAM: ≥ 2GB (MT5 x2 + Python)
- MT5 Terminal ต้องเปิดค้างไว้ตลอด
- Python 3.10+
- ติดตั้ง Visual C++ Redistributable
```

### 3. Error Handling Scenarios
```
- MT5 disconnect → auto-reconnect + notification
- Order ส่งไม่ผ่าน → retry + notification
- Price slippage → check max slippage before sending
- Symbol ไม่มีใน Slave → skip + notification
- VPS restart → auto-start + restore mappings
```

### 4. Timing Considerations
```
- Poll interval 500ms = ตรวจสอบ 2 ครั้งต่อวินาที
- Copy delay ≈ 500ms - 2000ms (ขึ้นอยู่กับ approach)
- ไม่เหมาะกับ scalping ที่ต้องการ < 100ms
- เหมาะกับ swing trade, day trade, หรือ long-term
```

---

## 📋 Development Phases

### Phase 1: Foundation (เริ่มก่อน ✅)
- [x] วางแผน architecture
- [ ] สร้าง project structure
- [ ] เขียน config/settings.py
- [ ] เขียน models/trade_models.py
- [ ] เขียน utils/logger.py
- [ ] เขียน .env.example

### Phase 2: MT5 Integration
- [ ] เขียน mt5_service.py (connect, get positions, send orders)
- [ ] ทดสอบ connect กับ MT5 demo account
- [ ] ทดสอบ อ่าน positions
- [ ] ทดสอบ ส่ง market order

### Phase 3: Core Copy Logic
- [ ] เขียน monitor_service.py (detect changes)
- [ ] เขียน copier_service.py (execute copy)
- [ ] เขียน position_tracker.py (mapping)
- [ ] ทดสอบ copy open/close/modify

### Phase 4: Notifications & Error Handling
- [ ] เขียน notification_service.py (Telegram)
- [ ] เพิ่ม error handling ทุก module
- [ ] เพิ่ม auto-reconnect

### Phase 5: Main Entry & Deployment
- [ ] เขียน main.py (entry point + main loop)
- [ ] ทดสอบ end-to-end บน demo account
- [ ] เพิ่ม Windows Task Scheduler สำหรับ auto-start
- [ ] Deploy บน VPS

### Phase 6: Enhancements (Optional)
- [ ] Web dashboard (Flask) สำหรับดูสถานะ
- [ ] รองรับ multiple slave accounts
- [ ] สรุปกำไร/ขาดทุนรายวัน
- [ ] Risk management (max drawdown stop)

---

## 🚀 Quick Start (After Development)

```bash
# 1. Clone/copy project to VPS
# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy .env.example to .env and fill in settings
copy .env.example .env

# 4. Edit .env with your MT5 credentials
notepad .env

# 5. Run the copy trader
python main.py
```

---

## 📊 เปรียบเทียบ Approach

| Feature | Single Process (A) | Multi-Process (B) |
|---------|-------------------|-------------------|
| ความง่าย | ⭐⭐⭐⭐⭐ ง่ายมาก | ⭐⭐⭐ ปานกลาง |
| ความเร็ว | ⭐⭐⭐ ~1-2s delay | ⭐⭐⭐⭐⭐ ~0.5s delay |
| MT5 Terminals | 1 ตัว (สลับ) | 2 ตัว (แยก) |
| Reliability | ⭐⭐⭐ ดี | ⭐⭐⭐⭐ ดีมาก |
| Resource Usage | ⭐⭐⭐⭐⭐ น้อย | ⭐⭐⭐ มากกว่า |

**🏆 แนะนำ: เริ่มด้วย Single Process (A) ก่อน แล้วค่อยอัพเกรดเป็น Multi-Process (B) ถ้าต้องการความเร็ว**

---

## 🔐 Security Notes

- ❌ ห้าม commit ไฟล์ `.env`, `.env.master`, `.env.slave` ขึ้น Git
- ✅ แยก credentials ออกเป็นไฟล์ `.env.master` / `.env.slave` → จัดการง่าย ปลอดภัย
- ✅ เก็บ log files ไว้ที่ VPS เท่านั้น
- ✅ ใช้ Telegram bot แบบ private chat เท่านั้น
- ✅ เปลี่ยน password ง่าย แก้แค่ไฟล์เดียวต่อ account
