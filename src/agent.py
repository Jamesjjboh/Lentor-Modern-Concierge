"""Gemini 3.8 Flash Agent core & Toolbelt for Lentor Modern Concierge."""

import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from google import genai
from google.genai import types

from src.config import GEMINI_API_KEY, GEMINI_MODEL, PROCESSED_DATA_DIR
from src.database import db_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# System instructions setting identity, guardrails, and tone
SYSTEM_INSTRUCTION = """
You are the Lentor Modern Digital Concierge, a helpful, polite, and accurate virtual concierge for the ~605 households of Lentor Modern (a premier integrated mixed-use development by GuocoLand in Singapore, atop Lentor Modern Mall and Lentor MRT).

You have access to 7 specialized tools:
1. `search_bylaws_and_handbook`: Use to look up official MCST by-laws, renovation hours & deposits, facility booking rules, aircon ledge rules, moving & delivery bay procedures, handover defect procedures, and developer supplier contact hotlines for appliances & fittings (e.g. Mitsubishi air conditioning 6473 2308, SMEG appliances 6950 0910, Rheem water heater 6872 2043, Yale digital lock 6591 8868, Fermax intercom/smart home 6259 0700).
2. `search_mall_directory`: Use to look up shops, supermarkets (CS Fresh), clinics, childcare, and eateries in Lentor Modern Mall, including floor levels (B1, L1, L2), unit numbers, operating hours, direct online ordering/queuing links (from ResiQ, e.g. QB Premium queue, Ajumma's, Yuen Kee Dumpling), verified resident discounts, and mall collection points (e.g. Twigly's #01-10 Shopee collection point).
3. `get_verified_community_tips`: Use to retrieve crowdsourced neighbour advice (e.g. delivery bay access, parcel lockers like Shopee/SPX lockers at Carpark Level 2 near Tower 5 letterbox, induction cooker lock quirks, aircon piping SWG requirements, evening grocery discounts).
4. `generate_mcst_email_draft`: Use when a resident needs to formally email the Managing Agent (MA) to report a defect, common property issue, or submit a request.
5. `submit_tip_to_moderation`: Use when a resident shares a new helpful tip, discovery, or advice that should be added to the community knowledge base.
6. `submit_developer_feedback`: Use when a resident provides feedback about the bot itself, reports a bug, mentions an error or inaccuracy in an answer, or suggests a new feature for the concierge creator & admin (@jamesjjboh).
7. `search_estate_profile`: Use to look up verified development and estate facts: developer (GuocoLand), tenure (99-yr from 2020), total 605 units across 3 towers of 25 storeys, postal codes (3 Lentor Central S788888, 5 S788889, 7 S788890), unit types & bathroom configurations (1BR+F 527sf 1-bath; 2BR+F with 678sf 1-bath vs 732sf 2-bath; 3BR+F with 969-990sf 2-bath vs 1109-1130sf 3-bath/yard WC; 4BR+F 1528sf 4-bath), transit links (Lentor MRT TE5 direct link, first/last train timings, station exits, bus stops & routes 825, 855, 852, 851, 652), and official MOE primary school proximity (Anderson Primary is strictly the ONLY primary school <1km; CHIJ St. Nicholas Girls' School is 1-2km, NOT within 1km).


Guidelines:
- Maintain a warm, helpful, and professional Singapore condo concierge tone.
- When answering questions about estate rules, mall shops, or property facts, ALWAYS invoke the relevant tool to provide factual, up-to-date information. Do not invent bylaw clauses or school distances.
- Strictly adhere to verified school distances: Anderson Primary is the ONLY school within 1km (<1km); CHIJ St. Nicholas Girls' School is in the 1km to 2km band, NOT within 1km.
- NEVER request or reveal sensitive Personally Identifiable Information (PII) like unit numbers (#XX-YY), private resident names, or mobile numbers.
- If you cannot find an answer in the bylaws, mall directory, estate profile, or community tips, do NOT leave the resident stranded or abruptly say you don't know. Warmly and concisely explain that this specific topic is not yet in the official estate records or handbook, and recommend they contact the Managing Agent (CBRE at managementoffice@LT-MODERN.COM or +65 6054 3370) or Concierge (+65 6054 3375).
"""


