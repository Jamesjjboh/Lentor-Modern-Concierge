# Lentor Modern AI Concierge & Resident Knowledge Base

A community-driven, privacy-preserving AI assistant and living knowledge base for residents of Lentor Modern (Singapore).

## 🎯 Purpose & Scope
Lentor Modern is an integrated mixed-use development (605 residential units + retail mall + Lentor MRT). 
This project bridges the gap between:
1. **Official Estate Documents:** MCST by-laws, renovation guidelines, facility booking rules, handover defect protocols.
2. **Commercial / Public Hub:** Lentor Modern Mall directory (CS Fresh, F&B, childcare, clinics), MRT first/last train timings.
3. **Crowdsourced Tribal Knowledge:** Actionable tips, proven contractor advice, appliance quirks, and community consensus distilled from resident Telegram topics (with strict PII scrubbing and manual review).

---

## 📁 Directory Structure
- `data/`
  - `raw/`: Raw topic export JSONs and developer PDF handbooks (git-ignored for privacy).
  - `processed/`: Anonymized, cleaned, and distilled knowledge chunks.
- `src/`
  - `parser.py`: Telegram JSON cleaner, noise stripper, and PII anonymizer.
  - `distiller.py`: LLM prompt pipeline to extract structured FAQs and actionable tips.
  - `bot.py`: Telegram bot interface for 1-on-1 resident queries.
- `requirements.txt`: Python dependencies.

---

## 🚀 Getting Started
1. Export high-value topic history (JSON format, no media) from Telegram Desktop.
2. Place the exported `result.json` files and condo handbook PDFs inside `data/raw/`.
3. Run the processing and distillation pipeline.
