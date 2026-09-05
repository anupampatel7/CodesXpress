# 🎁 Telegram Coupon Referral & Rewards Bot

A production-ready, modular, and secure Telegram bot built with **Python 3.12+**, **aiogram 3.x**, and **SQLAlchemy 2.0 Async ORM**.

Users earn points by referring friends through unique deep-links, verify mandatory Telegram channel memberships, and redeem discount vouchers/promo codes. Administrators enjoy a full-featured control panel to manage coupons, restock inventory, import bulk codes, adjust points, manage channels, and trigger database backups.

---

## 🌟 Key Features

- **aiogram 3.x Architecture**: Modular Routers, Custom Middlewares, Typed CallbackData factories, and FSM dialogue wizards.
- **Async SQLAlchemy 2.0 ORM**: Clean asynchronous queries with `aiosqlite` for local dev and full plug-and-play compatibility with PostgreSQL (`asyncpg`).
- **Anti-Fraud Referral Engine**:
  - Deep-link referral capture: `https://t.me/BOT_USERNAME?start=ref_CODE`.
  - Self-referral prevention (cannot refer own account).
  - Existing user protection (only brand-new first-time users generate referral links).
  - Atomic point distribution (+1 point) only after mandatory channel verification.
  - Strictly single-level referral (no multi-level marketing / MLM).
- **Dual-Mode Coupon Inventory**:
  - **Mode A (Quantity-based)**: Single reusable coupon code with numerical stock count.
  - **Mode B (Unique Individual Codes)**: Pool of distinct single-use codes imported in bulk; codes transition atomically from `AVAILABLE` to `USED`.
- **Atomic Redemptions**: Points deduction, stock decrement, unique code assignment, redemption receipt generation, and points ledger logging occur in a single database transaction.
- **Dynamic Required Channels**: Admin can add, remove, and toggle mandatory channels without modifying code. Bot verifies membership via `get_chat_member`.
- **Comprehensive Admin Suite (`/admin`)**:
  - Aggregate statistics dashboard.
  - Multi-step Add Coupon wizard.
  - Dedicated Restock & Bulk Add Codes tools.
  - User Inspector (Search by ID/Code, Add/Remove Points with Audit Log, Ban/Unban).
  - Channel Manager.
  - Timestamped SQLite backup generation (`/backup`).
- **Clean Hinglish / English UI**: Professional emojis and intuitive inline navigation.

---

## 📂 Project Structure

```
telegram_coupon_bot/
│
├── bot.py                     # Bot entrypoint, dispatcher & router setup, lifecycle hooks
├── config.py                  # Pydantic Settings configuration & validation
├── database.py                # Async engine, sessionmaker, pragmas, and schema initializer
├── requirements.txt           # Production dependencies
├── .env.example               # Template environment variables
├── .gitignore                 # Excludes secrets, databases, caches, and backups
├── Dockerfile                 # Multi-stage production container
├── docker-compose.yml         # Container orchestration (SQLite & PostgreSQL profiles)
├── README.md                  # Complete documentation and deployment guide
│
├── models/                    # SQLAlchemy 2.0 declarative async models
│   ├── __init__.py
│   ├── base.py                # Base model with timestamp mixins
│   ├── user.py                # User model with points & referral metadata
│   ├── coupon.py              # Coupon model (categories, stock_type, stock, points)
│   ├── coupon_code.py         # Individual unique coupon codes inventory pool
│   ├── referral.py            # Referral tracking (PENDING, SUCCESSFUL, REJECTED)
│   ├── redemption.py          # Coupon redemption receipts
│   ├── channel.py             # Required Telegram channels configuration
│   ├── point_transaction.py   # Auditable points ledger
│   └── admin_action.py        # Admin action audit logs
│
├── keyboards/                 # Inline keyboard builders & typed CallbackData
│   ├── __init__.py
│   ├── user.py                # User navigation, categories, coupons, channels, share
│   └── admin.py               # Admin dashboard, coupon manager, restock, user manager
│
├── handlers/                  # Modular aiogram 3 routers
│   ├── __init__.py
│   ├── start.py               # /start with deep-link referral processing
│   ├── menu.py                # Main menu navigation, help, privacy, terms, stats
│   ├── coupons.py             # Coupon browsing, categories, pagination, search, redemption
│   ├── referrals.py           # Refer & earn link generation, stats & sharing
│   ├── profile.py             # User points balance, history, and redeemed coupons
│   ├── channels.py            # Channel verification flow & callback triggers
│   └── admin.py               # Admin dashboard, coupon CRUD, restock, user & channel controls
│
├── services/                  # Transactional business logic layer
│   ├── __init__.py
│   ├── user_service.py        # User registration, point transactions, banning
│   ├── referral_service.py    # Referral validation, lifecycle & anti-fraud verification
│   ├── coupon_service.py      # Coupon CRUD, search, pagination, transactional redemption
│   ├── stock_service.py       # Dual-mode restock & bulk unique code importer
│   ├── channel_service.py     # Channel membership verification via Telegram Bot API
│   └── fraud_service.py       # Anti-abuse validation & system aggregate metrics
│
├── middlewares/               # aiogram middlewares
│   ├── __init__.py
│   ├── db_session.py          # Auto-injects async db session into handlers
│   └── auth_middleware.py     # Banned user checks & admin flag injection
│
├── utils/                     # Helper utilities
│   ├── __init__.py
│   ├── validators.py          # Input validation (numbers, dates, channel formats)
│   ├── formatting.py          # Hinglish / English message templates
│   ├── security.py            # Admin authorization check & secret masking
│   └── backup.py              # SQLite timestamped database backup utility
│
├── data/                      # Local SQLite persistence directory
│   └── .gitkeep
│
└── tests/                     # Pytest async automated test suite
    ├── __init__.py
    ├── conftest.py            # Test fixtures (async db engine, mock bot)
    ├── test_referrals.py      # Test referral creation, verification, anti-fraud
    ├── test_coupons.py        # Test coupon creation, browsing, and category filters
    ├── test_redemptions.py    # Test transactional redemption, stock decrements, unique codes
    ├── test_points.py         # Test points balance, ledger transactions, admin adjustments
    └── test_admin.py          # Test admin authorization, restock, bulk codes, channels
```