# --- Tool 1: Bylaws & Handbook Search ---
def search_bylaws_and_handbook(query: str) -> str:
    """Searches official Lentor Modern MCST by-laws, renovation guidelines, facility policies, and estate rules."""
    handbook_file = PROCESSED_DATA_DIR / "bylaws_handbook.json"
    if not handbook_file.exists():
        return "No handbook or bylaws data is currently available in the estate database."

    try:
        with open(handbook_file, "r", encoding="utf-8") as f:
            records: List[Dict[str, Any]] = json.load(f)
    except Exception as e:
        return f"Error loading handbook records: {e}"

    # Strip conversational stopwords so equipment/appliance and policy terms get priority
    STOPWORDS = {
        "i", "me", "my", "myself", "we", "our", "ours", "ourselves", "you", "your",
        "yours", "yourself", "yourselves", "he", "him", "his", "himself", "she",
        "her", "hers", "herself", "it", "its", "itself", "they", "them", "their",
        "theirs", "themselves", "what", "which", "who", "whom", "this", "that",
        "these", "those", "am", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "having", "do", "does", "did", "doing", "a", "an",
        "the", "and", "but", "if", "or", "because", "as", "until", "while", "of",
        "at", "by", "for", "with", "about", "against", "between", "into", "through",
        "during", "before", "after", "above", "below", "to", "from", "up", "down",
        "in", "out", "on", "off", "over", "under", "again", "further", "then",
        "once", "here", "there", "when", "where", "why", "how", "all", "any",
        "both", "each", "few", "more", "most", "other", "some", "such", "no",
        "nor", "not", "only", "own", "same", "so", "than", "too", "very", "s",
        "t", "can", "will", "just", "don", "should", "now", "issues", "issue", "help", "call"
    }
    raw_tokens = re.findall(r"\w+", query.lower())
    query_tokens = [t for t in raw_tokens if t not in STOPWORDS]
    if not query_tokens:
        query_tokens = raw_tokens

    scored_matches: List[Tuple[int, Dict[str, Any]]] = []

    for r in records:
        topic_text = r.get("topic", "").lower()
        section_text = r.get("section", "").lower()
        body_text = f"{r.get('content', '')} {r.get('text', '')}".lower()

        score = 0
        for token in query_tokens:
            if token in topic_text:
                score += 5
            if token in section_text:
                score += 3
            if token in body_text:
                score += 1

        if score > 0:
            scored_matches.append((score, r))

    scored_matches.sort(key=lambda x: x[0], reverse=True)
    top_matches = [m[1] for m in scored_matches[:3]]

    if not top_matches:
        return f"No official by-laws found matching '{query}'. Please check with the Concierge desk."

    results = []
    for m in top_matches:
        heading = m.get("section") or m.get("topic") or f"Page {m.get('page', '')}"
        body = m.get("content") or m.get("text", "")
        results.append(f"[{heading}]\n{body}")

    return "\n\n".join(results)


