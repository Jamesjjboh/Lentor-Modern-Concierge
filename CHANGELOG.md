# Changelog

All notable changes to the **Lentor Modern Digital Concierge** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
