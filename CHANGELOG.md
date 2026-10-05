# Changelog

All notable changes to the **Lentor Modern Digital Concierge** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.8.0] - 2026-10-05

### Added
- **Visitor Directions & Navigation Template Generator**:
  - Implemented dynamic visitor routing for both **MRT** (Exit 1 $\rightarrow$ past Burger King $\rightarrow$ Clubhouse entrance beside Ma Kuang & Fresh and Clean $\rightarrow$ Level 4 Concierge $\rightarrow$ Sky deck / bridge $\rightarrow$ Intercom) and **Car / Grab / Taxi** navigation.
  - Included critical driver warning: Alerts visitors that Google Maps often misdirects drivers to the commercial Mall drop-off by mistake, instructing them to keep left into the Residents' Carpark ramp to Level 2/3 visitor parking.
  - Added customized walking cues for Tower 5 (cross small bridge, turn right) and generalized directional signage guidance for Towers 3 and 7.
- **1-Tap Quick Menu & Shortcut Command (`/directions`)**:
  - Added `📍 Guest Directions (MRT & Car)` button to `/menu` for instant 1-tap template access.
  - Added dedicated `/directions` command producing a formatted, ready-to-forward WhatsApp/Telegram navigation message with tower options.
  - Integrated into admin analytics tracking under `Guest Directions`.
- **Interactive Estate Contacts Hub (`menu_contacts`)**:
  - Upgraded the primary Estate Contacts menu into an interactive directory hub covering 22 verified service providers and contractors.
  - Retained essential on-site management (CBRE Managing Agent, 24/7 Residential Concierge, 24/7 Security Control, GuocoLand CST / Lian Beng) on the primary screen.
  - Added 4 dedicated 1-tap interactive sub-screens:
    - `[ 🔧 Appliances & Equipment (8) ]`: Authorized warranty and repair contacts for Mitsubishi Electric (Aircon: `6473 2308`), SMEG Singapore (Kitchen appliances: `6950 0910`), Assa Abloy Yale (Digital lock: `6591 8868`), Rheem (Electric water heater: `6872 2043`), Ferroli (Town gas heater: `9747 8743`), Fermax (Intercom & smart home: `6259 0700`), Metform (Letterbox lock: `6757 2822`), and TK Elevator (24/7 Lifts: `6890 1640`).
    - `[ 🚪 Fittings & Finishes (8) ]`: Architectural & defect contractors for Hungsen Engineering (Windows & sliding doors), PD Door (Bi-fold doors), Slide & Hide (Pocket doors), Carera Bathroom (Sanitary ware & mixers), Jin Yuan (Shower screens), T.J. Seang (Timber flooring), Masonry Pte Ltd (Tiles), and King Hup Construction (Cabinetry & wardrobes).
    - `[ ⚡ Utilities & Gas (2) ]`: SP Group (`1800-222-2333` / 24/7 electricity breakdown `1800-778-8888`) and City Energy (`1800-555-1661` / 24/7 gas emergency `1800-752-1800`), with move-in account opening advice.
    - `[ ✉️ Draft Email to MA ]`: In-place ready-to-send email template with 1-tap copy block and back navigation.
- **Interactive Mall & Deals Hub Suite (`menu_mall`)**:
  - Upgraded the Mall quick menu card with pro-tips (CS Fresh 8:30 PM sushi & bakery 20%–30% markdown hack).
  - Added 4 dedicated 1-tap interactive exploration sub-screens:
    - `[ 🏢 Full Directory (54 Stores) ]`: Complete mall tenant listing organized cleanly by floor (Basement 1, Level 1, Level 2) with unit numbers and categories.
    - `[ 🎟️ GuocoLand Vouchers (34) ]`: Complete listing of all 34 participating outlets (21 F&B + 13 retail/services) plus the reminder that CS Fresh does not accept mall vouchers.
    - `[ 🏷️ Resident Perks (31) ]`: Full breakdown of 31 resident discounts across dining and personal services.
    - `[ 📲 Open ResiQ ]`: Direct mobile URL launcher to skip queues and order ahead online.
