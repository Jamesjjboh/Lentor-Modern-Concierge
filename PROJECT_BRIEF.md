# Lentor Modern AI Concierge & Resident Knowledge Base — Blueprint

## 1. Product Vision & Value Proposition
- **Target Audience:** ~605 households at Lentor Modern (integrated mixed-use development by GuocoLand in Singapore, atop Lentor Modern Mall & Lentor MRT).
- **Core Friction:** 
  - Official MCST handbooks are 60-page unsearchable PDFs.
  - Concierge desk closes at 8:00 PM.
  - The resident Telegram forum repeats the same 15 questions every week (aircon ledge dimensions, fiber broadband riser keys, defect contractor tracking, delivery truck parking, mall shop hours).
  - Telegram's native search lacks semantic context.
- **Product Definition:** An **autonomous AI Agent** (not a static workflow) living in a 1-on-1 Telegram Bot, connected to Google Cloud Firestore, with dynamic tool calling, crowdsourced tip moderation, and admin broadcast capabilities.

---

## 2. Why an "AI Agent" (Toolbelt Architecture)
Instead of a rigid single-prompt RAG workflow, the agent autonomously selects and chains tools based on user intent:

### The Agent's Tool Catalog:
1. `search_bylaws_and_handbook(query)`: Queries official MCST by-laws, renovation rules, and facility deposit policies.
2. `search_mall_directory(category, shop_name)`: Looks up Lentor Modern Mall tenants, floor levels (`B1`, `L1`), and opening hours.
3. `get_verified_community_tips(topic)`: Retrieves verified tribal knowledge crowdsourced from neighbours.
4. `generate_mcst_email_draft(issue_type, details)`: Formats a professional, bylaw-referenced email/ticket ready to send to the Managing Agent.
5. `submit_tip_to_moderation(tip_text, topic)`: Automatically structures resident-submitted tips and pushes them to the Firestore moderation queue.

---

## 3. Reusable Infrastructure & Cloud Stack (From Macro Tracker)

| Component | Technology | Implementation Detail |
| :--- | :--- | :--- |
| **Agent Core** | Google Gemini 2.5 Flash | Fast, low latency, large context, native tool/function calling via `google-genai` SDK. |
| **Database** | Google Cloud Firestore | NoSQL document database storing users, logs, moderation queue, and verified knowledge. |
| **Hosting** | Google Cloud Run | Serverless Docker container. Scales to 0 when idle (\$0 cost), auto-scales with traffic spikes. |
| **User Interface** | Telegram Bot API | 1-on-1 DM bot (`python-telegram-bot` async). Webhook on Cloud Run, polling for local dev. |
| **Version Control** | Git & GitHub | Modular repo with `.gitignore` strictly blocking raw chat logs and credentials. |

---

## 4. Firestore Data Models

### `users/` Collection
- `user_id` (Telegram user ID - Document ID)
- `first_name`, `username`
- `first_seen`, `last_active`
- `total_queries` (integer)
- `opted_in_broadcasts` (boolean, default true)

### `query_logs/` Collection (Analytics & Content Gap Detection)
- `log_id` (auto ID)
- `user_id`
- `timestamp`
- `user_query`
- `tools_called` (array of tool names)
- `agent_response`
- `answered_successfully` (boolean — tracks content gaps when agent has to say "I don't know")
- `feedback` (thumbs up / down)

### `community_tips/` Collection (Moderation Queue)
- `tip_id` (auto ID)
- `topic` (e.g. `aircon`, `deliveries`, `mall`, `wifi`)
- `content` (string)
- `status` (`pending`, `approved`, `rejected`)
- `submitted_by_user_id`
- `submitted_at`, `reviewed_at`

---

## 5. Superpowers & Admin Features

### Superpower A: In-Chat Admin Moderation
- When a resident submits a tip via the bot, the agent triggers `submit_tip_to_moderation()`.
- The bot pings the **Admin's private Telegram chat** with an interactive alert:
  > 🔔 **New Resident Tip Submitted:**  
  > *Category:* Mall / Food  
  > *Tip:* "CS Fresh sushi 20% discount starts at 8:30 PM."  
  > `[ ✅ Approve ]` `[ ❌ Reject ]`
- Tapping `[Approve]` updates Firestore status to `approved`, making it instantly live for all 600 residents.

### Superpower B: Admin Broadcast Engine (`/broadcast`)
- Admin command: `/broadcast 📢 Lift maintenance for Tower 2 tomorrow from 10am-1pm.`
- Bot iterates through all registered users in Firestore with Telegram-compliant rate-limiting (max 30 msgs/sec).

### Superpower C: Built-in Product Analytics
- Admin command `/admin_stats` displays:
  - Total users & 7-day active users.
  - Top 5 search queries.
  - **Unanswered questions list** (shows James what new rules/mall shops need to be added).

---

## 6. Project Directory Layout
```text
Lentor Modern Concierge/
├── data/
│   ├── raw/            <-- Telegram topic export result.json & condo PDFs (git-ignored)
│   └── processed/      <-- Distilled, clean JSON knowledge chunks
├── src/
│   ├── agent.py        <-- Gemini 2.5 Agent core & Tool definitions
│   ├── bot.py          <-- Telegram bot handlers (1-on-1 DM, inline keyboards)
│   ├── parser.py       <-- Telegram JSON cleaner & PII scrubber
│   ├── database.py     <-- Firestore client & queries
│   └── admin.py        <-- Moderation callback handlers & broadcast engine
├── Dockerfile          <-- Cloud Run container spec
├── deploy.sh           <-- Cloud Run deployment script
├── requirements.txt    <-- Python dependencies
├── PROJECT_BRIEF.md    <-- This document
└── README.md           <-- Quickstart guide
```

---

## 7. Immediate Next Steps
1. User drops exported Telegram topic `result.json` and any condo PDFs into `data/raw/`.
2. Inspect raw data schemas.
3. Build `src/parser.py` (noise filtering & strict PII scrubbing: unit numbers, phone numbers, personal names).
4. Define the initial Tool functions in `src/agent.py`.
