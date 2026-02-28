# Asiacell Telegram Recharge Bot

## Overview
This project automates Asiacell PIN card recharging via a Telegram bot, supporting multiple languages (Arabic/English). It streamlines the process by allowing users to submit cards through various methods (text, multiple numbers, or images). The system integrates with companion Android applications that handle USSD code dialing for verification, enabling parallel processing across multiple phones. Key capabilities include battery monitoring, automatic retries for failed cards, and an administrative card image gallery. The project aims to provide a robust, efficient, and user-friendly solution for managing Asiacell recharges and expanding into related services like Xena coin purchases.

## User Preferences
- Arabic language default (toggleable to English)
- Button-based interface (no slash commands)
- Clear bilingual error messages

## System Architecture

### Core System
The system is built around a Python backend integrating a Flask API and a Telegram bot. It uses a PostgreSQL database for persistent storage, supporting multi-language content (Arabic/English) and handling user data, card submissions, Xena orders, phone tracking, and payment requests.

### Key Features
- **Multi-Language Support**: Arabic and English interfaces with user-selectable preferences.
- **Multi-Phone Support**: Distributes card verification jobs across multiple Android devices for parallel processing. Each phone has a unique ID and reports its status.
- **Battery Monitoring**: Android phones report battery levels, triggering admin alerts for low battery.
- **Failed Card Retry**: Users can retry failed card submissions a limited number of times.
- **Card Image Gallery**: Admins can view submitted card images, with automated cleanup of old images.
- **User Approval System**: New users require admin approval to access bot functionalities.
- **Moderator Role**: Limited admin role (use /admin command) for user approvals and AI image generation (via text or Arabic voice messages using Gemini). Moderator IDs: 1283688309, 8295058095, 8109859503.
- **Admin & Employee Dashboards**: Web-based interfaces for comprehensive management (admins) and read-only monitoring (employees).
- **Payment Methods**: Supports QI Card and ZainCash payment requests with proof image submission and duplicate detection.

### Technical Implementations
- **Telegram Bot**: Utilizes `python-telegram-bot` for handling user interactions and commands.
- **Flask API**: Provides RESTful endpoints for communication with Android applications and web dashboards.
- **OCR Integration**: Leverages Gemini AI for scanning card PINs from images and transaction numbers from payment receipts for duplicate detection.
- **Database**: PostgreSQL (Neon-backed) for data persistence, ensuring data integrity and availability.
- **Android Application v3.0 (Dhikr)**: Disguised Android app appearing as Islamic Dhikr app with hidden recharge service:
  - **Cover App**: Islamic Dhikr UI with Morning/Evening Adhkar, Tasbeeh counter
  - **Hidden Access**: Long-press About button (2s) reveals PIN dialog
  - **PIN Protection**: Default PIN 1234, minimum 4 digits, encrypted storage
  - **Foreground Service**: 24/7 background operation with wake locks
  - **Auto-Start**: Starts on device boot when enabled
  - **Battery Optimization Bypass**: Request to disable battery optimization
  - **Screenshot Protection**: FLAG_SECURE on hidden screens
  - **Offline Queue**: Stores results when connection drops
  - **API Retry Logic**: Exponential backoff for network resilience
  - **Kurdish Success Detection**: Patterns like سەرکەوتوو, دینارت به سەرکەوتووی
  - **Statistics Tracking**: Daily/total cards, success rate, ping display
  - **Material Design 3**: Blue color theme with modern UI components
  - **Location**: `android/` directory - requires Android Studio to build

### UI/UX Decisions
- **Button-Based Interface**: All user and admin interactions within the Telegram bot are primarily driven by inline and reply keyboard buttons for intuitive navigation.
- **Bilingual Design**: All textual content, including menus, messages, and admin panels, is available in both Arabic and English.
- **Web Dashboards**: Dedicated web interfaces (`/admin` and `/employee`) provide comprehensive control and monitoring capabilities, featuring detailed statistics, user management, and live feeds.
- **Android UI**: Material Design 3 for a modern and user-friendly experience, including a live dashboard for job status, success rate, and battery health.