- **Public Privacy Policy (`PRIVACY.md`)**:
  - Published comprehensive Singapore PDPA-compliant privacy policy outlining data collection, zero third-party tracking, and transient session retention.
  - Linked to Telegram `@LMConciergeBot` via `@BotFather` `/setprivacy`.
- **High-Definition Mascot Avatars**:
  - Added custom 3D Pixar character mascot avatars in `assets/avatars/`, including Shiba Inu, Corgi, and Samoyed concierge editions.

---

## [1.7.0] - 2026-10-04

### Added
- **MCST Maintenance Fees by Unit Type & Share Value**:
  - Ingested verified estate maintenance fee schedule across all unit types into `estate_profile.json` and `bylaws_handbook.json`:
    - Base contribution: Sub-MC (Residential) at $39.00/SV + Main MC (Common Property) at $5.80/SV = $44.80/SV base ($48.832/SV incl. 9% GST).
    - 1-Bed + Flex (527 sf, 8 SV): $358.40/mo ($390.66 incl. GST).
    - 2-Bed + Flex (678 & 732 sf, 9 SV): $403.20/mo ($439.49 incl. GST).
    - 3-Bed + Flex Compact (969–990 sf, 10 SV): $448.00/mo ($488.32 incl. GST).
    - 3-Bed + Flex Premium (1,109–1,130 sf, 11 SV): $492.80/mo ($537.15 incl. GST).
    - 4-Bed + Flex (1,528 sf, 11 SV): $492.80/mo ($537.15 incl. GST).
  - Updated `search_estate_profile` and `search_bylaws_and_handbook` to answer fee breakdowns and share value questions immediately.
- **Supplier Hotlines & Appliance Servicing Contacts**:
  - Filtered conversational stopwords and weighted equipment terms in `search_bylaws_and_handbook`.
  - Inquiries about air conditioning, water heaters, hobs, or locks directly surface official supplier contacts:
    - Mitsubishi Electric (ACMV): `6473 2308`
    - SMEG Singapore: `6950 0910`
    - Rheem Water Heater: `6872 2043`
    - Ferroli Gas Heater: `9747 8743` (WhatsApp)
    - Assa Abloy Yale Lock: `6591 8868`
    - Fermax (Intercom/Smart Home): `6259 0700`
- **Parcel Lockers & Shopee Collection Points**:
  - Added Shopee / SPX automated parcel lockers at Carpark Level 2 (near Tower 5 and letterboxes) to `verified_community_tips.json`.
  - Added Twigly's Convenience Store (#01-10) official Shopee collection point to both `mall_directory.json` and `verified_community_tips.json`.
- **Anti-Spam Sliding Window Rate Limiting & Admin Alerts**:
  - Enforced a 10 requests / 60 seconds rate limit per user across text questions and photo uploads.
  - Throttled users receive a polite wait message; admin receives an immediate private alert card in Telegram (`🚨 Rate Limit Alert`).
- **Dynamic Telegram Command Menu (`set_my_commands`)**:
  - Implemented `post_init` hook registering the native Telegram blue `[Menu]` button:
    - Residents see: `/start`, `/menu`, `/help`, `/tip`, `/feedback`, `/bug`.
    - Admin additionally sees: `/admin_stats`, `/flagged`, `/reply`, `/broadcast`.
- **Webhook Security & Secret Token**:
  - Added optional `WEBHOOK_SECRET_TOKEN` support across `config.py`, `.env.example`, `bot.py`, and `deploy.sh` to verify `X-Telegram-Bot-Api-Secret-Token`.
  - Hardened system prompt with explicit anti-jailbreak instructions.

---

## [1.6.0] - 2026-10-03

### Added
- **Resident 1-Tap Answer Feedback (👍 Helpful / 👎 Inaccurate)**:
  - Factual AI concierge responses in 1-on-1 private chat now include inline buttons (`[ 👍 Helpful ]` and `[ 👎 Inaccurate ]`).
  - Positive feedback triggers an instant toast confirmation (*"👍 Thank you! Glad this was helpful."*) and collapses to `[ ✅ Marked as Helpful ]`.
  - Negative feedback alerts the user (*"🙏 Thank you for flagging! We've notified the admin to review and correct this."*), collapses to `[ ⚠️ Flagged for Review ]`, and logs feedback directly in Firestore.
