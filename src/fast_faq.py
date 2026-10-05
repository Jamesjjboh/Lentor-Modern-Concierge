"""High-speed zero-shot FAQ cache for instant responses to high-frequency resident queries.

Bypasses LLM token generation for repetitive queries (<5ms response time, zero API cost),
while falling back to Gemini 3.8 Flash for nuanced or novel questions.
"""

import re
from typing import List, Optional, Tuple

# Pre-compiled regex patterns for instant matching
FAQ_RULES = [
    # 1. Gym Operating Hours
    (
        re.compile(r"\b(gym|fitness center)\b.*\b(hours?|open|timing|close|schedule)\b|\b(what time|when).*\b(gym)\b", re.IGNORECASE),
        (
            "🏋️ *Indoor Gym (Level 4 Clubhouse)*\n\n"
            "• *Operating Hours:* *6:00 AM – 10:00 PM daily*\n"
            "• _Note:_ Extended from 8:00 AM for early morning workouts! Automated door access cuts off at 10:00 PM sharp.\n"
            "• Resident access card required for glass door entry."
        ),
        ["search_bylaws_and_handbook"],
    ),
    # 2. Swimming Pool & 50m Lap Pool
    (
        re.compile(r"\b(swimming pool|lap pool|pool)\b.*\b(hours?|open|timing|close|schedule)\b|\b(what time|when).*\b(pool)\b", re.IGNORECASE),
        (
            "🏊 *Swimming Pools & 50m Lap Pool (Level 4)*\n\n"
            "• *Operating Hours:* *7:00 AM – 10:00 PM daily*\n"
            "• Proper swimwear required at all times.\n"
            "• Children under 12 must be accompanied by an adult."
        ),
        ["search_bylaws_and_handbook"],
    ),
    # 3. Tennis Court Booking & Hours
    (
        re.compile(r"\b(tennis|tennis court)\b.*\b(hours?|book|booking|open|timing|cost|fee)\b|\b(how to book|reserve).*\b(tennis)\b", re.IGNORECASE),
        (
            "🎾 *Tennis Court (Level 4)*\n\n"
            "• *Operating Hours:* *8:00 AM – 10:00 PM daily*\n"
            "• *Booking:* Reserve via the *iPlus Living* mobile app (up to 14 days in advance, 1 peak slot/week per unit).\n"
            "• Strictly non-marking tennis court shoes required."
        ),
        ["search_bylaws_and_handbook"],
    ),
    # 4. Renovation Working Hours & Noisy Works
    (
        re.compile(r"\b(reno|renovation|drilling|hacking|noisy works?)\b.*\b(hours?|timing|saturday|sunday|holiday|permit|deposit)\b|\b(can i drill|can renovate)\b", re.IGNORECASE),
        (
            "🔨 *Renovation & Noisy Works Guidelines*\n\n"
            "• *Mondays to Fridays:* *9:00 AM – 5:00 PM*\n"
            "• *Saturdays:* *9:00 AM – 1:00 PM* (Quiet non-noisy installation only)\n"
            "• *Sundays & Public Holidays:* *STRICTLY PROHIBITED* (Zero works allowed)\n"
            "• *Heavy Drilling / Hacking:* Mon–Fri 9:00 AM – 5:00 PM only.\n"
            "• *Security Deposit:* $1,000 (non-hacking) / $2,000 (hacking).\n"
            "• Loading bay clearance: 3.8m via Lentor Central ramp."
        ),
        ["search_bylaws_and_handbook"],
    ),
    # 5. First & Last Train Timings (Lentor MRT)
    (
        re.compile(r"\b(first train|last train|train timing|train timings|mrt timing|mrt timings|train schedule)\b", re.IGNORECASE),
        (
            "🚇 *Lentor MRT Station (TEL TE5) Train Timings*\n\n"
            "🟢 *Northbound (Towards Woodlands North / RTS Link):*\n"
            "• First Train: Mon–Sat `05:58` | Sun/PH `06:18`\n"
            "• Last Train: `00:27` (to Woodlands North), `00:44` (terminates at Woodlands TE2)\n\n"
            "🟢 *Southbound (Towards Bayshore / Marina Bay):*\n"
            "• First Train: Mon–Sat `05:52` | Sun/PH `06:12`\n"
            "• Last Train: `23:49` (to Bayshore), `00:05` (to Outram Park), `00:15` (to Caldecott Circle Line)\n\n"
            "Sheltered direct connection via Exit 1 to B1/L1."
        ),
        ["search_estate_profile"],
    ),
    # 6. Official Estate Paint Codes
    (
        re.compile(r"\b(paint|colour|color)\b.*\b(code|balcony|interior|wall|dulux|intermatt)\b|\b(balcony paint|official paint)\b", re.IGNORECASE),
        (
            "🎨 *Official Estate Paint Specifications*\n\n"
            "• *Balcony Wall & Ceiling:* Dulux Thick Smoke (Code: `96YR 09/033`)\n"
            "• *Interior Walls (White):* Intermatt BS E55 (White)\n\n"
            "⚠️ *Bylaw Notice:* External balcony walls and ceilings must remain painted in Dulux Thick Smoke to maintain estate facade uniformity."
        ),
        ["search_bylaws_and_handbook"],
    ),
    # 7. MCST Maintenance Fees Schedule
    (
        re.compile(r"\b(maintenance fee|maintenance fees|mcst fee|share value fee|how much maintenance)\b", re.IGNORECASE),
        (
            "💰 *Lentor Modern MCST Maintenance Fees Schedule*\n\n"
            "• *Contribution Formula:* Sub-MC (Residential) $39.00/SV + Main MC (Common Property) $5.80/SV = *$44.80/SV base* (*$48.832/SV incl. 9% GST*)\n\n"
            "• *1-Bed + Flex* (8 SV): *$358.40/mo* ($390.66 incl. GST)\n"
            "• *2-Bed + Flex* (9 SV): *$403.20/mo* ($439.49 incl. GST)\n"
            "• *3-Bed + Flex Compact* (10 SV): *$448.00/mo* ($488.32 incl. GST)\n"
            "• *3-Bed + Flex Premium* (11 SV): *$492.80/mo* ($537.15 incl. GST)\n"
            "• *4-Bed + Flex* (11 SV): *$492.80/mo* ($537.15 incl. GST)\n\n"
            "Billed quarterly via GIRO / PayNow to the MCST."
        ),
        ["search_estate_profile"],
    ),
    # 8. CS Fresh Supermarket Hours & Discounts
    (
        re.compile(r"\b(cs fresh|supermarket)\b.*\b(hours?|timing|open|close|discount|sushi)\b|\b(cold storage)\b", re.IGNORECASE),
        (
            "🛒 *CS Fresh Supermarket (Basement 1, #B1-11 to 16)*\n\n"
            "• *Operating Hours:* *08:00 – 22:00 daily*\n"
            "• 💡 *Pro-Tip:* Fresh sushi, sashimi, bento, and bakery items are marked down *20% to 30% daily after 8:30 PM*!\n"
            "• *Vouchers:* Uses Cold Storage / yuu rewards (does not accept GuocoLand mall vouchers)."
        ),
        ["search_mall_directory"],
    ),
    # 9. Primary School 1km Proximity (Anderson & St Nicholas)
    (
        re.compile(r"\b(primary school|schools? within 1km|1km school|anderson primary|chij st nicholas)\b", re.IGNORECASE),
        (
            "🏫 *Official Primary School Distance (Home-School Distance)*\n\n"
            "• *Within 1km (<1km):*\n"
            "  ⭐ *Anderson Primary School* is strictly the *ONLY* primary school within 1km of Lentor Modern.\n\n"
            "• *Within 1km to 2km (1–2km band):*\n"
            "  • CHIJ St. Nicholas Girls' School (Primary)\n"
            "  • Mayflower Primary School\n"
            "  • Ang Mo Kio Primary School\n\n"
            "Verified against official Singapore Land Authority (SLA) OneMap distance parameters."
        ),
        ["search_estate_profile"],
    ),
    # 10. Developer, Tenure & Specifications
    (
        re.compile(r"\b(developer|who is developer|tenure|is it freehold|how many units|postal code)\b", re.IGNORECASE),
        (
            "🏢 *Lentor Modern Project Specifications*\n\n"
            "• *Developer:* GuocoLand Limited (Lentor Modern Pte. Ltd.)\n"
            "• *Tenure:* 99-year leasehold (commencing 2020)\n"
            "• *Total Residential Units:* 605 units across 3 towers of 25 storeys\n"
            "• *Postal Codes:*\n"
            "  • Tower 3: 3 Lentor Central S(788888)\n"
            "  • Tower 5: 5 Lentor Central S(788889)\n"
            "  • Tower 7: 7 Lentor Central S(788890)\n"
            "• *Integration:* Direct sheltered link to Lentor Modern Mall & Lentor MRT (TE5)."
        ),
        ["search_estate_profile"],
    ),
]


def match_fast_faq(user_query: str) -> Optional[Tuple[str, List[str]]]:
    """Matches common high-frequency resident questions against the fast zero-shot index.
    Returns (response_text, tools_called) if matched, or None if Gemini should handle it.
    """
    clean_q = (user_query or "").strip()
    if len(clean_q) < 3 or len(clean_q) > 150:
        return None

    for pattern, response_text, tools_called in FAQ_RULES:
        if pattern.search(clean_q):
            return response_text, tools_called

    return None