---

## 🚀 Getting Started (Local Setup)

### Step 1: Install Python 3.11+
Ensure Python 3.11 or 3.12 is installed:
```bash
python --version
```

### Step 2: Create a Telegram Bot with @BotFather
1. Open Telegram and search for [@BotFather](https://t.me/BotFather).
2. Send `/newbot` and follow the prompts to choose a Name and Username.
3. BotFather will provide an HTTP API Token (e.g. `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz123456789`).

### Step 3: Get Your Telegram User ID
1. Search for [@userinfobot](https://t.me/userinfobot) on Telegram and send `/start`.
2. Note your numerical `Id` (e.g. `123456789`).

### Step 4: Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Edit `.env` with your credentials:
```env
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz123456789
ADMIN_ID=123456789
BOT_USERNAME=MyCouponRewardBot
DATABASE_URL=sqlite+aiosqlite:///./data/bot.db
POINTS_PER_REFERRAL=1

# Required Channels Configuration
CHANNEL_1=@OfferRaider
CHANNEL_2=@OfferMate
CHANNEL_3=@Grabmint

LOG_LEVEL=INFO
```

### Step 5: Install Dependencies
Create a virtual environment and install requirements:
```bash
python -m venv venv

# On Windows:
venv\Scripts\activate

# On Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### Step 6: Run Automated Tests
Verify all business logic and database constraints:
```bash
pytest -v
```

### Step 7: Start the Bot
```bash
python bot.py
```

---

## 📢 Telegram Bot Permissions & Channel Setup

### Adding Required Channels
To verify whether a user has joined your channel:
1. Add your Bot as an **Administrator** in your Telegram channel(s).
2. The bot only needs the **"Invite Users via Link"** or standard admin membership check permission.
3. Open your bot as admin, send `/admin` -> Click **📢 Required Channels** -> **➕ Add Channel**.
4. Enter your Channel Username (e.g. `@MyDealsChannel`) or numerical Chat ID (e.g. `-1001234567890`) and invite link.

### Membership Verification Rules:
- `MEMBER` -> ✅ Valid
- `ADMINISTRATOR` -> ✅ Valid
- `CREATOR` -> ✅ Valid
- `RESTRICTED` (with `is_member=True`) -> ✅ Valid
- `LEFT` / `KICKED` / Not Found -> ❌ Verification fails with prompt to join

---

## 🎁 How Coupons & Stock Work

### Mode A: Single Reusable Code (Quantity Stock)
- Used for general promo codes (e.g. `AMZ100OFF`, `SWIGGY50`).
- You configure an initial stock count (e.g. `20`).
- Each user who redeems receives this promo code.
- Stock decrements by 1 on each redemption until it reaches `0`.

### Mode B: Unique Individual Codes Pool
- Used for unique gift cards or single-use activation vouchers (e.g. `AMZ-XYZ-111`, `AMZ-XYZ-222`).
- Admin imports codes in bulk using **Bulk Add Codes** (1 code per line).
- Duplicates are automatically skipped.
- When a user redeems, the system atomically assigns one `AVAILABLE` code to the user and marks it `USED`.
- Stock is always equal to the count of remaining `AVAILABLE` codes.

---

## 👑 Admin Capabilities Reference (`/admin`)

| Action | Description |
|---|---|
| **📊 Dashboard** | Live overview of users, referrals, points issued, stock, and redemptions. |
| **➕ Add Coupon** | 8-step wizard to create a coupon with category, points, and stock mode. |
| **📦 Restock Coupon** | Instantly add numerical stock or paste bulk unique codes. |
| **✏️ Edit / ⏸ Disable** | Modify coupon details or temporarily disable it from user view. |
| **👥 User Lookup** | Search users by Telegram ID/Code, view balance, add/deduct points, or ban. |
| **📢 Channel Manager** | Add or remove required channels dynamically. |
| **💾 Database Backup** | Create timestamped SQLite backup in `backups/` directory. |
| **📜 Audit Logs** | Track all administrative point changes and restock operations. |

---

## ☁️ Deployment Guides

### Deploying to Railway / Render / VPS with HTTPS WebApp

1. Fork or push this repository to GitHub.
2. In your deployment dashboard (Railway, Render, VPS), set your environment variables:
   - `BOT_TOKEN`: Your bot token from @BotFather
   - `ADMIN_ID`: Your Telegram numeric ID
   - `BOT_USERNAME`: Your bot username without @
   - `WEBAPP_PORT`: `8080` (or `PORT` provided by host)
   - `WEBAPP_URL`: `https://your-domain.com/verify` (Must be an **HTTPS** URL for Telegram Mini Apps)
   - `DATABASE_URL`: `sqlite+aiosqlite:///./data/bot.db` (with persistent volume mounted at `/app/data`) or PostgreSQL `postgresql+asyncpg://...`

### Local Development & Testing WebApp Mini App
Telegram Bot API requires an **HTTPS** URL to launch Mini Apps inside the Telegram client.
For local development:
1. Start the bot and server:
   ```bash
   python bot.py
   ```
2. In a separate terminal, expose the local port (8080) using Cloudflare Tunnel or Ngrok:
   ```bash
   cloudflared tunnel --url http://localhost:8080
   # OR
   ngrok http 8080
   ```
3. Copy the generated HTTPS URL (e.g. `https://random-id.trycloudflare.com/verify`) and set it in your `.env`:
   ```ini
   WEBAPP_URL=https://random-id.trycloudflare.com/verify
   ```
4. Restart `python bot.py`. The `🔒 Verify` button will now open the native Telegram WebApp popup on your phone or desktop.
6. Railway will automatically build the `Dockerfile` and start the bot.

---

### Deploying to Render

1. Log in to [Render.com](https://render.com).
2. Click **"New"** -> **"Background Worker"** (or **Web Service** with Docker runtime).
3. Connect your GitHub repository.
4. Select **Docker** as the Environment.
5. Under **Environment Variables**, set:
   - `BOT_TOKEN`
   - `ADMIN_ID`
   - `BOT_USERNAME`
6. If using SQLite, attach a **Persistent Disk** mounted at `/app/data`.
7. Click **Deploy**.

---

### Deploying to VPS (Docker Compose)

1. Clone repository on your VPS:
   ```bash
   git clone <repo_url> coupon_bot && cd coupon_bot
   ```
2. Copy and configure `.env`:
   ```bash
   cp .env.example .env
   nano .env
   ```
3. Build and launch with Docker Compose:
   ```bash
   docker compose up -d --build
   ```
4. View live logs:
   ```bash
   docker compose logs -f
   ```

---

## 🔒 Security & Privacy

- **Data Minimization**: Only Telegram ID, First Name, Username, Points Balance, and Redemption history are stored.
- **Zero Raw Secrets**: API tokens and private keys are loaded strictly via environment variables.
- **Transaction Safety**: All mutations utilize isolated transactional boundaries preventing race conditions.
- **Audit Logging**: Every point adjustment and restock action is permanently recorded.

<!-- Deployment trigger: Render restart -->