- **Real-Time Admin Flagged Answer Alert Workflow**:
  - Tapping `👎 Inaccurate` immediately pushes an alert card to Admin's private Telegram DM containing:
    - Resident name, Telegram handle, and User ID.
    - Exact query asked and bot's response.
    - Retrieved tools and knowledge sources.
    - Interactive `[ 💬 Reply to Resident ]` (2-way swipe/tap reply) and `[ 📁 Mark Reviewed ]` buttons.
- **Admin Review Command (`/flagged`)**:
  - Added dedicated `/flagged` admin command to inspect the 10 most recently reported inaccurate answers with timestamps and direct resident follow-up guidance.
- **Automated Test Suite (`tests/test_feedback.py`)**:
  - Full unit test coverage verifying rating keyboard generation, status transitions, Firestore logging, and callback handling.

---

## [1.5.0] - 2026-10-03

### Added
- **In-Chat Progress Status Bubble (Concierge Persona)**:
  - For text questions, the bot immediately posts `🛎️ Looking that up for you...` directly beneath the resident's message, editing into the response once ready.
  - For photo questions, the bot immediately posts `📥 Receiving photo...` and transitions to `🔍 Checking details from your photo...` before delivering the final answer.
- **Verified GuocoLand e-Voucher Merchant Directory (34 Official Stores)**:
  - Cross-referenced directly against official Lentor Modern Mall directory (`https://www.lentormodern.com.sg/shops/`), updating knowledge store with all 34 participating merchants categorized by F&B and Retail/Services.
- **Persistent Typing Heartbeat Indicator**:
  - Implemented background `_keep_typing` task running every 3.5s in `src/bot.py`, preventing Telegram's native typing indicator from expiring during agent tool execution and reasoning.
- **Refined Unanswered Query Concierge Fallback Cards**:
  - When the agent cannot find factual records for a query, it provides warm, polite signposting and attaches interactive 1-tap fallback buttons:
    - `[ ✉️ Draft Email to MA ]`: Generates a pre-formatted email draft addressed to CBRE (`managementoffice@LT-MODERN.COM`).
    - `[ 🏢 On-Site Contacts ]`: Instantly pulls up hotlines for Estate Management (+65 6054 3370), 24/7 Concierge (+65 6054 3375), and Security (+65 6054 3379).
    - `[ ◀️ Quick Menu ]`: Returns to main resident shortcut menu.
- **Warm Container Provisioning**:
  - Configured Cloud Run `--min-instances 1` in `deploy.sh` to eliminate container cold starts, keeping response times snappy 24/7.
- **Asynchronous Execution**:
  - Offloaded synchronous agent and multimodal vision execution to `asyncio.to_thread`, keeping the event loop responsive.

---

## [1.4.0] - 2026-10-03

### Added
- **Honest Resident Product Analytics Engine (`/admin_stats`)**:
  - Replaced ambiguous "registered households" metric with transparent, honest terminology: **Registered Residents (Telegram accounts)** out of 605 physical units.
  - Added rolling time-window analytics (`7d`, `30d`, `all`) with interactive inline switcher buttons (`[ 7D ]`, `[ 30D ]`, `[ All ]`).
  - Added daily activity sparkline and top topic volume tracking (Estate rules, Mall & shops, Community tips, MA drafts, Admin feedback, etc.).
  - **Ranked Content Gaps**: Groups and counts repeated unanswered questions so admin can prioritize adding missing estate bylaws or mall tenant details.
  - **Conversational Admin Q&A**: Admin can ask questions in natural language (e.g. *"what did residents ask most this week?"*) and receive structured analytics answers.
- **Verified Mulberry Learning @ Lentor Directory Correction**:
  - Replaced vague placeholder childcare reference with **Mulberry Learning @ Lentor** (`#02-01`, 1 Lentor Central S788887) across all estate profile data, community tips, and quick menus.
- **Interactive Quick Actions Menu (`/menu`)**:
  - 6 instant 1-tap resident shortcuts: Estate Contacts, Facilities & Gym, Transit & Buses, Mall & Deals, Moving & Reno, and iPlus Living Guide.