# --- Tool 2: Mall Directory Search ---
def search_mall_directory(category: str = "", shop_name: str = "") -> str:
    """Looks up Lentor Modern Mall tenant directory, floor levels (B1, L1, L2), unit numbers, operating hours, direct online ordering/queuing links (via ResiQ), and verified resident discounts."""
    mall_file = PROCESSED_DATA_DIR / "mall_directory.json"
    if not mall_file.exists():
        return "Mall directory is currently being updated."

    try:
        with open(mall_file, "r", encoding="utf-8") as f:
            tenants: List[Dict[str, Any]] = json.load(f)
    except Exception as e:
        return f"Error loading mall directory: {e}"

    search_term = f"{category} {shop_name}".strip().lower()
    words = search_term.split()

    def score_match(t: Dict[str, Any]) -> int:
        name_lower = t.get("name", "").lower()
        cat_lower = t.get("category", "").lower()
        desc_lower = t.get("description", "").lower()
        tips_lower = t.get("tips", "").lower()
        disc_lower = t.get("resident_discount", "").lower() if t.get("resident_discount") else ""
        order_url = t.get("order_url") or ""

        if not search_term:
            return 1

        score = 0
        if search_term == name_lower:
            score += 100
        elif search_term in name_lower:
            score += 60
        elif words and all(w in name_lower for w in words):
            score += 45
        elif words and any(w in name_lower for w in words):
            score += 25

        if search_term in cat_lower:
            score += 30
        elif words and any(w in cat_lower for w in words):
            score += 15

        if search_term in desc_lower or (words and any(w in desc_lower for w in words)):
            score += 15

        if search_term in tips_lower or (words and any(w in tips_lower for w in words)):
            score += 10

        if any(k in search_term for k in ["discount", "deal", "promo", "perk", "benefit"]):
            if disc_lower:
                score += 35

        if any(k in search_term for k in ["voucher", "evoucher", "guocoland voucher"]):
            if t.get("accepts_guocoland_voucher"):
                score += 45

        if any(k in search_term for k in ["resiq", "queue", "order", "online", "link", "qr", "app"]):
            if order_url:
                score += 35

        return score

    scored_matches = [(score_match(t), t) for t in tenants if score_match(t) > 0]
    scored_matches.sort(key=lambda x: x[0], reverse=True)
    matches = [t for _, t in scored_matches]

    # If resident specifically asks about GuocoLand vouchers
    if any(k in search_term for k in ["voucher", "vouchers", "evoucher", "e-voucher", "guocoland voucher"]):
        voucher_shops = [t for t in tenants if t.get("accepts_guocoland_voucher")]
        if voucher_shops:
            fnb = [s for s in voucher_shops if "food" in s.get("category", "").lower() or "beverage" in s.get("category", "").lower()]
            services = [s for s in voucher_shops if s not in fnb]

            lines = [f"🎟️ Official Participating Merchants Accepting GuocoLand e-Vouchers ({len(voucher_shops)} Stores at Lentor Modern Mall):\n"]
            lines.append("🍽️ Food & Beverages:")
            for s in sorted(fnb, key=lambda x: x["name"]):
                unit_str = f" ({s.get('unit')})" if s.get('unit') else ""
                lines.append(f"• {s['name']}{unit_str}")

            lines.append("\n🛍️ Retail, Services & Wellness:")
            for s in sorted(services, key=lambda x: x["name"]):
                unit_str = f" ({s.get('unit')})" if s.get('unit') else ""
                cat_str = f" [{s.get('category')}]" if s.get('category') else ""
                lines.append(f"• {s['name']}{unit_str}{cat_str}")

            lines.append("\n💡 Source: Verified directly from official Lentor Modern Mall directory (https://www.lentormodern.com.sg/shops/). Flash e-vouchers at cashier counters prior to payment.")
            return "\n".join(lines)

    if not matches:
        return f"No shops found in Lentor Modern Mall matching '{search_term}'. You can also browse the full resident portal at https://resiq-lm.vercel.app/."

    results = []
    for m in matches[:6]:
        unit_display = m.get('unit', '')
        info = (
            f"🏪 {m.get('name')} ({m.get('category')})\n"
            f"📍 Location: Floor {m.get('floor')}, Unit {unit_display}\n"
            f"⏰ Hours: {m.get('opening_hours', '10:00 - 21:30 daily')}\n"
            f"ℹ️ {m.get('description', '')}"
        )
        if m.get("resident_discount"):
            info += f"\n🏷️ Resident Discount: {m.get('resident_discount')}"
            if m.get("discount_terms"):
                info += f" ({m.get('discount_terms')})"
        if m.get("accepts_guocoland_voucher"):
            info += "\n🎟️ GuocoLand e-Vouchers: Accepted here"
        if m.get("order_url"):
            info += f"\n📲 Direct Order / Queue Link: {m.get('order_url')}\n🔗 ResiQ Portal: {m.get('resiq_link')}"
        elif m.get("resiq_link") and m.get("resiq_link") != "https://resiq-lm.vercel.app/":
            info += f"\n🔗 ResiQ Link: {m.get('resiq_link')}"
        if m.get("tips"):
            info += f"\n💡 Tip: {m.get('tips')}"
        results.append(info)

    header = "Found shops in Lentor Modern Mall (with ResiQ order & discount integrations):\n\n"
    return header + "\n\n".join(results)


# --- Tool 3: Verified Community Tips ---
def get_verified_community_tips(topic: str = "") -> str:
    """Retrieves verified tribal knowledge and practical tips crowdsourced from Lentor Modern residents."""
    tips = []
    # 1. Check local seed file
    tips_file = PROCESSED_DATA_DIR / "verified_community_tips.json"
    if tips_file.exists():
        try:
            with open(tips_file, "r", encoding="utf-8") as f:
                seed_tips = json.load(f)
                t_lower = topic.strip().lower()
                query_tokens = [w for w in re.findall(r"\w+", t_lower) if len(w) > 2]

                scored_seed: List[Tuple[int, Dict[str, Any]]] = []
                for st in seed_tips:
                    topic_text = st.get("topic", "").lower()
                    title_text = st.get("title", "").lower()
                    content_text = st.get("content", "").lower()
                    full_text = f"{topic_text} {title_text} {content_text}"

                    if not query_tokens:
                        scored_seed.append((1, st))
                    else:
                        score = 0
                        for token in query_tokens:
                            if token in title_text:
                                score += 5
                            elif token in topic_text:
                                score += 3
                            elif token in content_text:
                                score += 1
                        if score > 0:
                            scored_seed.append((score, st))

                scored_seed.sort(key=lambda x: x[0], reverse=True)
                for _, st in scored_seed:
                    tips.append(f"• [{st.get('topic', 'general').capitalize()}] {st.get('title')}: {st.get('content')}")
        except Exception as e:
            logger.error(f"Error reading seed tips: {e}")

    # 2. Check approved tips in Firestore
    try:
        db_tips = db_client.get_approved_tips(topic=topic, limit=5)
        for dt in db_tips:
            tips.append(f"• [{dt.get('topic', 'community').capitalize()}] {dt.get('content')}")
    except Exception as e:
        logger.error(f"Error fetching Firestore approved tips: {e}")

    if not tips:
        return f"No verified community tips found for '{topic}' yet."

    return "Verified Resident Tips:\n" + "\n".join(tips[:5])