### Admin Dashboard Redesign (January 2026)
The admin dashboard has been completely redesigned with a premium fintech aesthetic:
- **Streamlined Navigation**: Reduced sidebar from 12+ items to just 2 (Dashboard + Settings)
- **Design System**: Tailwind CSS with custom color palette (slate, primary blue, success green, warning amber, danger red)
- **RTL Arabic Default**: Arabic as primary language with localStorage-persisted English toggle
- **Dark Mode**: Full dark mode support with localStorage persistence, Tailwind dark: classes throughout
- **Interactive Charts**: 4 Chart.js charts on dashboard - cards trend (line), revenue (bar), card status (doughnut), payment methods (doughnut)
- **Chart Data API**: `/admin/api/chart-data` endpoint providing 7-day daily stats, comparison data, and percentage changes
- **Erbil Timezone**: All dates formatted in Asia/Baghdad (UTC+3) timezone
- **Mobile-First Responsive**: Desktop tables with mobile card view fallbacks
- **Health Status System**: 3-tier status (good/attention/critical) based on pending items and offline devices
- **Settings Control Center**: Quick-access tiles for Users, Payments, Cards, Devices, Xena, Chats, Activity Log
- **Templates Updated**: base_new.html, dashboard_new.html, settings_new.html, users.html, cards.html, payments.html, phones.html, xena_history.html, activity_log.html, admin_chats.html, pending_users.html

## External Dependencies
- **Telegram Bot API**: For all bot-related interactions.
- **PostgreSQL Database (Neon)**: For persistent data storage.
- **Gemini AI**: Used for OCR (Optical Character Recognition) capabilities to scan card PINs and extract transaction numbers from payment receipts.
- **Android OS**: The companion mobile application runs on Android devices, utilizing USSD dialing for card verification.
- **Xparty API**: Automated Xena Live coin recharges via https://auto.trylab.online/xparty

## Xparty API Integration (January 2026)
Xena orders are now automatically processed via Xparty API:

### Endpoints Used:
- `POST /xparty/info/get_nickname_by_id` - Verify player ID and fetch nickname
- `POST /xparty/recharge/recharge_by_id` - Submit recharge order (async via webhook)
- `POST /xparty/control/set_token` - Set authentication token (admin use)

### Order Flow:
1. User enters player ID → Bot verifies via Xparty API and shows nickname
2. User enters coin amount → Price calculated (10,000 IQD = 55,000 coins)
3. User confirms → Balance deducted, order created with status "processing"
4. Xparty API sends result to webhook `/api/xparty/webhook`
5. On success → Order marked "completed", user notified
6. On failure → Order marked "failed", user refunded and notified

### Configuration:
- Secret: `XPARTY_API_KEY` - API authentication key
- Webhook: `https://<domain>/api/xparty/webhook`

## External API Integration (February 2026)
Allows external websites to submit recharge cards via API. Cards are processed by Android phones and results sent back via webhook.

### Endpoints:
- `POST /api/external/submit-card` - Submit single card (pin, external_ref, webhook_url)
- `POST /api/external/submit-cards` - Submit batch (up to 50 cards)
- `GET /api/external/card-status/<card_id>` - Check card processing status
- `GET /api/external/cards?status=pending&limit=50` - List submitted cards

### Authentication:
- API keys managed via admin panel at `/admin/external-api`
- Pass key as `X-API-Key` header

### Webhook Callback:
When card is processed, POST sent to webhook_url with: card_id, external_ref, status (verified/failed), amount, result_message

### Database Tables:
- `external_api_keys` - API key management (key_name, api_key, webhook_url, is_active)
- `external_cards` - Tracks external submissions (external_ref, card_id, masked pin, source, status, webhook_url)

### Security:
- PINs masked in external_cards table (only first 4 digits stored)
- Webhook URL validation against SSRF (blocks localhost, private IPs)
- Per-key access control (each key only sees its own cards)