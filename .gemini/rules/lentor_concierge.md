# Lentor Modern AI Concierge Instructions

You are helping James (a Senior Product Manager) build the **Lentor Modern AI Concierge & Resident Knowledge Base**.

## Crucial Context:
1. Refer to `PROJECT_BRIEF.md` for full background, architecture, and PM decisions.
2. We are building a full **AI Agent** (autonomous tool calling, not a rigid single-prompt RAG workflow).
3. The tech stack reuses James's proven infrastructure from the Macro Tracker:
   - **Gemini 2.5 Flash** with native Tool/Function calling.
   - **Google Cloud Firestore** (users, analytics/query logs, community tips moderation queue).
   - **Google Cloud Run** (serverless Docker container, scales to 0).
   - **Telegram Bot API** (1-on-1 DM, inline keyboards, in-chat admin moderation, `/broadcast` engine).
4. Core Guardrails:
   - Mandatory PII scrubbing (strip unit numbers, phone numbers, personal names).
   - 1-on-1 DM bot distribution (not spamming the main group).
   - Human-in-the-loop review for community tips via Telegram interactive buttons.
5. Immediate Next Step:
   - Check `data/raw/` for exported Telegram `result.json` or condo PDFs, inspect the schema, and write `src/parser.py`.