# --- Tool 4: MCST Email Draft Generator ---
def generate_mcst_email_draft(issue_type: str, details: str, resident_name: str = "Resident") -> str:
    """Formats a professional, bylaw-referenced email draft addressed to the official Managing Agent (CBRE Pte Ltd at managementoffice@LT-MODERN.COM)."""
    subject = f"[Lentor Modern] Resident Inquiry / Feedback: {issue_type}"
    body = (
        f"To: managementoffice@LT-MODERN.COM\n"
        f"Cc: concierge@LT-MODERN.COM\n"
        f"Subject: {subject}\n\n"
        f"Dear Managing Agent (CBRE) / Estate Management Office,\n\n"
        f"I am writing as a resident of Lentor Modern regarding {issue_type}.\n\n"
        f"Details of Inquiry / Feedback:\n{details}\n\n"
        f"In accordance with estate management guidelines, could you kindly advise on the next steps or arrange for the necessary follow-up / rectification?\n\n"
        f"Thank you for your assistance and prompt attention.\n\n"
        f"Best regards,\n"
        f"{resident_name}\n"
        f"Lentor Modern Residential Unit: [Your Unit # / Tower]\n"
        f"Contact Number: [Your Contact #]\n\n"
        f"---\n"
        f"Estate Office Reference:\n"
        f"• Location: 9 Lentor Central, Level 3, Singapore 788891\n"
        f"• Office Tel: +65 6054 3370 (Mon-Fri 9am-6pm, Sat 9am-1pm)\n"
        f"• Concierge Tel: +65 6054 3375 (24/7)\n"
        f"• 24/7 Security Hotline: +65 6054 3379"
    )
    return body


# --- Tool 5: Tip Moderation Submission ---
def submit_tip_to_moderation(topic: str, tip_text: str, user_id: int = 0) -> str:
    """Submits a resident's practical tip or contractor discovery to the moderation queue for admin approval."""
    try:
        tip_id = db_client.submit_community_tip(user_id=user_id, topic=topic, content=tip_text)
        return (
            f"Thank you! Your tip about '{topic}' has been submitted to the moderation queue "
            f"(Reference ID: {tip_id}). Once approved by the admin, it will be visible to all neighbours!"
        )
    except Exception as e:
        return f"Failed to submit tip: {e}"


# --- Tool 6: Developer Feedback & Bug Submission ---
def submit_developer_feedback(category: str, details: str, user_id: int = 0) -> str:
    """Submits resident feedback, bug reports, feature requests, or handbook corrections directly to the bot creator & admin (@jamesjjboh).
    Use this tool whenever a resident expresses feedback, reports a bug or hallucination, mentions an error in an answer, or suggests a new bot feature.
    Args:
        category: One of ['bug', 'feature_request', 'data_correction', 'general']
        details: Clear description of the resident's feedback, correction, or requested feature.
        user_id: Telegram user ID of the resident submitting feedback.
    """
    try:
        fb_id = db_client.submit_feedback(
            user_id=user_id,
            username=None,
            first_name=None,
            category=category,
            message=details,
        )
        return (
            f"Thank you! Your feedback ({category}) has been submitted directly to the concierge creator & admin (@jamesjjboh) "
            f"(Reference ID: {fb_id}). James reviews all resident feedback to continuously improve the concierge."
        )
    except Exception as e:
        return f"Failed to submit feedback: {e}"


