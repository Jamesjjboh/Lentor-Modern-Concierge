"""Telegram JSON cleaner, PDF handbook extractor, and strict PII scrubber for Lentor Modern."""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from pypdf import PdfReader

from src.config import RAW_DATA_DIR, PROCESSED_DATA_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Regex patterns for Singapore PII ---
# 1. Singapore Condo Unit Numbers (e.g., #04-12, #21-105, # 12 - 08, Unit 12-04, etc.)
UNIT_PATTERN = re.compile(
    r"(?:(?:unit|#)\s*)?\b\d{1,2}\s*[-/]\s*\d{2,4}\b",
    re.IGNORECASE,
)

# 2. Singapore Phone Numbers (e.g., +65 9123 4567, 81234567, +6581234567)
PHONE_PATTERN = re.compile(
    r"(?:\+?65[\s-]?)?[89]\d{3}[\s-]?\d{4}\b"
)

# 3. Email Addresses
EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b"
)

# 4. Telegram @handles
HANDLE_PATTERN = re.compile(
    r"@[A-Za-z0-9_]{3,32}\b"
)

# Low-value noise filter (common conversational filler in Telegram condo groups)
NOISE_PHRASES = {
    "thanks", "thank you", "thx", "ty", "noted", "ok", "okay", "okie", "k",
    "received", "welcome", "you're welcome", "np", "no problem", "up", "bump",
    "+1", "agree", "pm sent", "pm-ed", "dm sent", "pls pm", "pls dm"
}


def scrub_pii(text: str) -> str:
    """Strictly redacts unit numbers, Singapore mobile numbers, emails, and TG handles."""
    if not text:
        return ""
    
    # Redact unit numbers
    text = UNIT_PATTERN.sub("[UNIT_REDACTED]", text)
    # Redact phone numbers
    text = PHONE_PATTERN.sub("[PHONE_REDACTED]", text)
    # Redact email addresses
    text = EMAIL_PATTERN.sub("[EMAIL_REDACTED]", text)
    # Redact handles
    text = HANDLE_PATTERN.sub("[USER_HANDLE]", text)
    
    # Clean redundant whitespaces
    text = re.sub(r"[ \t]+", " ", text).strip()
    return text


def extract_telegram_text(raw_text: Any) -> str:
    """Telegram exports format text as either a string or a list of mixed text/entity objects."""
    if isinstance(raw_text, str):
        return raw_text.strip()
    elif isinstance(raw_text, list):
        extracted = []
        for part in raw_text:
            if isinstance(part, str):
                extracted.append(part)
            elif isinstance(part, dict) and "text" in part:
                extracted.append(part["text"])
        return "".join(extracted).strip()
    return ""


def is_noise_message(text: str) -> bool:
    """Detects low-value chat noise to avoid polluting knowledge base."""
    cleaned = text.lower().strip()
    if not cleaned:
        return True
    if len(cleaned) < 8 and cleaned in NOISE_PHRASES:
        return True
    if cleaned in NOISE_PHRASES:
        return True
    # If the message is just punctuation/emojis and has no alphanumeric content
    if not re.search(r"\w{2,}", cleaned):
        return True
    return False


def parse_telegram_export(json_path: Path) -> List[Dict[str, Any]]:
    """Parses a Telegram desktop export (result.json), strips noise, and anonymizes PII."""
    logger.info(f"Parsing Telegram export from: {json_path}")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    messages = data.get("messages", [])
    cleaned_messages = []
    
    # Map raw user names/ids to anonymous identifiers (e.g. Resident_1, Resident_2)
    user_anonymizer: Dict[str, str] = {}
    anon_counter = 1

    for msg in messages:
        # Ignore service/system messages (joins, leaves, pin events)
        if msg.get("type") != "message":
            continue

        raw_text = msg.get("text", "")
        extracted_text = extract_telegram_text(raw_text)
        
        if is_noise_message(extracted_text):
            continue

        raw_sender = msg.get("from") or msg.get("from_id") or "Unknown"
        if raw_sender not in user_anonymizer:
            user_anonymizer[raw_sender] = f"Resident_{anon_counter}"
            anon_counter += 1
        
        anon_sender = user_anonymizer[raw_sender]
        sanitized_text = scrub_pii(extracted_text)

        cleaned_messages.append({
            "message_id": msg.get("id"),
            "date": msg.get("date"),
            "sender": anon_sender,
            "text": sanitized_text,
            "reply_to_message_id": msg.get("reply_to_message_id"),
        })

    logger.info(f"Parsed {len(messages)} raw messages -> {len(cleaned_messages)} cleaned messages.")
    return cleaned_messages


def parse_pdf_handbook(pdf_path: Path) -> List[Dict[str, Any]]:
    """Extracts text from an official MCST handbook PDF with page tracking and PII scrubbing."""
    logger.info(f"Parsing PDF handbook from: {pdf_path}")
    reader = PdfReader(str(pdf_path))
    chunks = []

    for page_num, page in enumerate(reader.pages, start=1):
        raw_text = page.extract_text() or ""
        # Clean hyphenation across line breaks: e.g. "con-\ntractor" -> "contractor"
        cleaned_text = re.sub(r"(\w+)-\n(\w+)", r"\1\2", raw_text)
        # Normalize line endings
        cleaned_text = re.sub(r"\n{2,}", "\n\n", cleaned_text)
        # Scrub any incidental PII
        sanitized_text = scrub_pii(cleaned_text)

        if len(sanitized_text.strip()) > 20:
            chunks.append({
                "source": pdf_path.name,
                "page": page_num,
                "text": sanitized_text.strip(),
            })

    logger.info(f"Extracted {len(chunks)} pages/chunks from {pdf_path.name}.")
    return chunks


def process_all_raw_data(
    raw_dir: Path = RAW_DATA_DIR, 
    processed_dir: Path = PROCESSED_DATA_DIR
) -> Dict[str, int]:
    """Scans raw_dir for JSON and PDF files, parses, scrubs PII, and outputs to processed_dir."""
    processed_dir.mkdir(parents=True, exist_ok=True)
    stats = {"tg_messages": 0, "pdf_pages": 0}

    # 1. Process Telegram exports
    for json_file in raw_dir.glob("*.json"):
        if json_file.name == ".gitkeep":
            continue
        cleaned = parse_telegram_export(json_file)
        if cleaned:
            out_file = processed_dir / f"cleaned_{json_file.stem}.json"
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(cleaned, f, indent=2, ensure_ascii=False)
            stats["tg_messages"] += len(cleaned)

    # 2. Process Handbook PDFs
    pdf_chunks = []
    for pdf_file in raw_dir.glob("*.pdf"):
        chunks = parse_pdf_handbook(pdf_file)
        pdf_chunks.extend(chunks)

    if pdf_chunks:
        out_file = processed_dir / "bylaws_handbook.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(pdf_chunks, f, indent=2, ensure_ascii=False)
        stats["pdf_pages"] += len(pdf_chunks)

    return stats


if __name__ == "__main__":
    results = process_all_raw_data()
    print(f"Data processing finished: {results}")