---

## [1.3.1] - 2026-10-03

### Added
- **Official Interior & Balcony Paint Specifications**:
  - **Internal Unit Paint (Walls & Ceilings)**: Verified developer handover specification is **Intermatt BS E55** (White). Injected into knowledge base to ensure resident touch-ups and defect rectification achieve exact sheen and color match.
  - **Balcony & Façade Paint**: Verified developer & MCST architectural specification is **Dulux (ICI) "Thick Smoke"**, Colour Code: **`96YR 09/033`** (System: Composilicon W55). Ingested into building by-law guidelines to maintain uniform external facade aesthetic.
  - Added seed verified community tip for instant 1-on-1 query answering regarding unit touch-up paint.

---

## [1.3.0] - 2026-10-03

### Added
- **Official Developer Documentation & Appliance Manual Ingestion**:
  - Extracted 44 official GuocoLand handover PDFs into structured knowledge stores (`data/processed/`).
  - Added full operational, maintenance, and error code guides for 8 home appliances:
    - SMEG Induction Hob (`SI2321D`): Child lock ('L') unlock steps, power booster, weekly cleaning.
    - SMEG Washer-Dryer (`WDJ852ESG`): Wash/dry cycles, error codes (`E01`-`E04`), drain pump maintenance.
    - SMEG Convectional Oven (`SF6300TVX`), Cooker Hood (`KSET62E`), and Fridge (`FC60EN3XL`).
    - Yale Digital Lock (`YDM7116A`): PIN setup, RFID pairing, emergency 9V battery jumpstart.
    - Rheem Storage Water Heater: Operation, safety relief valve, thermostat.
    - Mitsubishi Wall Mounted Aircon: Modes, vane positioning, filter cleaning cadence.
    - Smart Letterbox Lock (`S301`): PIN reset and programming.
  - Added official contacts directory (`estate_contacts.json`) covering 21 suppliers (Mitsubishi, SMEG, Yale, Fermax, TK Elevator, Carera, SP Services, City Energy).
  - Added Novade Defect Inspection guide and BCA 12-month Defect Liability Period (DLP) protocol.
  - Added material maintenance guides for engineered timber flooring, wall/floor tiles, solid surfaces, and windows.
- **Telegram Resident Chat Export Synthesis**:
  - Ingested 14 Telegram HTML chat files (9,802 messages) from verified owners and resident groups.
  - Applied automated filtering to eliminate 1,649 conversational chatter messages and 239 commercial ads / group buys (durians, ID packages, curtain pitches, marketplace sales).
  - Enforced strict Singapore PII sanitization (redacting `#XX-YY` unit numbers, `+65` numbers, and personal names).
  - Synthesized 31 verified, high-impact resident tips and workarounds into `verified_community_tips.json` (Level 2 delivery intercom access, 3.0m car park height limit, smart switch neutral wire requirements, and Novade defect photo practices).

---

## [1.2.0] - 2026-10-03

### Added
- **Resident Feedback & Bug Reporting System**:
  - Dedicated `/feedback <suggestion>` and `/bug <issue>` commands for residents to report inaccuracies, software bugs, or propose new features.
  - Multimodal bug screenshots supported: Residents can send photos with `/bug` or `/feedback` in the caption.
  - Autonomous Agent tool `submit_developer_feedback`: Gemini autonomously detects when a resident complains about an answer or requests a feature in natural chat, automatically filing it.
- **Native Swipe-to-Reply & Tap-to-Reply 2-Way Developer Communication**:
  - Admin receives real-time notification in private Telegram chat with resident metadata.
  - **Swipe-to-Reply:** Admin can swipe left on the notification card like a normal message, type the reply, and send.
  - **Tap-to-Reply:** Inline button `[ 💬 Reply ]` triggers Telegram `ForceReply` for 1-tap keyboard focus.
  - Bot relays developer messages directly into the resident's private chat.
  - Persistent message mapping (`admin_reply_mappings/` in Firestore) guarantees swipe-to-reply works even across serverless cold starts.
- **Feedback Analytics in `/admin_stats`**:
  - Tracks total feedback received and unresolved/new feedback count in Firestore.

---

## [1.1.0] - 2026-10-03