# --- Tool 7: Estate Profile, Transit & School Catchment Search ---
def search_estate_profile(query: str = "") -> str:
    """Looks up Lentor Modern project facts, developer (GuocoLand), tenure, completion dates, towers & postal codes, unit types and sizes, Lentor MRT (TE5) first/last train timings, surrounding bus routes (825, 855, 852, 851, 652), and official MOE primary school proximity tiers (e.g. Anderson Primary is strictly the ONLY school <1km; CHIJ St. Nicholas is 1–2km)."""
    profile_file = PROCESSED_DATA_DIR / "estate_profile.json"
    if not profile_file.exists():
        return "Estate profile data is currently being updated."

    try:
        with open(profile_file, "r", encoding="utf-8") as f:
            profile: Dict[str, Any] = json.load(f)
    except Exception as e:
        return f"Error loading estate profile: {e}"

    q_lower = query.lower()

    # 1. School Proximity Queries
    if any(k in q_lower for k in ["school", "primary", "secondary", "chij", "st nicholas", "nicholas", "anderson", "mayflower", "p1", "moe", "distance", "1km", "2km", "catchment"]):
        schools = profile.get("schools_proximity", {})
        pri = schools.get("primary_schools", {})
        within_1k = pri.get("within_1km", [])
        w_1k_2k = pri.get("within_1km_to_2km", [])
        sec = schools.get("secondary_and_tertiary_institutions", [])

        lines = ["🏫 Official MOE Primary School Proximity (Verified via SLA OneMap):"]
        lines.append(f"📌 Framework: {schools.get('moe_primary_registration_rule', '')}\n")
        lines.append("🟢 Primary Schools STRICTLY Within 1km (<1km):")
        for s in within_1k:
            lines.append(f"• {s['name']} ({s['distance']}) - {s['status']}")
            lines.append(f"  Address: {s['address']}")
            lines.append(f"  Verification: {s.get('official_verification', 'SLA OneMap')}")

        lines.append("\n🟡 Primary Schools Within 1km to 2km (1–2km Band):")
        for s in w_1k_2k:
            lines.append(f"• {s['name']} ({s['distance']}) - {s['status']}")
            if s.get("notes"):
                lines.append(f"  Note: {s['notes']}")
            lines.append(f"  Address: {s['address']}")

        lines.append("\n🎓 Nearby Secondary & Tertiary Institutions:")
        for s in sec[:4]:
            lines.append(f"• {s['name']} ({s['distance']}) - {s['level']}")

        return "\n".join(lines)

    # 2. Towers & Postal Codes Queries
    if any(k in q_lower for k in ["tower", "block", "postal", "address", "central", "lobby", "zip"]):
        proj = profile.get("project_overview", {})
        towers = proj.get("towers", [])
        lines = ["🏢 Lentor Modern Towers & Postal Codes:"]
        for t in towers:
            lines.append(f"• Tower {t['tower_number']}: {t['address']} ({t['storeys']} storeys)")
        lines.append("\nAll 3 towers share seamless sheltered access to Lentor Modern Mall (B1/L1) and Lentor MRT Station (TE5 Exit 1).")
        return "\n".join(lines)

    # 3. Unit Types, Bathroom Configurations & Sizes Queries
    if any(k in q_lower for k in ["unit", "bedroom", "layout", "size", "sqft", "flex", "type", "mix", "how many unit", "bath", "bathroom"]):
        proj = profile.get("project_overview", {})
        mix = proj.get("unit_mix", [])
        lines = [f"🏠 Lentor Modern Unit Mix & Layout Configurations (Total: {proj.get('total_residential_units', 605)} residential units):"]
        for item in mix:
            cat = item.get("category", "")
            if "configurations" in item:
                lines.append(f"\n📁 {cat} (Total: {item.get('total_units')} units, {item.get('percentage')}):")
                for c in item["configurations"]:
                    lines.append(f"  • {c.get('subtype')}: {c.get('size_sqft') or c.get('size_sqft_range')} | {c.get('bathrooms')}")
                    if c.get("units_count"):
                        lines.append(f"    Units: {c.get('units_count')} units")
                    if c.get("types_detail"):
                        lines.append(f"    Types: {c.get('types_detail')}")
                    lines.append(f"    Features: {c.get('layout_features')}")
            else:
                lines.append(f"\n📁 {cat} ({item.get('units_count')} units, {item.get('percentage')}):")
                lines.append(f"  • {item.get('subtype')}: {item.get('size_sqft')} | {item.get('bathrooms')}")
                lines.append(f"    Features: {item.get('layout_features')}")
        return "\n".join(lines)

    # 4. Developer / Tenure / Project Specs Queries
    if any(k in q_lower for k in ["developer", "guocoland", "tenure", "lease", "top", "contractor", "architect", "completion", "site area", "plot ratio"]):
        proj = profile.get("project_overview", {})
        lines = [
            "🏗️ Lentor Modern Project Specifications:",
            f"• Developer: {proj.get('developer')}",
            f"• Tenure: {proj.get('tenure')}",
            f"• Expected TOP: {proj.get('expected_top')} (Legal Completion: {proj.get('legal_completion')})",
            f"• Site Area: ~{proj.get('site_area_sqft', 0):,} sq ft / {proj.get('site_area_sqm', 0)} sqm (Plot Ratio: {proj.get('plot_ratio')})",
            f"• Architect: {proj.get('architect')}",
            f"• Landscape Architect: {proj.get('landscape_architect')}",
            f"• Main Contractor: {proj.get('main_contractor')}",
            f"• Residential Breakdown: {proj.get('total_residential_units')} units across {proj.get('residential_towers')} towers of {proj.get('storeys_per_tower')} storeys",
        ]
        return "\n".join(lines)

    # 5. Connectivity, MRT & Bus Queries
    if any(k in q_lower for k in ["mrt", "train", "station", "transit", "tel", "orchard", "travel time", "expressway", "bus", "825", "855", "852", "851", "652", "timing", "first train", "last train", "exit"]):
        conn = profile.get("connectivity_and_transport", {})
        mrt = conn.get("mrt_integration", {})
        buses = conn.get("bus_services_and_stops", [])

        is_timing_query = any(k in q_lower for k in ["timing", "first train", "last train", "schedule", "hour", "time", "late", "early"])
        is_bus_query = any(k in q_lower for k in ["bus", "825", "855", "852", "851", "652", "stop", "yck", "yio chu kang"])

        lines = [
            f"🚇 Transit & Transport Guide ({mrt.get('station_name', 'Lentor MRT')}):",
            f"• MRT Line: {mrt.get('line')}",
            f"• Connection: {mrt.get('connection')}",
        ]

        # Station Exits
        if any(k in q_lower for k in ["exit", "where is", "entrance"]):
            lines.append("\n🚪 Lentor MRT Station Exits:")
            for ex in mrt.get("station_exits", []):
                lines.append(f"• {ex['exit']}: {ex['description']}")

        # Train Timings
        timings = mrt.get("first_and_last_train_timings", {})
        if is_timing_query or not is_bus_query:
            nb = timings.get("northbound_woodlands_north", {})
            sb = timings.get("southbound_bayshore", {})
            lines.append("\n⏱️ First & Last Train Timings (Lentor TE5):")
            lines.append(f"🟢 Northbound - {nb.get('platform', 'Platform A')} ({nb.get('direction', 'Towards Woodlands North')}):")
            lines.append(f"  • First Train: Mon–Sat {nb.get('first_train_mon_sat')} | Sun & PH {nb.get('first_train_sun_ph')}")
            lines.append(f"  • Last Train to Woodlands North: {nb.get('last_train_to_woodlands_north')}")
            lines.append(f"  • Last Train terminating at Woodlands: {nb.get('last_train_terminating_at_woodlands')}")

            lines.append(f"🟢 Southbound - {sb.get('platform', 'Platform B')} ({sb.get('direction', 'Towards Bayshore / Marina Bay')}):")
            lines.append(f"  • First Train: Mon–Sat {sb.get('first_train_mon_sat')} | Sun & PH {sb.get('first_train_sun_ph')}")
            lines.append(f"  • Last Train to Bayshore: {sb.get('last_train_to_bayshore')}")
            lines.append(f"  • Last Train terminating at Outram Park: {sb.get('last_train_terminating_at_outram_park')}")
            lines.append(f"  • Last Train terminating at Caldecott (Circle Line): {sb.get('last_train_terminating_at_caldecott')}")

        # Bus Services
        if is_bus_query or not is_timing_query:
            lines.append("\n🚌 Surrounding Bus Services & Stops:")
            for stop in buses:
                lines.append(f"📍 {stop['stop_name']} ({stop.get('location', '')}):")
                for s in stop.get("services", []):
                    b_num = s.get("bus_number")
                    b_route = s.get("route")
                    b_hours = f" (Hours: {s.get('operating_hours')})" if s.get("operating_hours") else ""
                    lines.append(f"  • Bus {b_num}: {b_route}{b_hours}")

        # Key Transit Times
        if not is_bus_query and not is_timing_query:
            lines.append("\n⚡ Key Train Transit Times from Lentor (TE5):")
            for dest in mrt.get("key_destinations_transit_time", []):
                lines.append(f"• {dest['destination']}: {dest['stops']} stops (~{dest['time_mins']} mins)")

        return "\n".join(lines)

    # General overview default
    proj = profile.get("project_overview", {})
    return (
        f"Lentor Modern Estate Overview:\n"
        f"• Developer: {proj.get('developer')}\n"
        f"• Tenure: {proj.get('tenure')}\n"
        f"• Residential Units: {proj.get('total_residential_units')} units across 3 towers (3, 5, 7 Lentor Central)\n"
        f"• Integration: Direct sheltered connection to Lentor Modern Mall (~96,000 sq ft retail/F&B, CS Fresh, Mulberry Learning preschool) and Lentor MRT (TEL TE5, Exit 1).\n"
        f"• Primary Schools: Anderson Primary School (<1km); CHIJ St. Nicholas Girls' School (1–2km).\n"
        f"• Postal Codes: Tower 3 (S788888), Tower 5 (S788889), Tower 7 (S788890)."
    )


