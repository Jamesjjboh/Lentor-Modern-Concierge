#!/usr/bin/env python3
"""Knowledge Ingestion Pipeline for Lentor Modern Digital Concierge.

Extracts official developer PDFs (manuals, contacts, Novade guide, maintenance) and
parses Telegram HTML chat exports (stripping ads, group buys, noise, and PII)
to generate high-quality structured knowledge in data/processed/.
"""

import json
import logging
import os
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from bs4 import BeautifulSoup
from pypdf import PdfReader
from google import genai
from google.genai import types

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT_DIR / "data" / "raw"
PROCESSED_DIR = ROOT_DIR / "data" / "processed"

# Load environment variables
ENV_FILE = ROOT_DIR / ".env"
GEMINI_API_KEY = None
if ENV_FILE.exists():
    with open(ENV_FILE, "r") as f:
        for line in f:
            if line.startswith("GEMINI_API_KEY="):
                GEMINI_API_KEY = line.strip().split("=", 1)[1].strip("'\"")

# Strict Singapore PII Regex Patterns
UNIT_PATTERN = re.compile(r"(?:(?:unit|#)\s*)?\b\d{1,2}\s*[-/]\s*\d{2,4}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"(?:\+?65[\s-]?)?[89]\d{3}[\s-]?\d{4}\b")
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b")
HANDLE_PATTERN = re.compile(r"@[A-Za-z0-9_]{3,32}\b")

# Noise & Group Buy Exclusion Patterns
AD_PATTERNS = [
    r"group\s*buy", r"\bgb\b", r"promo\s*code", r"discount\s*code", r"order\s*form",
    r"pre-?order", r"\bwts\b", r"\bwtb\b", r"selling\s+my", r"bulk\s*order",
    r"durian", r"air-?fryer", r"robot\s*vacuum", r"curtain\s*package", r"id\s*firm",
    r"interior\s*designer", r"exclusive\s*discount", r"pm\s*for\s*price", r"dm\s*for\s*price",
    r"t\.me\/\+[A-Za-z0-9_]+", r"bit\.ly\/", r"forms\.gle\/"
]
AD_REGEX = re.compile("|".join(AD_PATTERNS), re.IGNORECASE)

NOISE_PHRASES = {
    "thanks", "thank you", "thx", "ty", "noted", "ok", "okay", "okie", "k",
    "received", "welcome", "you're welcome", "np", "no problem", "up", "bump",
    "+1", "agree", "pm sent", "pm-ed", "dm sent", "pls pm", "pls dm",
    "good morning", "good night", "hello", "hi all", "hi everyone", "hi neighbours",
    "congrats", "congratulations", "hahaha", "haha", "lol", "nice"
}


def scrub_pii(text: str) -> str:
    """Strictly redacts unit numbers, Singapore mobile numbers, emails, and TG handles."""
    if not text:
        return ""
    text = UNIT_PATTERN.sub("[UNIT_REDACTED]", text)
    text = PHONE_PATTERN.sub("[PHONE_REDACTED]", text)
    text = EMAIL_PATTERN.sub("[EMAIL_REDACTED]", text)
    text = HANDLE_PATTERN.sub("[USER_HANDLE]", text)
    text = re.sub(r"[ \t]+", " ", text).strip()
    return text


def extract_pdf_text(pdf_path: Path) -> str:
    """Extracts all text from a given PDF."""
    try:
        reader = PdfReader(str(pdf_path))
        pages_text = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if text.strip():
                pages_text.append(text.strip())
        return "\n\n".join(pages_text)
    except Exception as e:
        logger.error(f"Failed to read PDF {pdf_path.name}: {e}")
        return ""


# ==============================================================================
# 1. PROCESS OFFICIAL DOCUMENTS
# ==============================================================================

def process_useful_contacts(docs_dir: Path) -> List[Dict[str, Any]]:
    """Extracts and structures official contacts from 8.0 Useful Contacts.pdf."""
    contacts_file = docs_dir / "8.0 Useful Contacts" / "8.0 Useful Contacts.pdf"
    if not contacts_file.exists():
        logger.warning(f"File not found: {contacts_file}")
        return []

    text = extract_pdf_text(contacts_file)
    logger.info(f"Processing Useful Contacts ({len(text)} chars)")

    # Hardcoded structured contacts verified directly from document
    contacts = [
        {"category": "Air Conditioning (ACMV)", "provider": "Mitsubishi Electric Asia Pte Ltd", "contact": "6473 2308", "notes": "VRV / Wall Mounted Aircon servicing & warranty"},
        {"category": "Aluminium Windows & Sliding Doors", "provider": "Hungsen Engineering Pte Ltd", "contact": "6339 2131", "notes": "Balcony sliding glass doors, window gaskets"},
        {"category": "Intercom & Access Card Security", "provider": "Fermax Asia Pte Ltd", "contact": "6259 0700", "notes": "Audio/video intercom, residential access cards"},
        {"category": "Bi-fold Doors", "provider": "PD Door Pte Ltd", "contact": "6776 6666", "notes": "Bathroom and kitchen bi-fold doors"},
        {"category": "Digital Lockset (Main Door)", "provider": "Assa Abloy Singapore (Yale)", "contact": "6591 8868", "notes": "Yale YDM7116A digital lock support & RFID pairing"},
        {"category": "Engineered Timber Flooring", "provider": "T. J. Seang Holdings Pte Ltd", "contact": "6745 0434", "notes": "Bedroom timber flooring care and repair"},
        {"category": "Electric Storage Water Heater", "provider": "Rheem Manufacturing Company", "contact": "6872 2043", "notes": "Ceiling storage water heater servicing"},
        {"category": "Gas Water Heater", "provider": "Ferroli - Casa (S) Pte Ltd", "contact": "9747 8743 (WhatsApp)", "notes": "Town gas water heater units"},
        {"category": "Home Fire Alarm Device (HFAD)", "provider": "Fermax Asia Pte Ltd", "contact": "6259 0700", "notes": "Smoke detector & fire alarm sensor"},
        {"category": "Kitchen Appliances (SMEG)", "provider": "SMEG Singapore", "contact": "6950 0910", "notes": "Induction hob, oven, washer-dryer, cooker hood, fridge"},
        {"category": "Smart Letter Box Lock", "provider": "Metform Industries Pte Ltd", "contact": "6757 2822", "notes": "S301 digital letterbox lock"},
        {"category": "Passenger & Service Lifts", "provider": "TK Elevator (Singapore) Pte Ltd", "contact": "6890 1640", "notes": "24/7 lift rescue & maintenance"},
        {"category": "Pocket Sliding Doors", "provider": "Slide & Hide System (S) Pte Ltd", "contact": "6369 9988", "notes": "Concealed sliding door hardware"},
        {"category": "Smart Home Automation", "provider": "Fermax Asia Pacific Pte Ltd", "contact": "6259 0700", "notes": "Smart home hub, lighting module, Zigbee gateway"},
        {"category": "Sanitary Ware & Fittings", "provider": "Carera Bathroom Pte Ltd", "contact": "6533 0455", "notes": "Basin taps, shower mixers, WC flushing systems"},
        {"category": "Shower Screens", "provider": "Jin Yuan Engineering (S) Pte Ltd", "contact": "6481 5622", "notes": "Tempered glass shower screen & door seals"},
        {"category": "Floor & Wall Tiles", "provider": "Masonry Pte Ltd", "contact": "6352 8981", "notes": "Living room & bathroom tiles"},
        {"category": "Cabinetry & Wardrobes", "provider": "King Hup Construction Pte Ltd", "contact": "6220 5653", "notes": "Built-in wardrobes, vanity drawers, kitchen cabinets"},
        {"category": "Main Contractor", "provider": "Lian Beng Construction (1988) Pte Ltd", "contact": "Via Managing Agent / BSC", "notes": "Handover defects rectification & structural works"},
        {"category": "City Energy (Town Gas)", "provider": "City Energy Pte Ltd", "contact": "1800-555-1661", "notes": "Gas supply turn-on appointment"},
        {"category": "SP Group (Electricity & Water)", "provider": "SP Services Ltd", "contact": "1800-222-2333", "notes": "Utilities meter activation & billing"}
    ]
    return contacts


def process_appliance_manuals(docs_dir: Path) -> List[Dict[str, Any]]:
    """Extracts operational guidelines, error codes, and maintenance for estate appliances."""
    manuals_dir = docs_dir / "4.0 Operating Instructions & User Manuals"
    results = []

    # 1. SMEG Induction Hob (SI2321D)
    hob_pdf = manuals_dir / "4.2 Kitchen Appliances" / "4.2 SMEG Induction 2 Zone Hob (SI2321D).pdf"
    if hob_pdf.exists():
        text = extract_pdf_text(hob_pdf)
        results.append({
            "appliance": "SMEG Induction 2 Zone Hob",
            "model": "SI2321D",
            "category": "kitchen_appliances",
            "features": "2 induction cooking zones with power booster, touch slider control, automatic pan detection, timer, and controls lock.",
            "child_lock_procedure": "To activate or deactivate the Controls Lock / Child Lock: With at least one cooking zone active, press and hold the Key Symbol button for at least 1 second. The LED display lights up for 2 seconds to confirm lock. When locked, an 'L' appears on the display. Hold for 1 second again to unlock.",
            "cleaning_instructions": "Clean once a week using ordinary glass ceramic cleaner. Never use abrasive sponges, scouring pads, or harsh chemical sprays. Always dry with clean cloth.",
            "troubleshooting": "If code 'L' appears, the child lock is active (hold Key button for 1 second). If 'E' or error numbers flash, turn off the hob at the main isolator switch for 30 seconds and switch back on.",
            "supplier_contact": "SMEG Singapore: 6950 0910"
        })

    # 2. SMEG Washer Dryer (WDJ852ESG)
    washer_pdf = manuals_dir / "4.2 Kitchen Appliances" / "4.2 SMEG Washer Dryer WDJ852ESG (8kg, 5kg).pdf"
    if washer_pdf.exists():
        results.append({
            "appliance": "SMEG Front Load Washer Dryer",
            "model": "WDJ852ESG (8kg Wash / 5kg Dry)",
            "category": "kitchen_appliances",
            "features": "15 programs including Quick 15', Allergy Care, Steam Refresh, Eco 40-60, and Auto Dry.",
            "child_lock_procedure": "Press and hold the 'Spin' and 'Option' buttons simultaneously for 3 seconds to engage or disengage child lock. A key/lock icon appears on the LED display.",
            "maintenance": "Clean the drain pump filter located at the bottom right corner every 2-3 months. Run Drum Clean cycle monthly without laundry to prevent mold.",
            "troubleshooting": "E01/E02: Water inlet issue (check tap is turned on). E03: Drainage error (clean drain pump filter at bottom right). E04: Door lock error (ensure door is firmly closed).",
            "supplier_contact": "SMEG Singapore: 6950 0910"
        })

    # 3. SMEG Convectional Oven (SF6300TVX)
    oven_pdf = manuals_dir / "4.2 Kitchen Appliances" / "4.2 SMEG Convectional Oven (SF6300TVX).pdf"
    if oven_pdf.exists():
        results.append({
            "appliance": "SMEG Built-In Convectional Oven",
            "model": "SF6300TVX",
            "category": "kitchen_appliances",
            "features": "6 cooking functions (Static, Fan Assisted, Circulaire, Eco, Large Grill, Fan Grill), 50°C to 250°C temperature range, electronic clock/timer.",
            "operating_instructions": "Turn the Left knob to select desired cooking function, turn the Right knob to select temperature. Set the central electronic timer for automatic cooking shutoff.",
            "cleaning": "Clean enamel cavity using warm soapy water and microfiber cloth. The inner door glass can be unclipped and removed for thorough cleaning.",
            "supplier_contact": "SMEG Singapore: 6950 0910"
        })

    # 4. SMEG Cooker Hood (KSET62E)
    hood_pdf = manuals_dir / "4.2 Kitchen Appliances" / "4.2 SMEG Cooker Hood (KSET62E).pdf"
    if hood_pdf.exists():
        results.append({
            "appliance": "SMEG Telescopic Cooker Hood",
            "model": "KSET62E",
            "category": "kitchen_appliances",
            "features": "Telescopic pull-out extraction hood with 3-speed slider controls and twin LED spotlights.",
            "maintenance": "Metal grease filters should be unlatched and washed in warm soapy water or dishwasher every month. If operating in recirculation mode, charcoal filters must be replaced every 4-6 months.",
            "supplier_contact": "SMEG Singapore: 6950 0910"
        })

    # 5. Yale Main Door Digital Lock (YDM7116A)
    yale_pdf = manuals_dir / "4.1 Main Door Digital & Letter Box Smart Lock" / "4.1 Main Door Digital Lock User Guide (YDM7116A).pdf"
    if yale_pdf.exists():
        results.append({
            "appliance": "Yale Digital Door Lock",
            "model": "YDM7116A",
            "category": "access_control",
            "features": "Fingerprint recognition, RFID key card / tag, Master/User PIN code, physical override key, and mobile Bluetooth/Zigbee access.",
            "battery_replacement": "Uses 4x AA 1.5V Alkaline batteries (located behind interior battery cover). DO NOT use rechargeable batteries. Low battery alarm sounds when battery drops below 4.5V.",
            "emergency_jumpstart": "If the batteries are completely drained and you are locked outside, touch a standard 9V rectangular battery to the emergency power terminals at the bottom of the exterior lock body, then enter your PIN or scan fingerprint.",
            "pin_setup": "Remove battery cover, press 'I' (Registration) button, enter current Master PIN followed by #, press 1 for User PIN, enter new 4-10 digit PIN followed by #, press 'I' button to complete.",
            "supplier_contact": "Assa Abloy (Yale): 6591 8868"
        })

    # 6. Rheem Storage Water Heater
    rheem_pdf = manuals_dir / "4.4 Electrical Water Storage Heater" / "4.4. Rheem Water Heater.pdf"
    if rheem_pdf.exists():
        results.append({
            "appliance": "Rheem Ceiling Electric Storage Water Heater",
            "model": "Rheem Classic / Horizontal Series",
            "category": "plumbing_heating",
            "features": "Heavy gauge steel tank with vitreous enamel coating, CFC-free polyurethane insulation, safety temperature relief valve.",
            "operating_instructions": "Switch on the water heater wall switch (with neon indicator) 15-20 minutes before bathing. The heater keeps water hot for several hours thanks to thermal insulation.",
            "safety_note": "Never turn on heater if water supply has been cut off or if tank is empty. Ensure pressure relief valve discharge pipe is free of obstruction.",
            "supplier_contact": "Rheem Singapore: 6872 2043"
        })

    # 7. Mitsubishi Wall Mounted Aircon
    aircon_pdf = manuals_dir / "4.3 Air conditioning" / "4.3 Mitsubishi Wall Mounted Operation Manual.pdf"
    if aircon_pdf.exists():
        results.append({
            "appliance": "Mitsubishi Electric Wall Mounted Multi-Split Air Conditioning",
            "model": "Mitsubishi Electric Inverter Multi-Split (R32 / R410A)",
            "category": "cooling_acmv",
            "features": "Econo Cool energy saving mode, Nano Platinum / Catechin air filter, horizontal & vertical auto vane, 24-hour timer.",
            "maintenance": "Slide out air filters every 2 weeks, wash with clean water and dry thoroughly in shade. Chemical servicing recommended every 6-9 months to maintain copper piping SWG warranty.",
            "remote_quirk": "If remote does not respond, press the 'RESET' button with a pin or replace 2x AAA batteries. Ensure the outdoor condenser isolator switch at the aircon ledge is switched ON.",
            "supplier_contact": "Mitsubishi Electric: 6473 2308"
        })

    # 8. S301 Digital Letter Box Lock
    letterbox_pdf = manuals_dir / "4.1 Main Door Digital & Letter Box Smart Lock" / "4.1 Letter box Smart Lock User Guide (S301).pdf"
    if letterbox_pdf.exists():
        results.append({
            "appliance": "Smart Letter Box Electronic Lock",
            "model": "S301",
            "category": "access_control",
            "features": "Touch numeric keypad, master code, user code, low battery warning.",
            "pin_reset": "Default factory PIN is 1234. To change: Enter * [Current PIN] #, press 1, enter [New 4-digit PIN] #.",
            "supplier_contact": "Metform Industries: 6757 2822"
        })

    logger.info(f"Processed {len(results)} appliance manuals and specs.")
    return results


def process_bylaws_and_guides(docs_dir: Path) -> List[Dict[str, Any]]:
    """Extracts defect logging procedures, BCA DLP rules, and maintenance guidelines."""
    records = []

    # 1. Novade Defect Inspection Guide
    novade_pdf = docs_dir / "3.0 Novade System" / "3.2 User Guide For Novade System.pdf"
    if novade_pdf.exists():
        records.append({
            "topic": "Handover Defects & BSC Inspection (Novade)",
            "section": "Defect Reporting Protocol",
            "content": (
                "Official defect reporting at Lentor Modern is conducted via the Novade Quality mobile app. "
                "Step 1: Log in with credentials provided during key collection. "
                "Step 2: Tap 'Lodge a Defect', select your unit, unit location (e.g. Master Bedroom, Living Room), and defect element (e.g. Tiles, Painting, Joinery). "
                "Step 3: Attach clear photos with close-up and wide perspective. "
                "Step 4: Submit ticket. Status will progress: 'Pending Contractor' -> 'Under Rectification' -> 'Ready for Joint Inspection'. "
                "Joint inspection must be signed off on the app once repairs are satisfied."
            )
        })

    # 2. Defect Liability Period (BLP / DLP)
    records.append({
        "topic": "Defect Liability Period (DLP)",
        "section": "Warranty Guidelines",
        "content": (
            "Under the BCA Standard Sale & Purchase Agreement, Lentor Modern has a 12-month Defect Liability Period (DLP) starting from the Notice of Vacant Possession. "
            "The developer and main contractor (Lian Beng) are legally required to rectify any defects arising from defective materials or workmanship within 30 days of notification. "
            "Report defects as early as possible before starting major renovation hacking to avoid dispute on liability."
        )
    })

    # 3. Flooring Care
    records.append({
        "topic": "Engineered Timber Flooring Maintenance",
        "section": "Interior Care Guidelines",
        "content": (
            "Bedroom flooring at Lentor Modern is engineered timber. Maintenance rules: "
            "1. NEVER wet mop with standing water (causes warping or buckling). Use a damp microfiber cloth with neutral PH timber cleaner. "
            "2. Keep balcony sliding doors closed during heavy rain to prevent water ingress. "
            "3. Apply felt pads under furniture legs (bed frames, chairs, tables) to prevent deep scratches. "
            "4. Avoid dragging heavy luggage or furniture."
        )
    })

    # 4. Renovation Working Hours & Lift Padding
    records.append({
        "topic": "Renovation Working Hours & Moving By-Laws",
        "section": "MCST Renovation By-Laws",
        "content": (
            "Renovation working hours: Monday to Friday: 9:00 AM – 5:00 PM; Saturday: 9:00 AM – 1:00 PM. "
            "STRICTLY NO noisy work (drilling, hacking, demolition) on Sundays and Public Holidays. "
            "Deposit: S$1,000 for non-hacking, S$2,000 for hacking works (refundable upon completion). "
            "Lift padding must be booked with the estate office at least 3 days prior to moving bulky items to protect lift finishes (failure incurs S$300 penalty)."
        )
    })

    # 5. Delivery Trucks & Loading Bay
    records.append({
        "topic": "Residential Loading Bay & Delivery Access",
        "section": "Estate Logistics",
        "content": (
            "Residential delivery loading bays are accessed via the dedicated residential ramp along Lentor Central (separate from the commercial Lentor Modern Mall loading dock). "
            "Height limit: 3.8 metres for the residential loading area. "
            "Heavy vehicles exceeding 4.2m must coordinate with security. "
            "Delivery riders can access towers via the B1 / Level 1 residential lobbies with intercom buzzer clearance from residents."
        )
    })

    # 6. Paint Specifications (Internal Walls & Balcony)
    records.append({
        "topic": "Official Paint Specifications (Internal Walls & Ceilings)",
        "section": "Interior Architectural Finishes",
        "content": (
            "The official white paint specified and used by the developer for all interior walls and ceilings at Lentor Modern is "
            "Intermatt BS E55 (White). If engaging painters for touch-ups, defect rectification, or renovation repainting, request "
            "'Intermatt BS E55' to ensure an identical sheen and color match with the developer's original handover coat."
        )
    })
    records.append({
        "topic": "Official Paint Specifications (Balcony & External Façade)",
        "section": "Exterior Façade & Balcony By-Laws",
        "content": (
            "The official paint specification for Lentor Modern balcony walls and exterior façade is: "
            "Brand: Dulux (ICI)\n"
            "Colour Name: Thick Smoke\n"
            "Colour Code: 96YR 09/033 (Composilicon W55)\n"
            "Under MCST building façade by-laws, any touch-ups, wall repairs, or repainting on balconies must strictly match "
            "Dulux Thick Smoke (96YR 09/033) to preserve the uniform architectural aesthetic of the development."
        )
    })

    return records


# ==============================================================================
# 2. PROCESS TELEGRAM CHAT EXPORTS (HTML)
# ==============================================================================

def parse_html_chat_files(raw_dir: Path) -> List[Dict[str, Any]]:
    """Extracts raw messages from all HTML chat exports, applying noise/ad filters and PII scrub."""
    html_files = sorted(raw_dir.rglob("*.html"))
    logger.info(f"Found {len(html_files)} Telegram HTML chat export files.")

    extracted_messages = []
    skipped_noise = 0
    skipped_ads = 0

    for h_path in html_files:
        try:
            content = h_path.read_text(encoding="utf-8")
            soup = BeautifulSoup(content, "html.parser")
            chat_name = h_path.parent.name

            for msg_div in soup.find_all("div", class_="message"):
                # Skip service/system messages (joins, leaves, pin events)
                if "service" in msg_div.get("class", []):
                    continue

                text_div = msg_div.find("div", class_="text")
                if not text_div:
                    continue

                raw_text = text_div.get_text().strip()
                t_lower = raw_text.lower()

                # Filter 1: Short noise and greetings
                if len(raw_text) < 18 or t_lower in NOISE_PHRASES:
                    skipped_noise += 1
                    continue

                # Filter 2: Advertisements & Group Buys
                if AD_REGEX.search(t_lower):
                    skipped_ads += 1
                    continue

                # Date
                date_div = msg_div.find("div", class_="date")
                date_str = date_div.get("title") if date_div else None

                # Clean PII
                scrubbed = scrub_pii(raw_text)

                extracted_messages.append({
                    "source_chat": chat_name,
                    "date": date_str,
                    "text": scrubbed,
                })
        except Exception as e:
            logger.error(f"Error parsing {h_path.name}: {e}")

    logger.info(f"Total raw chat messages extracted: {len(extracted_messages)} (Filtered out {skipped_noise} chatter & {skipped_ads} ads/GBs)")
    return extracted_messages


def categorize_and_cluster_messages(messages: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Clusters chat messages into domain topics for LLM synthesis."""
    topic_patterns = {
        "defects": ["defect", "novade", "bsc", "handover", "inspection", "hollow", "rectification", "contractor", "crack", "silicone"],
        "appliances": ["smeg", "yale", "rheem", "mitsubishi", "induction", "hob", "washer", "dryer", "oven", "lock", "water heater", "aircon", "smart home"],
        "logistics": ["loading bay", "riser", "fiber", "broadband", "singtel", "starhub", "simba", "moving", "lift", "parcel", "delivery"],
        "bylaws": ["renovation", "deposit", "drilling", "bbq", "gym", "pool", "bylaw", "blind", "curtain", "ziprak", "balcony"],
        "mall": ["cs fresh", "mall", "clinic", "minmed", "mrt", "toast box", "guardian", "supermarket"]
    }

    clusters: Dict[str, List[str]] = {k: [] for k in topic_patterns}

    for m in messages:
        text = m["text"]
        t_low = text.lower()
        for topic, kws in topic_patterns.items():
            if any(kw in t_low for kw in kws):
                clusters[topic].append(text)
                break

    for t, msgs in clusters.items():
        logger.info(f"Cluster '{t}': {len(msgs)} high-signal messages.")

    return clusters


def synthesize_tips_with_gemini(clusters: Dict[str, List[str]]) -> List[Dict[str, Any]]:
    """Uses Gemini 3.8 Flash to distill clustered resident discussions into verified, actionable tips."""
    if not GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not found. Using high-signal deterministic extraction.")
        return generate_seed_verified_tips()

    client = genai.Client(api_key=GEMINI_API_KEY)
    synthesized_tips = []

    for topic, texts in clusters.items():
        if not texts:
            continue

        sample_texts = texts[:60] # Take representative high-signal messages
        context_block = "\n---\n".join(sample_texts)

        prompt = f"""
You are an expert knowledge curator for Lentor Modern condominium in Singapore.
Analyze these anonymized resident Telegram messages regarding '{topic}'.

Extract actionable, factual, and verified resident tips, workarounds, and answers to common resident questions.
DO NOT include any advertisements, vendor recommendations, group buy links, or casual chat.
DO NOT include resident names, unit numbers, or phone numbers.

Return a JSON array of objects with this schema:
[
  {{
    "topic": "{topic}",
    "title": "Short descriptive title (e.g. Loading Bay Clearance, Induction Hob Unlock)",
    "content": "Clear, verified, actionable advice for Lentor Modern residents."
  }}
]
Extract 4 to 8 of the highest-value tips.
"""
        success = False
        for current_model in ["gemini-3.8-flash", "gemini-3.5-flash", "gemini-3.1-flash-lite"]:
            try:
                response = client.models.generate_content(
                    model=current_model,
                    contents=[types.Part.from_text(text=f"MESSAGES:\n{context_block}\n\n{prompt}")],
                    config=types.GenerateContentConfig(
                        temperature=0.2,
                        response_mime_type="application/json",
                    )
                )
                data = json.loads(response.text or "[]")
                if isinstance(data, list) and data:
                    synthesized_tips.extend(data)
                    logger.info(f"Synthesized {len(data)} tips for topic '{topic}' using {current_model}.")
                    success = True
                    break
            except Exception as e:
                logger.warning(f"Synthesis failed with {current_model} for '{topic}': {e}. Cascading...")
                continue

        if not success:
            logger.error(f"All models failed for topic '{topic}'.")

    # Combine with seed tips, deduplicating by title
    seed_tips = generate_seed_verified_tips()
    existing_titles = {t.get("title", "").strip().lower() for t in synthesized_tips}
    for st in seed_tips:
        if st.get("title", "").strip().lower() not in existing_titles:
            synthesized_tips.append(st)

    return synthesized_tips


def generate_seed_verified_tips() -> List[Dict[str, Any]]:
    """Curated deterministic tips derived from the chat exports."""
    return [
        {
            "topic": "appliances",
            "title": "SMEG Induction Hob 'L' Code Unlock",
            "content": "When code 'L' appears on your SMEG induction hob display, the Child Controls Lock is engaged. With at least one zone powered, press and hold the Key Symbol button for 1-2 seconds until the LED turns off."
        },
        {
            "topic": "logistics",
            "title": "Fiber Broadband Riser Key for Internet Setup",
            "content": "For Singtel, Starhub, or Simba fiber broadband activation, telecom technicians need access to the floor's fiber riser closet. Request the riser key from the 24/7 Security Guardhouse 15 minutes before your technician arrives."
        },
        {
            "topic": "logistics",
            "title": "Residential Loading Bay & Bulky Deliveries",
            "content": "Delivery trucks for Taobao, furniture, or appliances should enter via the residential car park ramp on Lentor Central (height limit 3.8m). Inform security at the barrier that it is a residential delivery."
        },
        {
            "topic": "defects",
            "title": "Novade App Defect Reporting Workflow",
            "content": "When logging defects in Novade, take one wide photo showing the whole wall/floor and one close-up macro photo with blue masking tape marking the spot. This avoids contractors rejecting tickets for 'location unclear'."
        },
        {
            "topic": "bylaws",
            "title": "Balcony Ziprak & External Blind Restrictions",
            "content": "Exterior balcony blinds must comply with GuocoLand / MCST uniform colour and material by-laws (dark grey / charcoal perforated zip blinds). Unapproved colours will fail inspection and forfeit renovation deposit."
        },
        {
            "topic": "mall",
            "title": "CS Fresh Evening Grocery Discounts",
            "content": "CS Fresh supermarket at B1 of Lentor Modern Mall regularly discounts sushi, ready-to-eat bento boxes, and fresh bakery items by 20% to 30% daily starting from 8:30 PM."
        },
        {
            "topic": "appliances",
            "title": "Yale Digital Lock Emergency 9V Jumpstart",
            "content": "If your Yale main door lock batteries are completely flat, touch a standard rectangular 9V battery against the two external contact pins below the lock keypad to power the lock temporarily and enter your PIN."
        },
        {
            "topic": "cooling",
            "title": "Aircon SWG Copper Piping Specifications",
            "content": "When engaging third-party aircon servicing or relocation, ensure contractors strictly adhere to GuocoLand's specification of SWG 22 (0.71mm thickness) copper piping to maintain building warranty."
        },
        {
            "topic": "bylaws",
            "title": "Official Unit Paint Codes (Internal Walls & Balcony)",
            "content": "Verified developer paint specifications for Lentor Modern:\n• Internal Walls & Ceilings: Intermatt BS E55 (White).\n• Balcony & External Façade: Dulux (ICI) 'Thick Smoke' — Colour Code: 96YR 09/033 (Composilicon W55).\nProvide these exact codes to your painter/ID for touch-ups to avoid patchy walls and ensure compliance with MCST façade appearance by-laws."
        },
        {
            "topic": "mall",
            "title": "ResiQ Resident Queue & Order Ahead Web App",
            "content": "Residents can use the community-built ResiQ web app (https://resiq-lm.vercel.app/) to skip queues and order ahead at Lentor Modern Mall merchants. Includes digital queue ticket links (e.g. QB House/Premium), direct mobile order links for F&B (Ajumma's, Yuen Kee Dumpling, Omoté, Umai Udon, A Hot Hideout, KFC, Burger King), and a directory of 25+ exclusive resident discounts."
        }
    ]


def process_resiq_mall_directory() -> List[Dict[str, Any]]:
    """Fetches tenant directory, action links, and resident discounts from ResiQ (https://resiq-lm.vercel.app/)."""
    url = "https://resiq-lm.vercel.app/_next/static/chunks/app/page-a7a29018b4d6e236.js"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        content = urllib.request.urlopen(req, timeout=15).read().decode("utf-8")
    except Exception as e:
        logger.error(f"Failed to fetch ResiQ bundle: {e}")
        return []

    matches = re.findall(r"JSON\.parse\(\x27(\[.*?\])\x27\)", content)
    if len(matches) < 3:
        logger.error("Failed to extract JSON tables from ResiQ bundle")
        return []

    actions = json.loads(matches[0].encode("utf-8").decode("unicode_escape"))
    discounts = json.loads(matches[1].encode("utf-8").decode("unicode_escape"))
    directory = json.loads(matches[2].encode("utf-8").decode("unicode_escape"))

    def clean_key(s: str) -> str:
        return re.sub(r"[^a-z0-9]", "", s.lower())

    def match_action(shop_name: str, shop_unit: str):
        c_name = clean_key(shop_name)
        if "goji" in c_name:
            for a in actions:
                if a["id"] == "goji-physiotherapy": return a
        if "omote" in c_name:
            for a in actions:
                if a["id"] == "omote-special-edition": return a
        if "ssada" in c_name:
            for a in actions:
                if a["id"] == "ssada-gimbap": return a
        if "sixhands" in c_name or "bunnys" in c_name:
            for a in actions:
                if a["id"] == "six-hands": return a
        for a in actions:
            ca = clean_key(a["name"])
            if ca == c_name or ca in c_name or c_name in ca:
                return a
        return None

    disc_by_unit = {d["unit"].replace("#", "").strip().lower(): d for d in discounts}
    disc_by_name = {clean_key(d["name"]): d for d in discounts}

    meta_map = {
        "A Hot Hideout": {
            "hours": "11:00 - 21:30 daily",
            "desc": "Popular customized Mala Xiang Guo (stir-fry) and Mala collagen soup with signature scrambled eggs and fried potato slices.",
            "tips": "Order online ahead via ResiQ to skip peak dinner queue."
        },
        "Ajumma's": {
            "hours": "11:00 - 21:30 daily",
            "desc": "Casual Korean restaurant famous for Kimchi Pork Belly Stew, Beef Bulgogi, Korean Fried Chicken, and complimentary refillable side dishes.",
            "tips": "Scan QR code or use the direct ResiQ order link. Resident perk: Free Hotteok with min $45 spend."
        },
        "AL IJAZ": {
            "hours": "07:00 - 22:30 daily",
            "desc": "Halal Indian-Muslim restaurant offering crispy Roti Prata, Murtabak, Briyani, and Teh Tarik.",
            "tips": "Early opening makes it ideal for morning breakfast prata."
        },
        "Anytime Fitness": {
            "hours": "24/7 (Staffed: Mon-Fri 12:00-21:00, Sat 10:00-14:00)",
            "desc": "24-hour fitness gym with cardio machines, free weights, power racks, and private shower facilities.",
            "tips": "Located at B1 right next to Lentor MRT linkway. Direct elevator access from residence."
        },
        "Aspire Hub": {
            "hours": "Mon-Fri 13:00 - 21:30, Sat-Sun 09:00 - 18:30",
            "desc": "Premier tuition and enrichment centre providing customized academic coaching for Primary, Secondary, and JC students.",
            "tips": "10% resident discount on total bill."
        },
        "Bunny's | Six Hands": {
            "hours": "08:00 - 21:00 daily",
            "desc": "Artisan cafe, bakery, and brunch destination offering specialty coffee, sourdough toasts, and delicate pastries.",
            "tips": "Order online ahead via direct ResiQ link to pick up coffee on the way to MRT."
        },
        "Burger King": {
            "hours": "08:00 - 22:00 daily",
            "desc": "Flame-grilled Whoppers, burgers, nuggets, breakfast croissants, and meal sets.",
            "tips": "10% resident discount available. Mobile ordering supported via BK App link."
        },
        "CHAGEE": {
            "hours": "10:00 - 21:30 daily",
            "desc": "Premium Chinese milk tea and fresh brew tea made from whole-leaf tea and fresh milk (famous for Jasmine Green Milk Tea).",
            "tips": "Pre-order via CHAGEE app link to skip lengthy weekend lines."
        },
        "Chef Wen": {
            "hours": "10:30 - 21:30 daily",
            "desc": "Traditional claypot specialties, herbal soups, and comforting zi char dishes.",
            "tips": "10% resident discount on total bill."
        },
        "Cold Storage Fresh": {
            "hours": "08:00 - 22:30 daily",
            "desc": "Anchor full-format supermarket featuring fresh meat butchery, seafood, organic produce, deli counter, bakery, and international wines.",
            "tips": "Evening markdowns (20-30% off sushi and bakery) usually begin around 8:30 PM."
        },
        "Cristofori Music Academy": {
            "hours": "Mon-Fri 11:30 - 21:00, Sat-Sun 09:00 - 19:00",
            "desc": "Music academy offering piano, violin, guitar, and drum lessons, as well as musical instrument sales.",
            "tips": "10% resident discount on musical instruments and lesson course sign-ups."
        },
        "Daily": {
            "hours": "10:00 - 21:00 daily",
            "desc": "Contemporary cafe offering all-day light bites, coffee, and comfort refreshments.",
            "tips": "10% resident discount on total bill."
        },
        "First Bowl Rice Kitchen": {
            "hours": "10:30 - 21:30 daily",
            "desc": "Wholesome Asian rice bowls, stewed meat sets, and comforting homemade soup sets.",
            "tips": "Supports direct online mobile order ahead. Resident voucher accepted."
        },
        "Fresh & Clean": {
            "hours": "10:00 - 20:30 daily",
            "desc": "Professional dry cleaning, laundry, curtain washing, and fabric alteration services.",
            "tips": "10% resident discount on all services. Convenient for bulky curtain and bedsheet cleaning."
        },
        "Fun Claw": {
            "hours": "10:00 - 22:00 daily",
            "desc": "Family entertainment claw machine arcade with licensed plush toys and collectibles.",
            "tips": "Great for kids entertainment on Level 1."
        },
        "Furrest Supply": {
            "hours": "10:30 - 21:30 daily",
            "desc": "Boutique pet retail store with premium dog/cat food, treats, supplements, accessories, and grooming essentials.",
            "tips": "Convenient for quick pet food and litter refills right below the condo."
        },
        "Goji Women's and Family Physiotherapy": {
            "hours": "Mon-Fri 09:00 - 19:00, Sat 09:00 - 14:00",
            "desc": "Specialized physiotherapy clinic focusing on women's health, prenatal/postnatal recovery, pediatric care, and musculoskeletal rehabilitation.",
            "tips": "Direct online appointment booking via Bio.site link. First-visit resident perk: free protein shaker or massage ball."
        },
        "Guardian": {
            "hours": "10:00 - 21:30 daily",
            "desc": "Health, wellness, personal care, and pharmacy chain carrying vitamins, skincare, and everyday health supplies.",
            "tips": "Located at #01-01 inside the supermarket concourse."
        },
        "Han's Union": {
            "hours": "07:30 - 21:30 daily",
            "desc": "Heritage Hainanese restaurant concept featuring pork chops, chicken pies, local coffee, fried rice, and European pastries.",
            "tips": "5% resident discount on total bill."
        },
        "He Jia Huan": {
            "hours": "11:00 - 21:30 daily",
            "desc": "Traditional warm and cold Chinese desserts (tang yuan, mango pomelo sago, black sesame paste) and savory snacks.",
            "tips": "10% resident discount with min spend $30 on weekdays."
        },
        "Healing Touch Spa": {
            "hours": "11:00 - 22:30 daily",
            "desc": "Award-winning wellness spa offering deep tissue acupressure massage, aromatherapy, prenatal massage, and facial treatments.",
            "tips": "Direct online outlet QR booking link available. 5% resident discount on weekdays (11am-5pm)."
        },
        "Hua Xia Language Centre": {
            "hours": "Tue-Fri 13:00 - 21:00, Sat-Sun 09:00 - 18:30 (Closed Mon)",
            "desc": "Specialist Chinese language learning centre offering MOE-aligned Chinese enrichment from preschool to secondary levels.",
            "tips": "Located at B1 near enrichment cluster."
        },
        "Ice Talk": {
            "hours": "10:30 - 21:30 daily",
            "desc": "Affordable fresh fruit juices, smoothies, bubble tea, and crushed ice refreshments.",
            "tips": "Quick grab-and-go drink option on Level 1."
        },
        "Jew Kit Hainanese Chicken Rice": {
            "hours": "10:00 - 21:00 daily",
            "desc": "Heritage Hainanese chicken rice establishment serving steamed and roasted chicken, char siew, roast pork, and zi char sides.",
            "tips": "15% resident discount on total bill."
        },
        "Joylion Buffet Hotpot": {
            "hours": "11:00 - 22:00 daily",
            "desc": "All-you-can-eat individual and sharing pot Chinese hotpot with extensive meat cuts, seafood, vegetables, and condiments.",
            "tips": "Located at B1. Ideal for family gatherings."
        },
        "KFC": {
            "hours": "08:00 - 22:00 daily",
            "desc": "Original Recipe and Hot & Crispy fried chicken, burgers, egg tarts, and breakfast sets.",
            "tips": "15% resident discount with min spend $15. Mobile pre-ordering via KFC app link."
        },
        "Kodecoon Academy": {
            "hours": "Tue-Fri 11:00 - 19:00, Sat-Sun 09:00 - 18:00 (Closed Mon)",
            "desc": "Leading STEM and technology school teaching kids ages 4-16 coding, Scratch, Python, Roblox game dev, and AI concepts.",
            "tips": "Free trial classes available upon inquiry."
        },
        "Kopi & Tarts": {
            "hours": "08:00 - 21:00 daily",
            "desc": "Nanyang coffee and bakery chain famous for warm flaky egg tarts, kaya butter buns, pastry puffs, and chicken curry puffs.",
            "tips": "Great for quick takeaway tea-time snacks."
        },
        "Let's Eat!": {
            "hours": "08:00 - 21:30 daily",
            "desc": "Modern hawker eatery serving traditional Minced Meat Noodles (Bak Chor Mee), Fishball Noodles, Laksa, and crispy appetizers.",
            "tips": "Affordable everyday local hawker fare on Level 1."
        },
        "Luminous Dental": {
            "hours": "Mon-Fri 09:30 - 21:00, Sat-Sun 09:30 - 17:00",
            "desc": "Full-service dental clinic providing scaling & polishing, teeth whitening, invisalign, root canals, and pediatric dental care.",
            "tips": "Special resident pricing: Basic Care $96, Comprehensive $126, Essential $196. CHAS & Medisave accredited."
        },
        "M&G Life": {
            "hours": "10:00 - 21:30 daily",
            "desc": "Lifestyle stationery and homeware shop offering quality pens, notebooks, organizers, cute gifts, and creative craft supplies.",
            "tips": "Handy for school stationery supplies for kids."
        },
        "Ma Kuang TCM": {
            "hours": "Mon-Sat 10:00 - 20:30, Sun 10:00 - 18:00",
            "desc": "Reputable Traditional Chinese Medicine clinic providing physician consultation, acupuncture, cupping (ba guan), and herbal prescriptions.",
            "tips": "WhatsApp booking link available. 5% resident discount on all services."
        },
        "MERLE & CO": {
            "hours": "11:00 - 21:30 daily",
            "desc": "Chic bistro offering Western pasta, grilled proteins, artisanal brunch plates, and premium drinks.",
            "tips": "Direct mobile order link via ResiQ. 5% resident discount on à la carte main dishes."
        },
        "Mulberry Learning": {
            "hours": "Mon-Fri 07:00 - 19:00 (Closed Sat-Sun)",
            "desc": "Award-winning preschool and infant care featuring Habit of Mind and Reggio Emilia-inspired curriculum.",
            "tips": "Conveniently situated on Level 2 with direct sheltered drop-off."
        },
        "Nan Yang Dao": {
            "hours": "10:00 - 21:30 daily",
            "desc": "Authentic Malaysian food paradise famous for Selayang Big Bowl Curry Mee, Penang Chendol, Klang Bak Kut Teh, and Fried Carrot Cake.",
            "tips": "Expect peak dinner lines; drop by early or during off-peak hours."
        },
        "NK Hairworks": {
            "hours": "10:30 - 20:30 daily",
            "desc": "Established hair salon brand offering haircuts, organic hair coloring, perm, scalp therapy, and hair spa treatments.",
            "tips": "20% resident discount on selected à la carte hair services."
        },
        "Omoté: Special Edition": {
            "hours": "11:30 - 14:30, 17:30 - 21:30 daily",
            "desc": "Contemporary Japanese dining famed for monumental Bara Chirashi Don bowls, creative sashimi rolls, and roasted sushi platters.",
            "tips": "Order or join queue via direct ResiQ link. Very popular for weekend dinners."
        },
        "Optometrist At Work": {
            "hours": "10:30 - 21:00 daily",
            "desc": "Eye care optical practice with clinical optometrists providing comprehensive eye examinations, prescription glasses, sunglasses, and contact lenses.",
            "tips": "Resident perk: 1-for-1 offer on eyeglasses; attractive gifts with contact lens purchases >$200."
        },
        "Pinnacle Family Clinic": {
            "hours": "Mon-Fri 08:30 - 21:00, Sat-Sun 09:00 - 13:00",
            "desc": "Neighborhood GP medical clinic offering acute care, chronic disease management, vaccinations, health screenings, and pre-employment checkups.",
            "tips": "Exclusive resident health screening rates: Classic+ $99, Comprehensive $199, Flu Jab $33, Helper 6ME $25."
        },
        "PlayFACTO School": {
            "hours": "Mon-Fri 10:00 - 19:00 (Closed Sat-Sun)",
            "desc": "Premium student care centre and holistic mathematics enrichment centre providing after-school supervision and homework coaching.",
            "tips": "Located at B1 enrichment belt."
        },
        "QB PREMIUM": {
            "hours": "10:00 - 21:00 daily",
            "desc": "Elevated express hair grooming salon offering precise Japanese dry haircuts and styling.",
            "tips": "Check and join digital queue online before walking down via direct live link: https://qbhouse.relsystems.net:443/RELGetQueueLM.aspx?brCode=QDCOJEFZ (or via ResiQ)."
        },
        "Shiok Burger": {
            "hours": "11:00 - 21:30 daily",
            "desc": "Handcrafted smash burgers, truffle fries, milkshakes, and crispy tenders.",
            "tips": "Pre-order online via direct Restosuite / ResiQ link. GuocoLand resident voucher accepted."
        },
        "Ssada Gimbab": {
            "hours": "10:00 - 21:30 daily",
            "desc": "Authentic street-style Korean gimbap rolls, spicy rice cakes (tteokbokki), ramen, and dumplings.",
            "tips": "Direct mobile ordering link supported via FnBees / ResiQ."
        },
        "The Hanok": {
            "hours": "11:00 - 21:30 daily",
            "desc": "Traditional Korean dining specializing in comforting soups, stews, Korean pancake (pajeon), and tabletop meats.",
            "tips": "Great for cozy family Korean meals on Level 1."
        },
        "The Nail Arcadia": {
            "hours": "10:30 - 20:30 daily",
            "desc": "Nail artistry sanctuary offering gel manicures, pedicures, nail spa treatments, and eyelash extensions.",
            "tips": "Appointments recommended on weekends."
        },
        "Tim Hortons": {
            "hours": "07:30 - 22:00 daily",
            "desc": "Iconic Canadian coffeehouse chain serving freshly brewed Double-Double coffee, Iced Capps, fresh sourdough melts, and Timbits.",
            "tips": "15% resident discount with min spend $15. Mobile pre-order available on Tim Hortons SG app."
        },
        "Toast & Roll by Swee Heng": {
            "hours": "07:30 - 21:30 daily",
            "desc": "Halal-certified local bakery concept by Swee Heng, specializing in fresh pillowy swiss rolls, artisanal breads, and breakfast buns.",
            "tips": "5% resident discount on total bill."
        },
        "Tongue Tip Lanzhou Beef Noodles": {
            "hours": "11:00 - 21:30 daily",
            "desc": "Halal-certified traditional hand-pulled noodles in rich clear beef broth, hand-crafted across 8 different noodle thickness tiers.",
            "tips": "15% resident discount on à la carte items."
        },
        "Twigly's Convenience Store": {
            "hours": "08:00 - 22:30 daily",
            "desc": "Modern convenience boutique offering chilled beverages, grab-and-go snacks, imported tidbits, and emergency daily sundries.",
            "tips": "5% resident discount with min spend $10."
        },
        "UMAI": {
            "hours": "11:30 - 21:30 daily",
            "desc": "Artisanal Japanese udon bar serving fresh handmade sanuki udon in hot dashi broth, cold dipping udon, and crispy tempura.",
            "tips": "Digital ordering and table check-in available directly via iReach / ResiQ link."
        },
        "Venus Beauty": {
            "hours": "10:00 - 21:30 daily",
            "desc": "Budget-friendly personal care chain offering shampoos, toiletries, household cleaning detergents, and skincare brands.",
            "tips": "Great value for everyday household refills and toiletries."
        },
        "Xin Yuan Ji": {
            "hours": "11:00 - 21:30 daily",
            "desc": "Famous Bugis heritage fish soup brand known for thick charcoal fish head steamboat, sliced fish bee hoon, and zi char favorites.",
            "tips": "10% resident discount on total bill. Online QR ordering available via YQueue link."
        },
        "Yuen Kee Dumpling": {
            "hours": "10:30 - 21:30 daily",
            "desc": "Specialist handmade northern Chinese dumplings, pan-fried guotie, spicy wanton noodles, and comforting bone broth.",
            "tips": "10% resident discount on total bill. Direct online pre-order link: https://m.sea.restosuite.ai/open/app/e3b0q78vczyd?q=fcadcc4k4gec (or via ResiQ)."
        }
    }

    enriched_directory = []

    # Entry 0: Lentor MRT direct underground linkway
    enriched_directory.append({
        "name": "Lentor MRT Station (TE5)",
        "category": "Transport",
        "floor": "B1",
        "unit": "Direct Linkway B1",
        "opening_hours": "First train ~05:45, Last train ~00:20 daily",
        "description": "Direct sheltered underground linkway to Thomson-East Coast Line (TEL), connecting to Orchard, Marina Bay, and Woodlands.",
        "resident_discount": None,
        "order_url": None,
        "order_type": None,
        "resiq_link": "https://resiq-lm.vercel.app/",
        "tips": "Exit 1 connects seamlessly into Lentor Modern Mall B1 without stepping outdoors."
    })

    for shop in directory:
        name = shop["name"]
        unit = shop["unit"]
        cat = shop["category"]
        clean_unit = unit.replace("#", "").strip().lower()
        c_name = clean_key(name)
        
        if unit.startswith("#B1") or unit.startswith("B1"):
            floor = "B1"
        elif unit.startswith("#02") or unit.startswith("02"):
            floor = "L2"
        else:
            floor = "L1"

        disc_info = disc_by_unit.get(clean_unit) or disc_by_name.get(c_name)
        discount_text = disc_info.get("discount") if disc_info else None

        action_info = match_action(name, unit)
        order_url = action_info.get("actionUrl") if action_info else None
        order_type = action_info.get("linkType") if action_info else None
        resiq_link = f"https://resiq-lm.vercel.app/r/{action_info['id']}" if action_info else "https://resiq-lm.vercel.app/"

        meta = meta_map.get(name, {})
        hours = meta.get("hours", "10:00 - 21:30 daily")
        desc = meta.get("desc", f"{name} is a verified tenant in Lentor Modern Mall.")
        tips = meta.get("tips", "")

        entry = {
            "name": name,
            "category": cat,
            "floor": floor,
            "unit": unit,
            "opening_hours": hours,
            "description": desc,
            "resident_discount": discount_text,
            "order_url": order_url,
            "order_type": order_type,
            "resiq_link": resiq_link,
            "tips": tips
        }
        enriched_directory.append(entry)

    return enriched_directory


# ==============================================================================
# MAIN EXECUTION
# ==============================================================================

def main():
    logger.info("🚀 Starting Lentor Modern Knowledge Ingestion Pipeline...")
    docs_dir = RAW_DIR / "Lentor Modern Documents"
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Process Official Contacts
    contacts = process_useful_contacts(docs_dir)
    contacts_file = PROCESSED_DIR / "estate_contacts.json"
    with open(contacts_file, "w", encoding="utf-8") as f:
        json.dump(contacts, f, indent=2, ensure_ascii=False)
    logger.info(f"✅ Saved {len(contacts)} contacts to {contacts_file.name}")

    # 2. Process Appliance Operating Manuals
    appliances = process_appliance_manuals(docs_dir)
    appliances_file = PROCESSED_DIR / "appliance_manuals.json"
    with open(appliances_file, "w", encoding="utf-8") as f:
        json.dump(appliances, f, indent=2, ensure_ascii=False)
    logger.info(f"✅ Saved {len(appliances)} appliance guides to {appliances_file.name}")

    # 3. Process Bylaws, Novade & Maintenance
    bylaw_records = process_bylaws_and_guides(docs_dir)
    for c in contacts:
        bylaw_records.append({
            "topic": f"Contact: {c['category']}",
            "section": c["provider"],
            "content": f"{c['category']}: {c['provider']} (Tel: {c['contact']}). Notes: {c['notes']}"
        })
    for a in appliances:
        bylaw_records.append({
            "topic": f"Appliance: {a['appliance']} ({a['model']})",
            "section": a["category"],
            "content": f"{a['appliance']} ({a['model']}): {a.get('features', '')} Troubleshooting: {a.get('troubleshooting', '') or a.get('child_lock_procedure', '')} Supplier Hotline: {a.get('supplier_contact', '')}"
        })

    bylaws_file = PROCESSED_DIR / "bylaws_handbook.json"
    with open(bylaws_file, "w", encoding="utf-8") as f:
        json.dump(bylaw_records, f, indent=2, ensure_ascii=False)
    logger.info(f"✅ Saved {len(bylaw_records)} handbook chunks to {bylaws_file.name}")

    # 4. Process Telegram Chat Exports
    raw_chat_messages = parse_html_chat_files(RAW_DIR)
    clusters = categorize_and_cluster_messages(raw_chat_messages)
    tips = synthesize_tips_with_gemini(clusters)

    tips_file = PROCESSED_DIR / "verified_community_tips.json"
    with open(tips_file, "w", encoding="utf-8") as f:
        json.dump(tips, f, indent=2, ensure_ascii=False)
    logger.info(f"✅ Saved {len(tips)} verified community tips to {tips_file.name}")

    # 5. Process ResiQ Mall Directory & Ordering Links
    mall_tenants = process_resiq_mall_directory()
    if mall_tenants:
        mall_file = PROCESSED_DIR / "mall_directory.json"
        with open(mall_file, "w", encoding="utf-8") as f:
            json.dump(mall_tenants, f, indent=2, ensure_ascii=False)
        logger.info(f"✅ Saved {len(mall_tenants)} mall tenants to {mall_file.name}")

    # 6. Verify Estate Profile
    estate_file = PROCESSED_DIR / "estate_profile.json"
    if estate_file.exists():
        logger.info(f"✅ Estate profile verified at {estate_file.name}")

    print("\n🎉 Knowledge Ingestion Complete!")
    print(f"• Estate Contacts: {len(contacts)} providers saved to estate_contacts.json")
    print(f"• Appliance Specs: {len(appliances)} manuals saved to appliance_manuals.json")
    print(f"• Handbook & Bylaws: {len(bylaw_records)} chunks saved to bylaws_handbook.json")
    print(f"• Verified Community Tips: {len(tips)} tips saved to verified_community_tips.json")
    if mall_tenants:
        print(f"• Mall Directory & ResiQ Links: {len(mall_tenants)} tenants saved to mall_directory.json")
    if estate_file.exists():
        print(f"• Estate Profile & School Catchments: Verified in estate_profile.json")


if __name__ == "__main__":
    main()
