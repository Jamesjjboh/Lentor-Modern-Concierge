# Lentor Modern Digital Concierge & Resident Knowledge Base

[![Google Cloud Run](https://img.shields.io/badge/Google_Cloud_Run-Serverless-4285F4?logo=google-cloud&logoColor=white)](https://cloud.google.com/run)
[![Google Cloud Firestore](https://img.shields.io/badge/Google_Cloud_Firestore-Native_NoSQL-FFCA28?logo=firebase&logoColor=black)](https://cloud.google.com/firestore)
[![Gemini 3.5 Flash Lite](https://img.shields.io/badge/Gemini_3.5_Flash_Lite-Autonomous_Agent-8E75C2?logo=google&logoColor=white)](https://ai.google.dev/)
[![Telegram Bot API](https://img.shields.io/badge/Telegram_Bot_API-v22.8-26A5E4?logo=telegram&logoColor=white)](https://core.telegram.org/bots/api)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An autonomous, privacy-preserving 24/7 Digital Concierge and living knowledge base built for the **~605 households at Lentor Modern** (an integrated mixed-use development by GuocoLand in Singapore, atop Lentor Modern Mall and Lentor MRT).

**Status:** Live 24/7 on Google Cloud Run (Dedicated to ~605 households at Lentor Modern).  
*Direct bot access is restricted to estate residents.*

---

## 🎯 Product Purpose & Value Proposition

In large residential condominiums, residents encounter three distinct friction points:
1. **The 8:00 PM Desk Closure:** The physical concierge desk on Level 4 closes in the evening, leaving after-hours questions unanswered.
2. **Unsearchable Estate PDFs:** Official MCST by-laws and renovation guidelines are buried in 60-page PDF documents.
3. **Telegram Chat Noise:** Community groups repeat the same 15 questions every week (aircon ledge restrictions, broadband riser keys, Taobao delivery loading bays, mall clinic hours, and defect contractor tracking).

The **Lentor Modern Digital Concierge** bridges this gap as an **autonomous AI Agent** (not a brittle single-prompt RAG), dynamically choosing and chaining specialized tools to answer resident inquiries in private 1-on-1 chats.

### 📈 Production Traction (First 72 Hours)
Following a single announcement in the resident Telegram community:
* **55 registered households** (~9.1% estate adoption) onboarded organically with zero marketing or reminders.
* **193 production interactions logged** (64 conversational queries + 129 quick menu taps).
* **100% answer accuracy rate** with zero negative feedback flags.
* **53.4% of queries occurred after 6:00 PM**—validating strong after-hours self-serve demand once the physical concierge desk closes.
* **Sustained Daily Organic Engagement:** Continues to handle daily resident queries beyond initial launch-day curiosity.

---

## 🏗️ System Architecture & Ultra-Fast Response Pipeline

```mermaid
flowchart TD
    subgraph ResidentExperience["Resident Experience (1-on-1 Telegram)"]
        User["Resident (@LMConciergeBot)"] -->|"Tap Menu or Ask Question"| Webhook["Cloud Run Webhook<br/>(asia-southeast1)"]
    end

    subgraph FastPath["Zero-Shot Fast FAQ (<5ms, Zero LLM Cost)"]
        Webhook -->|"Top 21+ High-Frequency Queries"| FastFAQ["Pre-Compiled Regex Index<br/>(src/fast_faq.py)"]
        FastFAQ -->|"Instant Match (Gym, Pool, Reno, MRT, Paint, EV, Lifts, Chute, Games Room, Co-Working, Yale Lock, Novade)"| QuickReturn["Instant Verified Response (<5ms)"]
    end

    subgraph AgentCore["Autonomous Agent Core (Gemini 3.5 Flash Lite)"]
        FastFAQ -->|"Nuanced, Novel or Complex Queries"| Agent["Autonomous Tool Orchestrator<br/>(src/agent.py)"]
        Agent -->|"Multimodal Vision Analysis"| Vision["analyze_resident_image"]
        Agent -->|"Bylaws & Defect Hotlines"| Tool1["search_bylaws_and_handbook"]
        Agent -->|"Mall Directory & ResiQ"| Tool2["search_mall_directory"]
        Agent -->|"Crowdsourced Neighbour Tips"| Tool3["get_verified_community_tips"]
        Agent -->|"MA Ticket Draft"| Tool4["generate_mcst_email_draft"]
        Agent -->|"New Tip Submission"| Tool5["submit_tip_to_moderation"]
        Agent -->|"Estate & School Catchment"| Tool7["search_estate_profile"]
    end

    subgraph KnowledgeData["In-Memory Knowledge Cache (_DATA_CACHE)"]
        Tool1 --- K1[("bylaws_handbook.json<br/>(Bylaws, Paint Specs & Contacts)")]
        Tool1 --- K4[("appliance_manuals.json<br/>(SMEG, Yale, Rheem, Aircon)")]
        Tool1 --- K5[("estate_contacts.json<br/>(21 Supplier Hotlines)")]
        Tool2 --- K2[("mall_directory.json")]
        Tool3 --- K3[("verified_community_tips.json<br/>(34 Verified Resident Tips)")]
        Tool7 --- K6[("estate_profile.json<br/>(Transit, Fees & Schools)")]
    end

    subgraph DatabaseLayer["Cloud Persistence & Moderation"]
        Tool5 -->|"Pending Tip"| Firestore[("Cloud Firestore<br/>(Native Mode)")]
        Firestore -->|"Push Alert with [Approve]/[Reject]"| Admin["Admin Private Telegram<br/>(@jamesjjboh)"]
        Admin -->|"Taps [Approve]"| Firestore
    end
```

---

## 🛠️ The 7 Autonomous Agent Tools

| Tool | Purpose | Data Source |
| :--- | :--- | :--- |
| `search_bylaws_and_handbook(query)` | Queries official MCST by-laws, paint specifications (Intermatt BS E55, Dulux Thick Smoke 96YR 09/033), 8 appliance manuals (SMEG, Yale, Rheem, Mitsubishi), 21 supplier hotlines, Novade defect logging, and renovation rules. | `data/processed/bylaws_handbook.json` + `appliance_manuals.json` + `estate_contacts.json` |
| `search_mall_directory(category, shop_name)` | Looks up Lentor Modern Mall shops (CS Fresh, Minmed Clinic, Guardian, Toast Box, Mulberry Learning childcare), floor levels (`B1`, `L1`, `L2`), hours, direct online ordering/queuing links (via ResiQ), and verified resident discounts. | `data/processed/mall_directory.json` |
| `get_verified_community_tips(topic)` | Retrieves verified crowdsourced neighbour tips (Level 2 delivery intercom, 3.8m loading bay clearance, induction lock quirks, aircon piping SWG requirements, evening grocery discounts). | `data/processed/verified_community_tips.json` + Firestore approved tips |
| `generate_mcst_email_draft(issue_type, details)` | Formats structured, professional inquiries addressed to the Managing Agent (CBRE at `managementoffice@LT-MODERN.COM`). | Dynamic Agent Template |
| `submit_tip_to_moderation(topic, tip_text)` | Automatically structures resident discoveries and queues them for admin moderation. | Firestore `community_tips/` queue |
| `submit_developer_feedback(category, details)` | Captures resident suggestions, bug reports, or data corrections and routes them directly to the bot creator & admin (@jamesjjboh). | Firestore `resident_feedback/` queue |
| `search_estate_profile(query)` | Looks up verified estate specs (GuocoLand, 605 units across 3 towers), unit mix & bathroom configurations, Lentor MRT (TE5) first/last train timings, bus lines (825, 855, 852), and official MOE primary school proximity tiers (Anderson Primary strictly <1km; CHIJ St. Nicholas 1–2km). | `data/processed/estate_profile.json` |

---

## ⚡ Superpowers & Admin Features

### 1. In-Chat Interactive Moderation
* When a resident submits a tip via `/tip <topic> <content>`, the agent pushes an interactive alert directly to the Admin's private Telegram chat:
  > 🔔 **New Resident Tip Submitted:**  
  > *Topic:* Mall  
  > *Tip:* "CS Fresh sushi 20% discount starts at 8:30pm"  
  > `[ ✅ Approve ]` `[ ❌ Reject ]`
* Tapping `[ ✅ Approve ]` updates Firestore status to `approved`, making it instantly live for all ~605 households.

### 2. Estate Broadcast Engine (`/broadcast`)
* Admin command: `/broadcast 📢 Lift maintenance for Tower 1 tomorrow from 10am to 12pm.`
* Iterates through all registered users in Firestore with safety rate-limiting (25 msgs/sec).

### 3. Product Analytics, Growth & Content Gaps (`/admin_stats [7|30|all]` & `/growth`)
An instant, text-first dashboard (no chart rendering), with inline buttons `[ 7d ] [ 30d ] [ All ] [ 📈 Growth ] [ 🕒 Recent ] [ 👥 Users ] [ 📋 Gaps ] [ 🔄 Refresh ]`.

| Metric | Definition |
| :--- | :--- |
| **Registered users** | Unique Telegram accounts that have started or messaged the bot. This is **not** a household count: one home may have several users, and no unit numbers are collected (privacy by design). |
| **New / Active 7d / Active 30d** | Users first seen in the window, and users active in the last 7 / 30 days. |
| **Adoption ≈** | Registered users ÷ 605 units. An approximation only (users, not households). |
| **Total Interactions** | Combined resident usage summing **Questions Asked + Quick-Menu Taps** in the selected window. |
| **Questions asked** | Typed and photo questions in the window, showing total questions, active askers count & percentage, average questions per active user, and lurker count. |
| **Quick-menu taps** | Summation total of all `/menu` button presses alongside individual button counts (Transit, Facilities, Contacts, etc.). |
| **Growth & Traffic Engine (`/growth`)** | 1-Tap `[ 📈 Growth ]` sub-screen displaying **Hourly Traffic Distribution** (Morning/Afternoon/Evening/Late Night peak hours in SGT), **Daily Activity Breakdown**, and **Week-on-Week (WoW)** percentage engagement deltas. |
| **User Activity Breakdown** | 1-Tap `[ 👥 Users ]` sub-screen ranking residents by activity (questions asked in window, lifetime queries, quick-menu taps, and humanized relative active timestamps). |
| **Recent Questions Stream** | 1-Tap `[ 🕒 Recent ]` sub-screen or `/recent [n]` command displaying the latest resident queries with user attribution, time elapsed, and matched retrieval tools. |
| **Answer rate** | Share of questions the bot could answer, detected from the reply wording (e.g. "I don't have…", "No shops found…", "couldn't find…"), not just two fixed phrases. |
| **Top topics** | Questions grouped by the tool used (handbook, mall, transit/estate profile, tips, etc.). |
| **Content gaps** | Unanswered questions, de-duplicated and ranked by how often they were asked (`"Is there a pet salon?" ×7`). |
| **Feedback** | Totals, new/unresolved count, breakdown by type (bug / data correction / feature request) and age of the oldest unresolved item. |

* **Daily sparkline:** a 7-day question trend, e.g. `▁▃▅▂▇▄▂`.
* **Growth engine (`/growth [7|30|all]`):** track hourly peak times and week-on-week adoption trends to optimize estate notices and identify when residents most frequently seek assistance.
* **Recent questions stream (`/recent [n]`):** easily audit the latest questions asked by residents to spot immediate community concerns or missing handbook items.
* **Conversational analytics (admin only):** just ask in chat, e.g. *"What was total bot engagement this week?"*, *"Who are the most active users?"*, or *"How many questions did each user ask?"*. Gemini answers using only the verified aggregates (never raw resident messages) and cites exact numbers.

### 4. Multimodal Vision & Photo Ingestion
* Residents can snap photos of mall flyers, opening hours notices, or appliance error codes directly in Telegram without typing.
* **Auto-Intent Classification:** Automatically categorizes photos into either a *Community Tip* (e.g., CS Fresh promotions), *Bug/Feedback* (with screenshot), or a *Resident Query* (e.g., induction cooker error code "L").
* **Photo Moderation Cards:** For tips, pushes the resident's photo directly to the Admin's private Telegram chat with interactive inline `[ ✅ Approve ]` / `[ ❌ Reject ]` buttons.
* **Privacy by Design:** Strict Singapore PII scrubber ensures unit numbers, phone numbers, and resident identities are stripped before publication.

### 5. Native Swipe-to-Reply & Tap-to-Reply Resident Feedback
* Residents can submit feature requests or report bugs via `/feedback <idea>`, `/bug <issue>`, or natural chat.
* **Instant Admin Notification:** Pushes a card with resident details directly to Admin's private Telegram.
* **Native Swipe-to-Reply:** Admin simply swipes left on the notification card like a normal chat message, types their response, and hits send. The bot routes the message directly into the resident's 1-on-1 chat.
* **Tap-to-Reply:** Inline button `[ 💬 Reply ]` triggers Telegram `ForceReply` for 1-tap mobile reply mode.
* **Serverless Resilient:** Stores message mappings in Firestore (`admin_reply_mappings/`) so swipe-to-reply works seamlessly even after Cloud Run restarts.

### 6. Interactive 1-Tap Quick Menu (`/menu`)
* Residents can pull up immediate answers without consuming AI tokens:
  * **Estate Contacts Hub:** Managing Agent (CBRE), Physical Concierge Counter (9am–8pm daily), 24/7 Security Control Room, and Developer CST, with interactive sub-screens for **Appliances & Equipment** (Mitsubishi aircon, SMEG kitchen, Yale lock, Rheem/Ferroli heaters, Fermax intercom, Metform letterbox, TK Elevator), **Fittings & Contractors** (Windows, bi-fold & pocket doors, sanitary mixers, shower screens, timber flooring, tiles, carpentry, Lian Beng), **Utilities** (SP Services & City Energy), and a 1-tap **MA Email Draft**.
  * **Facilities & Gym:** Gym hours (6am–10pm), pool hours (7am–10pm), tennis court, Games Room (convertible table tennis/pool/darts), Dance Studio, Business Lounge & Co-Working Space (Level 4 Clubhouse work booths & Level 14 Sky Club study corners), BBQ pavilions, car wash bays, and L3 resident EV charging lots.
  * **Transit & Buses:** Lentor MRT (TE5) first/last train timings and Exit 1 buses (825, 855, 852).
  * **Mall & Deals Hub:** CS Fresh markdown pro-tip, full 54-store tenant directory by floor, 34 GuocoLand voucher merchants, 31 resident discounts, and direct ResiQ order/queue link.
  * **Moving & Reno:** Renovation & drilling hours, minor DIY drilling guidelines, deposit schedule, loading bay clearance (3.8m), Level 2 bin area disposal for large boxes, and official paint codes.
  * **iPlus Living Guide:** Mobile intercom buzzer video setup, property activation codes, and facility booking rules (Tennis, Games Room, Dance Studio, Meeting Room, BBQ, Function Room).
  * **Guest Directions (MRT & Car):** 1-tap tower selection buttons (`[ Tower 3 ]`, `[ Tower 5 ]`, `[ Tower 7 ]`) and `/directions` command for copy-paste visitor guidance.

### 7. Responsive UX: In-Chat Status Bubbles & 1-Tap Fallback Action Cards
* **In-Chat Progress Status Bubble:** Matches modern interactive bot UX by posting immediate feedback directly below the resident's message (`🛎️ Looking that up for you...` for text, `📥 Receiving photo...` $\rightarrow$ `🔍 Checking details from your photo...` for photos) and seamlessly editing it into the response.
* **Typing Indicator Heartbeat:** Background heartbeat task continuously refreshes Telegram's `ChatAction.TYPING` every 3.5 seconds, ensuring residents always see that the bot is actively thinking and working on their question.
* **Warm Container Response:** Cloud Run maintains `--min-instances 1` to eliminate container cold starts.
* **Empathetic Concierge Fallback Cards:** If a resident asks a question outside existing bylaws or directories, the bot provides warm concierge signposting and attaches 1-tap action buttons:
  * `[ ✉️ Draft Email to MA ]`: Generates a formatted inquiry email to CBRE (`managementoffice@LT-MODERN.COM`).
  * `[ 🏢 On-Site Contacts ]`: Displays estate office phone hotlines and locations.
  * `[ ◀️ Quick Menu ]`: Jumps back to main quick shortcuts.

### 8. Resident 1-Tap Answer Rating & Admin Review Workflow
* **1-Tap Answer Validation:** Every factual response sent to residents contains subtle `[ 👍 Helpful ]` and `[ 👎 Inaccurate ]` buttons.
* **Auto-Collapse & Reassurance:** Tapping `👍` immediately confirms via toast and locks to `[ ✅ Marked as Helpful ]`. Tapping `👎` reassures the resident that the admin was alerted and locks to `[ ⚠️ Flagged for Review ]`.
* **Instant Admin Alert Card:** When an answer is flagged `👎`, the bot pushes an interactive alert card to the Admin's private Telegram DM containing resident details, query text, bot response, retrieved tools, plus `[ 💬 Reply to Resident ]` and `[ 📁 Mark Reviewed ]` buttons.
* **Admin Review Command (`/flagged`):** Allows admin to review the top 10 most recent flagged answers on demand anytime.

### 9. Anti-Abuse Rate Limiting, Admin Spam Alerts & Webhook Security
* **Sliding-Window Rate Limiter:** Protects Gemini API quotas and serverless compute by capping requests at 10 queries per 60 seconds per user.
* **Instant Admin Spam Alert:** If a user hammers the limit, their requests are throttled and an alert card (`🚨 Rate Limit Alert`) is immediately pushed to the Admin's private Telegram DM.
* **Webhook Secret Verification:** Cloud Run webhook supports `WEBHOOK_SECRET_TOKEN` to ensure updates are verified against Telegram's `X-Telegram-Bot-Api-Secret-Token`.
* **Prompt Hardening:** Strict anti-jailbreak guidelines protect system prompts, API keys, and internal configs.

### 10. Comprehensive Estate Data: MCST Maintenance Fees & Supplier Hotlines
* **MCST Maintenance Fees & Share Values:** Full schedule ingested for all unit types (Sub-MC $39/SV + Main MC $5.80/SV = $44.80/SV base, or $48.832/SV incl. 9% GST; 1BR 8 SV / $390.66; 2BR 9 SV / $439.49; 3BR Compact 10 SV / $488.32; 3BR Premium & 4BR 11 SV / $537.15).
* **Official Supplier Hotlines:** Direct contacts for Mitsubishi Aircon (6473 2308), SMEG (6950 0910), Rheem Water Heater (6872 2043), Assa Abloy Yale Lock (6591 8868), and Fermax Intercom (6259 0700).
* **Shopee / SPX Parcel Hubs:** Documented 24/7 Shopee lockers at Carpark Level 2 and Twigly's Convenience Store (#01-10) collection point.
* **Dynamic Telegram Command Menu:** Automatically syncs native Telegram `[Menu]` buttons tailored for residents vs. administrators.

### 11. Visitor Navigation Engine & Resident Directions Generator
* **MRT & Car Directions Templates:** Ingested navigation knowledge covering Lentor MRT Exit 1 $\rightarrow$ Clubhouse Lobby $\rightarrow$ Level 4 Concierge $\rightarrow$ Sky deck / bridge transfer, plus the crucial Google Maps warning (preventing drivers from mistakenly turning into the commercial mall drop-off).
* **1-Tap Menu & Dedicated Command (`/directions`):** Residents can tap `📍 Guest Directions (MRT & Car)` in `/menu` or run `/directions [tower] [unit]` to get an instant, copy-paste WhatsApp/Telegram message formatted with clear emojis.
* **Zero PII Storage:** Purely parameterized templates without hardcoded resident unit numbers or levels.
* **Published Privacy Policy:** Full Singapore PDPA-compliant [PRIVACY.md](PRIVACY.md) linked directly to the bot profile via Telegram's `/setprivacy`.

---

## 💰 Zero-Cost Serverless Architecture ($0.00 / month)

| Cloud Component | Service Tier | Monthly Cost |
| :--- | :--- | :--- |
| **Hosting** | Google Cloud Run (`asia-southeast1`) | **\$0.00** (Free Tier includes 2 million requests + 360,000 GiB-seconds / month; warm instance with 512MiB memory) |
| **Database** | Google Cloud Firestore (Native Mode) | **\$0.00** (Uses <1% of 50k free reads/day) |
| **Storage / Registry** | Google Artifact Registry | **\$0.00** (Automated cleanup keeps $\le 2$ builds, < 380 MB of 500 MB Free Tier) |
| **AI Inference** | Google Gemini 3.5 Flash Lite (with 3.1 / 3.8 fallback cascade) | **\$0.00** (Generous API tier) |

### Automated Artifact Registry Cleanup Policy
To ensure container images never trigger storage billing (avoiding historical build accumulation):
```bash
gcloud artifacts repositories set-cleanup-policies cloud-run-source-deploy \
    --location=asia-southeast1 \
    --policy=scripts/cleanup-policy.json \
    --no-dry-run
```
* **Rule 1 (`keep-latest-two-versions`)**: Protects the active and backup container images.
* **Rule 2 (`delete-old-images`)**: Automatically deletes builds older than 1 day upon new release.

---

## 🛡️ Privacy & Strict Singapore PII Sanitization

Before raw chat exports or community submissions touch the knowledge base, [src/parser.py](file:///Users/jamesboh/Lentor%20Modern%20Concierge/src/parser.py) applies multi-stage redaction:
* **Singapore Unit Numbers:** `#\d{1,2}-\d{2,4}` $\rightarrow$ `[UNIT_REDACTED]`
* **Singapore Phone Numbers:** `(?:\+?65)?[89]\d{7}` $\rightarrow$ `[PHONE_REDACTED]`
* **Email Addresses:** `[\w\.-]+@[\w\.-]+\.\w+` $\rightarrow$ `[EMAIL_REDACTED]`
* **Telegram Usernames:** `@[A-Za-z0-9_]+` $\rightarrow$ `[USER_HANDLE]`
* **Noise Stripping:** Automatically removes fillers (*"thanks"*, *"ok"*, stickers, service notices).

---

## 🚀 Setup & Local Development

### 1. Clone & Setup Environment
```bash
git clone https://github.com/Jamesjjboh/Lentor-Modern-Concierge.git
cd Lentor-Modern-Concierge
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment (`.env`)
```bash
cp .env.example .env
```
Fill in:
* `GEMINI_API_KEY`: Google AI Studio API Key.
* `TELEGRAM_BOT_TOKEN`: Token from `@BotFather`.
* `ADMIN_TELEGRAM_ID`: Your personal Telegram ID from `@userinfobot`.
* `GCP_PROJECT_ID`: `gen-lang-client-0682470012`

### 3. Run Locally (Long Polling)
```bash
python -m src.bot
```

### 4. Deploy to Google Cloud Run (Singapore)
```bash
./deploy.sh
```

---

## 📁 Repository Directory Structure

```text
Lentor Modern Concierge/
├── data/
│   ├── raw/                  # Raw PDFs & Telegram exports (strictly git-ignored)
│   └── processed/            # Cleaned, PII-scrubbed JSON knowledge chunks
├── scripts/
│   ├── cleanup-policy.json   # Artifact Registry lifecycle policy (keeps max 2 builds)
│   └── ingest_knowledge.py   # Knowledge ingestion pipeline (PDFs, chat exports, ResiQ)
├── src/
│   ├── __init__.py
│   ├── config.py             # Decoupled environment & model settings
│   ├── parser.py             # PDF extractor & Singapore PII scrubber
│   ├── database.py           # Firestore client & query models
│   ├── agent.py              # Gemini 3.8 Flash agent & 7 tools
│   ├── analytics.py          # Admin analytics engine: metrics, content gaps, dashboard, Q&A
│   ├── admin.py              # In-chat moderation callbacks, /broadcast & /admin_stats
│   └── bot.py                # Telegram bot, 1-tap /menu & webhook runner
├── tests/
│   └── test_analytics.py     # Unit tests for the analytics engine
├── Dockerfile                # Production Cloud Run container specification
├── deploy.sh                 # Zero-downtime deployment script with webhook registration
├── requirements.txt          # Python dependencies
├── CHANGELOG.md              # Semantic release history
└── README.md                 # Project documentation
```

### Run the tests
```bash
PYTHONPATH=. python -m unittest tests.test_analytics
```

---

## 👤 Author & Maintainer
Built and maintained by **James Boh** for the residents of Lentor Modern.