# Toolbelt registry
TOOL_FUNCTIONS: List[Callable[..., Any]] = [
    search_bylaws_and_handbook,
    search_mall_directory,
    get_verified_community_tips,
    generate_mcst_email_draft,
    submit_tip_to_moderation,
    submit_developer_feedback,
    search_estate_profile,
]


class LentorAgent:
    """Autonomous agent wrapping Gemini 3.8 Flash and the Lentor Modern tool catalog."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or GEMINI_API_KEY
        self.model = model or GEMINI_MODEL
        self.client: Optional[genai.Client] = None
        self._init_client()

    def _init_client(self):
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
            logger.info(f"Initialized Gemini Agent with model: {self.model}")
        else:
            logger.warning("GEMINI_API_KEY is not set. Agent will run in simulated rule-matching mode.")

    def run_query(self, user_query: str, user_id: int = 0) -> Tuple[str, List[str]]:
        """Processes a resident query, calls tools as needed, and returns (response_text, tools_called)."""
        tools_called: List[str] = []

        if not self.client:
            # Fallback simulator for local testing before API key is provided
            return self._simulated_response(user_query, user_id)

        candidate_models = [self.model]
        for fallback in ["gemini-3.5-flash", "gemini-3.1-flash-lite"]:
            if fallback not in candidate_models:
                candidate_models.append(fallback)

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=TOOL_FUNCTIONS,
            temperature=0.3,
        )

        last_error = None
        for current_model in candidate_models:
            try:
                chat = self.client.chats.create(
                    model=current_model,
                    config=config,
                )

                response = chat.send_message(user_query)
                final_text = response.text or ""

                # Check history for tool calls executed by the agent
                for msg in chat.get_history():
                    for part in getattr(msg, "parts", []):
                        fn_call = getattr(part, "function_call", None)
                        if fn_call and fn_call.name:
                            tools_called.append(fn_call.name)

                return final_text, tools_called

            except Exception as e:
                if any(code in str(e) for code in ["503", "UNAVAILABLE", "402", "RESOURCE_EXHAUSTED", "429"]):
                    logger.warning(f"Model {current_model} error ({e}). Cascading to next fallback model...")
                    continue
                else:
                    logger.error(f"Error in Gemini agent query execution with {current_model}: {e}")
                    break


        return f"I encountered an unexpected issue processing your query: {last_error}. Please try again shortly.", tools_called

    def analyze_resident_image(
        self,
        image_bytes: bytes,
        caption: str = "",
        user_id: int = 0,
    ) -> Dict[str, Any]:
        """Analyzes an image and optional caption using Gemini Vision.
        Determines if it's a community tip submission or a visual query/troubleshooting.
        """
        if not self.client:
            intent = "RESIDENT_QUESTION"
            if "/tip" in caption.lower():
                intent = "TIP_SUBMISSION"
            elif any(k in caption.lower() for k in ["/feedback", "/bug", "bug", "feedback"]):
                intent = "FEEDBACK_SUBMISSION"
            return {
                "intent": intent,
                "topic": "general",
                "title": "Photo Submission",
                "tip": caption or "Resident submitted photo.",
                "user_reply": "📸 Photo received! In live mode, Gemini 3.8 Flash will analyze the text and details.",
            }

        image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")

        prompt = f"""