### Added
- **Multimodal Gemini Vision for Resident Photos**:
  - Residents can snap photos in chat (e.g. mall promo flyers, store opening hours, appliance error codes) instead of typing out lengthy descriptions.
  - Automatic intent classification into `TIP_SUBMISSION` (queues for admin moderation) vs `RESIDENT_QUESTION` (instant visual troubleshooting, e.g. induction hob 'L' child lock).
  - Automatic structured JSON extraction (`topic`, `title`, `tip`, `user_reply`) with strict PII scrubbing.
- **Photo-Enabled Admin Moderation Cards**:
  - Pushes the resident's photo directly to the Admin's private Telegram chat with interactive inline `[ ✅ Approve ]` and `[ ❌ Reject ]` buttons.
  - Dynamically edits the photo caption on approval/rejection to prevent duplicate admin actions.
- **Refined `/start` Onboarding Experience**:
  - Updated identity to **Lentor Modern Digital Concierge**.
  - Restructured onboarding prompts to highlight realistic resident scenarios: Renovations, Residential Loading Bay access, Mall Directory, Gym/BBQ facility booking, MA defect reporting, and Photo Assistance.
- **Database Schema Extension**:
  - Extended Firestore `community_tips/` documents with `has_image` (boolean) and `image_summary` (string) metadata.

---

## [1.0.0] - 2026-10-03

### Added
- **24/7 Serverless Cloud Run Deployment**: Deployed the production bot to Google Cloud Run in Singapore (`asia-southeast1`) with automatic scaling to 0 instances when idle ($0.00/month fixed infrastructure cost).
- **Gemini 3.8 Flash Autonomous Agent**: Upgraded agent reasoning core to Gemini 3.8 Flash with native Automatic Function Calling (AFC) via the modern `google-genai` SDK.
- **Resilient Model Cascade**: Implemented an automated fallback cascade (`gemini-3.8-flash` $\rightarrow$ `gemini-3.5-flash` $\rightarrow$ `gemini-3.1-flash-lite`) to bypass transient 503 high-demand spikes with 100% uptime for residents.
- **5 Specialized Estate Tools**:
  - `search_bylaws_and_handbook`: Searches official MCST by-laws, renovation hours & deposit schedules, moving procedures, facility rules, and handover defect protocols.
  - `search_mall_directory`: Looks up Lentor Modern Mall shops (CS Fresh, medical clinics, childcare, F&B), floor levels (B1, L1), unit numbers, and operating hours.
  - `get_verified_community_tips`: Retrieves crowdsourced neighbour advice (Taobao delivery bay access, induction cooker lock quirks, aircon copper piping SWG requirements, evening grocery discounts).
  - `generate_mcst_email_draft`: Formats structured, formal inquiries/tickets ready to send to the Managing Agent.
  - `submit_tip_to_moderation`: Automatically pushes resident-submitted tips to the Firestore moderation queue.
- **Google Cloud Firestore Database Layer**: Integrated serverless NoSQL storage following strict $O(1)$ single-document access patterns to prevent query bloat and bill explosions (`users/`, `query_logs/`, `community_tips/`).
- **In-Chat Admin Moderation**: When residents submit community tips via `/tip`, the bot pings the administrator's private Telegram chat with interactive inline `[ ✅ Approve ]` and `[ ❌ Reject ]` buttons.
- **Estate Broadcast Engine (`/broadcast`)**: Broadcasts announcements to registered households with Telegram rate-limiting (25 msgs/sec).
- **Product Analytics & Content Gap Detection (`/admin_stats`)**: Reports total registered households, query counts, and unanswered queries to highlight missing bylaws or untracked mall tenants.
- **Automated Artifact Registry Storage Protection**: Configured automated lifecycle cleanup policy (`scripts/cleanup-policy.json`) retaining only the 2 most recent container versions, guaranteeing permanent compliance within Google's 500 MB Free Tier limit.
- **Strict Singapore PII Scrubber**: Built `src/parser.py` with regex and heuristic cleaners that redact Singapore unit numbers (`#XX-YY`), local phone numbers (`+65...`), emails, and personal Telegram handles before data reaches knowledge stores.