You are the Lentor Modern Digital Concierge analyzing an image sent by a resident of Lentor Modern.
The resident included this caption: "{caption}".

Evaluate the resident's intent:
1. "TIP_SUBMISSION": The resident is sharing an informative poster, retail promotion, opening hours notice, or neighbour recommendation (or they explicitly included '/tip' in the caption).
2. "FEEDBACK_SUBMISSION": The resident is reporting a bug, bot error/hallucination, screenshot of an issue, or providing feedback (or they explicitly included '/feedback' or '/bug' in the caption).
3. "RESIDENT_QUESTION": The resident is asking a question about what is shown in the image (e.g. an appliance error code on their induction hob, where something is located, a defect, or estate rule).

If TIP_SUBMISSION:
- Extract the core details from the image and caption.
- Determine the topic: one of ["mall", "services", "appliances", "bylaws", "food", "general"].
- Title: A concise title (e.g., "CS Fresh Sushi Evening Discount", "Minmed Clinic Weekend Hours").
- Tip: Clear, actionable, and structured advice for neighbours (including store unit number, floor, timings, discount percentage).
- Ensure strict PII scrubbing: DO NOT include private resident names, unit numbers (#XX-YY), or phone numbers.
- Friendly reply confirming submission to moderation.

If FEEDBACK_SUBMISSION:
- Determine the topic/category: one of ["bug", "feature_request", "data_correction", "general"].
- Title: A concise title (e.g., "Handbook Hours Inaccuracy", "Bot Display Error").
- Tip: Clear description of the bug or feedback.
- Friendly reply thanking the resident and confirming it has been delivered directly to project creator & admin @jamesjjboh.

If RESIDENT_QUESTION:
- Inspect the visual details (e.g., error code 'L' on induction cooker, defect sticker, facility sign).
- Answer the resident's question directly, referencing known estate quirks (e.g. 'L' on induction hob = child lock; hold key for 3 seconds).

Return a JSON object with this exact structure:
{{
  "intent": "TIP_SUBMISSION" or "FEEDBACK_SUBMISSION" or "RESIDENT_QUESTION",
  "topic": "mall",
  "title": "Short Title",
  "tip": "Extracted tip or feedback description (empty if RESIDENT_QUESTION)",
  "user_reply": "Message to send to resident"
}}
"""

        candidate_models = [self.model]
        for fallback in ["gemini-3.5-flash", "gemini-3.1-flash-lite"]:
            if fallback not in candidate_models:
                candidate_models.append(fallback)

        config = types.GenerateContentConfig(
            temperature=0.2,
            response_mime_type="application/json",
        )

        for current_model in candidate_models:
            try:
                response = self.client.models.generate_content(
                    model=current_model,
                    contents=[image_part, prompt],
                    config=config,
                )
                text = response.text or "{}"
                data = json.loads(text)
                return data
            except Exception as e:
                if any(code in str(e) for code in ["503", "UNAVAILABLE", "402", "RESOURCE_EXHAUSTED", "429"]):
                    logger.warning(f"Model {current_model} error ({e}) during image analysis. Cascading...")
                    continue
                else:
                    logger.error(f"Image analysis error with {current_model}: {e}")
                    break


        return {
            "intent": "RESIDENT_QUESTION",
            "topic": "general",
            "title": "Photo Analysis",
            "tip": "",
            "user_reply": "I received your photo but had trouble processing the details. Could you please try again or describe what is in the photo?",
        }



    def _simulated_response(self, user_query: str, user_id: int) -> Tuple[str, List[str]]:
        """Rule-based simulation mode for testing when Gemini API key is not yet set."""
        q_lower = user_query.lower()
        tools_called = []

        if any(w in q_lower for w in ["bylaw", "rule", "renovation", "deposit", "moving", "aircon ledge", "riser", "bbq", "gym", "hours", "parking"]):
            tools_called.append("search_bylaws_and_handbook")
            result = search_bylaws_and_handbook(user_query)
            return f"[Simulated Gemini 3.8 Flash Response]\n\nBased on official estate guidelines:\n\n{result}", tools_called

        elif any(w in q_lower for w in ["mall", "cs fresh", "supermarket", "clinic", "shop", "toast box", "mrt", "guardian"]):
            tools_called.append("search_mall_directory")
            result = search_mall_directory(shop_name=user_query)
            return f"[Simulated Gemini 3.8 Flash Response]\n\nFrom the Lentor Modern Mall directory:\n\n{result}", tools_called

        elif any(w in q_lower for w in ["tip", "advice", "hack", "trick", "discount"]):
            tools_called.append("get_verified_community_tips")
            result = get_verified_community_tips(topic=user_query)
            return f"[Simulated Gemini 3.8 Flash Response]\n\n{result}", tools_called

        elif any(w in q_lower for w in ["email", "draft", "ma", "managing agent", "complain", "feedback"]):
            tools_called.append("generate_mcst_email_draft")
            result = generate_mcst_email_draft(issue_type="Estate Feedback", details=user_query)
            return f"[Simulated Gemini 3.8 Flash Response]\n\nHere is a draft email for the Managing Agent:\n\n{result}", tools_called

        elif any(w in q_lower for w in ["school", "primary", "chij", "st nicholas", "nicholas", "anderson", "postal", "tower", "unit", "bedroom", "developer", "tenure", "top", "completion"]):
            tools_called.append("search_estate_profile")
            result = search_estate_profile(query=user_query)
            return f"[Simulated Gemini 3.8 Flash Response]\n\n{result}", tools_called

        return (
            "[Simulated Gemini 3.8 Flash Response]\n\n"
            "Hello! I am the Lentor Modern AI Concierge. You can ask me about MCST by-laws, renovation hours, "
            "mall shops & opening hours, estate specs, or verified neighbour tips. (Configure GEMINI_API_KEY to enable full live agent reasoning).",
            tools_called,
        )


# Global agent instance
concierge_agent = LentorAgent()
