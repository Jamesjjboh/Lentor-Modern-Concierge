"""High-speed zero-shot FAQ cache for instant responses to high-frequency resident queries.

Bypasses LLM token generation for repetitive queries (<5ms response time, zero API cost),
while falling back to Gemini 3.8 Flash for nuanced or novel questions.
"""

import json
import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from src.config import PROCESSED_DATA_DIR

logger = logging.getLogger(__name__)

# Preload mall directory stores for instant discount lookup
_MALL_STORES: List[Dict[str, Any]] = []
try:
    mall_path = PROCESSED_DATA_DIR / "mall_directory.json"
    if mall_path.exists():
        with open(mall_path, "r", encoding="utf-8") as f:
            _MALL_STORES = json.load(f)
except Exception as e:
    logger.warning(f"Could not preload mall_directory.json in fast_faq: {e}")

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
        re.compile(r"\b(tennis court)\b|\btennis\b.*\b(hours?|book|booking|open|timing|cost|fee)\b|\b(how to book|reserve).*\btennis\b", re.IGNORECASE),
        (
            "🎾 *Tennis Court (Level 4)*\n\n"
            "• *Operating Hours:* *8:00 AM – 10:00 PM daily*\n"
            "• *Booking:* Reserve via the *iPlus Living* mobile app (up to 14 days in advance, 1 peak slot/week per unit).\n"
            "• Strictly non-marking tennis court shoes required."
        ),
        ["search_bylaws_and_handbook"],
    ),
    # 4. Games Room, Table Tennis, Pool Table & Darts
    (
        re.compile(
            r"\b(table tennis|ping\s*pong|games?\s*room|darts?|pool table|billiard|dance\s*studio|dance\s*room)\b",
            re.IGNORECASE,
        ),
        (
            "🎯 *Games Room & Amenities (Level 4 Clubhouse)*\n\n"
            "• *Location:* Level 4 Clubhouse (located right beside the Dance Studio).\n"
            "• *Operating Hours:* *Until 10:00 PM daily*.\n\n"
            "🏓 *What is available inside:*\n"
            "• *Multi-Function Convertible Table:* Functions as both a *Table Tennis (Ping Pong)* table and a *Pool / Billiard* table!\n"
            "• *Electronic Dart Board:* Available for residents.\n"
            "• *Dance Studio:* Located adjacent to the Games Room with wall mirrors for dance and yoga.\n\n"
            "📱 *Booking:* Reserve your slot via the *iPlus Living* mobile app under Facility Booking."
        ),
        ["search_bylaws_and_handbook"],
    ),
    # 5. Business Lounge, Co-Working Space & Meeting Room
    (
        re.compile(
            r"\b(co[\s-]*working|coworking|business lounge|meeting room|work booth|study room|work lounge|hot[\s-]*desking)\b|\bwhere (can i|to) (work|study)\b",
            re.IGNORECASE,
        ),
        (
            "💼 *Business Lounge, Co-Working Space & Meeting Room (Level 4 Clubhouse)*\n\n"
            "• *Location:* Level 4 Grand Clubhouse\n"
            "• *Operating Hours:* *Until 10:00 PM daily*\n\n"
            "💻 *Work & Productivity Amenities:*\n"
            "• *Hot-Desking & Work Booths:* Private semi-enclosed acoustic work booths and window counters designed for focused solo work, study, and video calls (open walk-in access for residents).\n"
            "• *Enclosed Meeting Room:* Dedicated 6-person private conference room equipped for business discussions, group work, and presentations.\n"
            "• *Level 14 Sky Club:* Additional work corners and club lounge seating across Towers 3, 5, and 7.\n\n"
            "📱 *Facility Booking (iPlus Living):*\n"
            "• *Hot-desking booths & open tables:* Free walk-in access (no booking required).\n"
            "• *6-Person Meeting Room:* Reserve your slot via the *iPlus Living* mobile app under Facility Booking."
        ),
        ["search_bylaws_and_handbook"],
    ),
    # 6. Renovation Working Hours & Noisy Works
    (
        re.compile(r"\b(reno|renovation|hacking|noisy works?)\b.*\b(hours?|timing|saturday|sunday|holiday|permit|deposit)\b|\bcan renovate\b", re.IGNORECASE),
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
    # 11. Physical Concierge Desk Operating Hours
    (
        re.compile(r"\b(physical concierge|concierge desk|concierge counter|concierge)\b.*\b(hours?|open|opened|timing|close|closing|until|schedule)\b|\b(what time|when).*\b(concierge)\b", re.IGNORECASE),
        (
            "🛎️ *Lentor Modern Physical Concierge Desk (Level 4 Clubhouse)*\n\n"
            "• *Physical Counter Hours:* *9:00 AM – 8:00 PM daily*\n"
            "  _(For in-person inquiries, car decal collection, visitor reception, parcel assistance)_\n"
            "• *Telephone:* +65 6054 3375\n"
            "• *Email:* concierge@LT-MODERN.COM\n\n"
            "🌙 *After 8:00 PM / Late Night Assistance:*\n"
            "• The physical desk counter is unstaffed after 8:00 PM.\n"
            "• For urgent estate issues or night entry assistance, please contact *24/7 Security Control at +65 6054 3379*."
        ),
        ["search_bylaws_and_handbook", "search_estate_profile"],
    ),
    # 12. Defect Liability Period (DLP) & Handover Defects (Novade)
    (
        re.compile(
            r"\b(dlp|defect liability|defects? liability period|novade|novade quality)\b|\b(when|what time|until when|last day|deadline)\b.*\b(defect|defects|dlp)\b|\b(defect|defects|dlp)\b.*\b(end|ends|expiry|expire|expires|over|deadline)\b|\bhow to (report|lodge).*defect\b",
            re.IGNORECASE,
        ),
        (
            "🛠️ *Lentor Modern Defect Liability Period (DLP)*\n\n"
            "• *Individual Unit DLP:* Strictly *12 months from your individual Key Collection / Notice of Vacant Possession (NVP) date* under the BCA S&P Agreement.\n"
            "  _(Check your exact unit expiry date inside the *Novade Quality* app or confirm with your Block Manager)_\n\n"
            "• *Development & Common Property DLP:* *25 February 2027* _(Confirmed by CBRE Management Office)_\n"
            "  _(Covers external wall façade, corridors, swimming pools, clubhouse, landscape deck, and lifts)_\n\n"
            "📱 *How to Report Defects via Novade:*\n"
            "1. *Download the App:*\n"
            "   • [Apple App Store (iOS)](https://apps.apple.com/app/id1579805253)\n"
            "   • [Google Play Store (Android)](https://play.google.com/store/apps/details?id=com.novade.field)\n"
            "2. *Log In:* Use the login credentials provided during key collection / NVP.\n"
            "3. *Lodge Defect:* Select your unit and room, attach clear close-up & wide photos, and submit.\n"
            "4. *Track Status:* `Pending Contractor` ➔ `Under Rectification` ➔ `Ready for Joint Inspection`.\n\n"
            "🏢 *Common Property Defects:*\n"
            "• Report common area defects (lifts, pools, facade) directly to CBRE Management Office (`+65 6054 3370` / `managementoffice@LT-MODERN.COM`).\n\n"
            "📞 *GuocoLand Customer Service Team (CST):* `6433 9342` | `LMcustomerservice@lentormodern.com.sg` (Mon–Fri 9am–6pm)."
        ),
        ["search_bylaws_and_handbook", "search_estate_profile"],
    ),
    # 13. Lift Faults, Health Check & Emergency Breakdown
    (
        re.compile(
            r"\b(lift|lifts|elevator|elevators|tke|tk elevator)\b.*\b(issue|issues|fault|faults|breakdown|break\s*downs?|break\s*down|stuck|trap|trapped|jerk|jerky|sensor|slow|spoil|spoilt|broken|health check|not working)\b|\b(report|broken)\b.*\b(lift|elevator)\b",
            re.IGNORECASE,
        ),
        (
            "🛗 *Lift Issues & Fault Reporting (TK Elevator / TKE)*\n\n"
            "• *24/7 Emergency Lift Rescue:* `+65 6890 1640`\n"
            "  _(TK Elevator emergency hotline if someone is trapped or urgent breakdown)_\n\n"
            "• *Ongoing Rectifications:* Management completed a comprehensive lift health check across all towers, and TKE is conducting ongoing rectifications.\n\n"
            "📋 *How to Report Lift Faults to Management:*\n"
            "Send an email to `managementoffice@LT-MODERN.COM` or call `+65 6054 3370` with these *4 details*:\n"
            "1. *Tower & lift identification* (e.g. Tower 3 Passenger Lift 1, Service Lift)\n"
            "2. *Date & time* of the incident\n"
            "3. *Brief description* of issue (e.g. jerky motion, levelling gap, delayed doors, unlit buttons)\n"
            "4. *Photo or video* (if available)\n\n"
            "Management compiles all reports directly with TKE for technical investigation."
        ),
        ["search_bylaws_and_handbook"],
    ),
    # 14. Rubbish / Refuse Chute Stuck or Choked
    (
        re.compile(
            r"\b(rubbish|refuse|trash|garbage)\b.*\b(chute|chutes)\b|\b(chute|chutes)\b.*\b(stuck|choke|choked|jam|jammed|spoil|spoilt|broken|block|blocked|full|smell|cannot open)\b|\b(chute\s*stuck|stuck\s*chute|choked?\s*chute)\b|\bwhere to (throw|dump|dispose).*(big|bulky|large|box|boxes|rubbish|trash)\b",
            re.IGNORECASE,
        ),
        (
            "🗑️ *Rubbish & Refuse Chute Stuck / Choked Guidelines*\n\n"
            "If your floor's rubbish or recycling chute is jammed, stuck, or won't open:\n\n"
            "🚨 *1. Immediate Reporting to Clear the Choke:*\n"
            "• *Office Hours (Mon–Fri 9am–6pm, Sat 9am–1pm):*\n"
            "  Contact *CBRE Management Office* at `+65 6054 3370` or email `managementoffice@LT-MODERN.COM` with your *Tower & Floor/Level* so the estate cleaning team can clear it immediately.\n"
            "• *After Hours, Sundays & Urgent Emergencies:*\n"
            "  Contact *24/7 Security Control* at `+65 6054 3379` to dispatch duty officers.\n\n"
            "📦 *2. Temporary Disposal (Level 2 Bin Area):*\n"
            "• *DO NOT leave rubbish bags outside the chute or along the common corridor* (this creates severe foul odors, cockroaches, and pest infestations for corridor neighbours).\n"
            "• Please take the lift down to the *Level 2 Bin Area* to dispose of accumulated rubbish or recyclables.\n\n"
            "💡 *3. Choke Prevention Guidelines:*\n"
            "• The chute hopper opening is compact (requires pulling past 45°).\n"
            "• *Never force or squeeze oversized trash bags, rigid delivery boxes, or stiff paper/tote bags* into the chute—they get wedged inside the vertical barrel.\n"
            "• Flatten all cardboard delivery boxes and bring bulky trash directly down to Level 2."
        ),
        ["search_bylaws_and_handbook"],
    ),
    # 15. Electric Vehicle (EV) Charging Stations & Rates
    (
        re.compile(
            r"\b(ev\s*charg\w*|electric vehicle|charge\s*car|ev\s*station|novowatt|watt\s*app)\b|\b(charge|charging)\b.*\b(ev|car|vehicle|mall|resident)\b",
            re.IGNORECASE,
        ),
        (
            "⚡ *Electric Vehicle (EV) Charging at Lentor Modern*\n\n"
            "🚗 *1. Resident Carpark (Level 3 under Block 3):*\n"
            "• *Exclusivity:* Strictly for Lentor Modern residents (behind barrier ramp).\n"
            "• *Lots:* 5 dedicated EV lots.\n"
            "• *Operator:* *Novowatt* (App: *Watt - EV Charging* | 24/7 Hotline: `+65 6537 7333`).\n"
            "• *Charging Rate:* *~$0.50 / kWh* (pay-per-use; zero carpark hourly fees for resident vehicles).\n\n"
            "🛒 *2. Mall Carpark (Basement 1, Lots 39–42):*\n"
            "• *Access:* Open to *both residents and the public*.\n"
            "• *Lots:* 4 AC charging lots.\n"
            "• *Operator:* *SP Mobility* (billed via the *SP App*).\n"
            "• *Charging Rate:* *~$0.75 – $0.81 / kWh* (SP Group EV tariff).\n"
            "• *Carpark Fees:* Normal mall parking rates apply ($1.20 1st hr, $0.50/30m thereafter; 10-min free grace period).\n\n"
            "💡 *Tip:* Level 3 Resident Carpark (~$0.50/kWh, no parking fees) is significantly cheaper than B1 Mall Carpark!"
        ),
        ["search_bylaws_and_handbook"],
    ),
    # 14. Security Control Room, Guardhouse & Management Contacts
    (
        re.compile(
            r"\b(security numbers?|guard\s*house numbers?|guardhouse|security control|security hotline|call security)\b|\b(what is|how to call|phone number of|contact for|number of|number for)\b.*\b(security|guardhouse|guard house)\b",
            re.IGNORECASE,
        ),
        (
            "🛡️ *Lentor Modern Security & Estate Hotlines*\n\n"
            "• *24/7 Security Control Room / Guardhouse:* `+65 6054 3379`\n"
            "  _(Available 24 hours daily for urgent emergencies, barrier gate issues, noise complaints, and visitor verification)_\n\n"
            "• *Managing Agent (CBRE Management Office):* `+65 6054 3370`\n"
            "  • Location: 9 Lentor Central, Level 3\n"
            "  • Hours: Mon–Fri 9:00 AM – 6:00 PM | Sat 9:00 AM – 1:00 PM (Closed Sun & PH)\n"
            "  • Email: managementoffice@LT-MODERN.COM\n\n"
            "• *On-Site Concierge Desk:* `+65 6054 3375`\n"
            "  • Location: Level 4 Clubhouse\n"
            "  • Hours: 9:00 AM – 8:00 PM daily\n"
            "  • Email: concierge@LT-MODERN.COM\n\n"
            "• *Intercom & Access Hardware Support (Fermax Asia):* `+65 6259 0700`\n"
            "  _(Developer supplier for video intercom and resident access card technical support)_"
        ),
        ["search_bylaws_and_handbook", "search_estate_profile"],
    ),
    # 14. High-Rise Littering & Smoking Regulations
    (
        re.compile(
            r"\b(cig|cigarette|smoking|smoke|cigs|ash|butts?)\b.*\b(window|balcony|throw|litter|toss|outside)\b|\b(throw|drop|litter|toss)\b.*\b(window|balcony|corridor)\b|\bhigh\s*rise littering\b",
            re.IGNORECASE,
        ),
        (
            "🚭 *Smoking & High-Rise Littering By-Laws*\n\n"
            "• *Strictly Prohibited:* Discarding cigarette butts, ash, or any rubbish from windows, balconies, or service yards is *strictly illegal* under the Environmental Public Health Act (EPHA) and estate by-laws.\n\n"
            "• *Severe Legal Penalties (NEA):*\n"
            "  • Under NEA laws, a *statutory presumption* applies to the registered unit owner/tenant if litter originates from their unit.\n"
            "  • Fines: Up to *$2,000* for the first court conviction, *$4,000* for the second, and up to *$10,000* for subsequent convictions, alongside Corrective Work Orders (CWO).\n"
            "  • Discarding burning butts also creates severe fire hazards for lower-floor balconies.\n\n"
            "• *Common Area Smoking:* Smoking is prohibited in all estate common property (corridors, lobbies, stairwells, pool deck, gym, BBQ pavilions).\n\n"
            "• *Reporting Incidents:* To report offenders, note the tower, approximate floor/unit, and timestamp, and contact the Management Office (CBRE: `+65 6054 3370`) or file via the *NEA myENV* app."
        ),
        ["search_bylaws_and_handbook"],
    ),
    # 15. Minor Drilling & DIY Works vs Renovation Permit
    (
        re.compile(
            r"\b(can i drill|drill wall|drilling|hang.*painting|mount.*tv|drill.*hole|minor works?)\b",
            re.IGNORECASE,
        ),
        (
            "🔨 *Minor Drilling & DIY Works Guidelines*\n\n"
            "• *Do I need a Renovation Permit for simple drilling?*\n"
            "  • *No formal permit/deposit needed:* Minor DIY drilling inside your unit (e.g. drilling a few holes to hang paintings, mirrors, curtain tracks, or mount a TV) does *not* require an MCST Renovation Permit (Form 2.0) or renovation deposit.\n\n"
            "• *Strict Working Hours for Drilling & Noisy Works:*\n"
            "  • *Monday to Friday:* 9:00 AM – 5:00 PM\n"
            "  • *Saturday:* 9:00 AM – 1:00 PM\n"
            "  • *Sundays & Public Holidays:* *STRICTLY PROHIBITED*\n\n"
            "⚠️ *Safety Caution:* Use a stud/pipe detector or check architectural plans before drilling to avoid concealed electrical conduits, aircon refrigerant trunking, or water pipes embedded inside the walls!"
        ),
        ["search_bylaws_and_handbook"],
    ),
    # 16. QB Premium Resident Discount & Queue
    (
        re.compile(r"\b(qb\s*premium|qb\s*house|qb)\b.*\b(discount|promo|perk|resident|offer|deal|cut|hair|queue)\b|\b(discount|promo|perk|resident|offer|deal)\b.*\b(qb\s*premium|qb\s*house|qb)\b", re.IGNORECASE),
        (
            "✂️ *QB PREMIUM (#01-45)*\n\n"
            "• *Resident Discount:* *$3 off all haircuts*\n"
            "• *How to Redeem:* Flash your physical *Lentor Modern Resident Access Card* prior to payment.\n"
            "• *Validity:* Till 31 December 2026 (not valid with other promotions).\n"
            "• *Operating Hours:* 10:00 – 21:30 daily\n"
            "• 💡 *Live Queue:* Check live queue and get digital queue ticket online before walking down:\n"
            "  https://qbhouse.relsystems.net:443/RELGetQueueLM.aspx?brCode=QDCOJEFZ"
        ),
        ["search_mall_directory"],
    ),
    # 12. Jew Kit Hainanese Chicken Rice Resident Discount
    (
        re.compile(r"\b(jew kit|chicken rice)\b.*\b(discount|promo|perk|resident|offer|deal|have)\b|\b(discount|promo|perk|resident|offer|deal)\b.*\b(jew kit|chicken rice)\b", re.IGNORECASE),
        (
            "🍗 *Jew Kit Hainanese Chicken Rice (#B1-04)*\n\n"
            "• *Resident Discount:* *15% off total bill*\n"
            "• *How to Redeem:* Flash your physical *Lentor Modern Resident Access Card* prior to making payment.\n"
            "• *Validity:* Till 31 December 2026 (not combinable with other ongoing promotions).\n"
            "• *Operating Hours:* 10:00 – 21:30 daily"
        ),
        ["search_mall_directory"],
    ),
    # 13. KFC Resident Discount
    (
        re.compile(r"\b(kfc)\b.*\b(discount|promo|perk|resident|offer|deal)\b|\b(discount|promo|perk|resident|offer|deal)\b.*\b(kfc)\b", re.IGNORECASE),
        (
            "🍗 *KFC (#01-21/22)*\n\n"
            "• *Resident Discount:* *15% off with minimum spending of $15* (dine-in & takeaway).\n"
            "• *How to Redeem:* Flash your physical *Lentor Modern Resident Access Card* at the counter before payment.\n"
            "• *Operating Hours:* 10:00 – 21:30 daily"
        ),
        ["search_mall_directory"],
    ),
    # 14. Tim Hortons Resident Discount
    (
        re.compile(r"\b(tim hortons?|tims?)\b.*\b(discount|promo|perk|resident|offer|deal)\b|\b(discount|promo|perk|resident|offer|deal)\b.*\b(tim hortons?|tims?)\b", re.IGNORECASE),
        (
            "☕ *Tim Hortons (#01-37)*\n\n"
            "• *Resident Discount:* *15% off with minimum spending of $15*\n"
            "• *How to Redeem:* Flash your physical *Lentor Modern Resident Access Card* prior to ordering.\n"
            "• *Operating Hours:* 10:00 – 21:30 daily"
        ),
        ["search_mall_directory"],
    ),
    # 15. Burger King Resident Discount
    (
        re.compile(r"\b(burger king|bk)\b.*\b(discount|promo|perk|resident|offer|deal)\b|\b(discount|promo|perk|resident|offer|deal)\b.*\b(burger king|bk)\b", re.IGNORECASE),
        (
            "🍔 *Burger King (#01-14/15)*\n\n"
            "• *Resident Discount:* *10% off total bill*\n"
            "• *How to Redeem:* Flash your physical *Lentor Modern Resident Access Card* prior to ordering.\n"
            "• *Operating Hours:* 10:00 – 21:30 daily"
        ),
        ["search_mall_directory"],
    ),
    # 16. General Resident Discounts & Perks Overview
    (
        re.compile(r"\b(what|which|list|all)\b.*\b(resident discounts?|mall discounts?|resident perks?)\b|\bresident perks\b|\ball discounts\b|\blist of discounts\b", re.IGNORECASE),
        (
            "🏷️ *Lentor Modern Resident Discounts & Perks Overview*\n\n"
            "Flash your physical *Lentor Modern Resident Access Card* prior to payment to enjoy:\n\n"
            "🍽️ *F&B & Dining:*\n"
            "• *Jew Kit Chicken Rice (#B1-04):* 15% off total bill\n"
            "• *KFC (#01-21/22):* 15% off with min. $15 spend\n"
            "• *Tim Hortons (#01-37):* 15% off with min. $15 spend\n"
            "• *Burger King (#01-14/15):* 10% off total bill\n"
            "• *Tongue Tip Lanzhou Beef Noodles (#01-38):* 15% off à la carte\n"
            "• *Toast & Roll by Swee Heng (#01-23):* 5% off total bill\n"
            "• *Joylion Buffet Hotpot (#B1-08):* 10% off dine-in\n"
            "• *Ajumma's (#01-30):* Free hotteok with min. $45 spend\n\n"
            "✂️ *Hair & Services:*\n"
            "• *QB PREMIUM (#01-45):* $3 off all haircuts\n"
            "• *NK Hairworks (#01-28):* 20% off selected services\n"
            "• *The Nail Arcadia (#01-47):* 10% off all services\n\n"
            "🩺 *Health & Clinic:*\n"
            "• *Pinnacle Family Clinic (#01-46):* Screenings from $99, Flu vaccine $33\n"
            "• *Luminous Dental (#01-49):* Basic dental care at $98\n"
            "• *Ma Kuang TCM (#01-12):* 5% off services\n\n"
            "🛒 *Supermarket:*\n"
            "• *CS Fresh (#B1-11 to 16):* 20%–30% markdown on sushi/bento after 8:30 PM\n\n"
            "_You can also ask about any specific store (e.g. 'discount for QB Premium')!_"
        ),
        ["search_mall_directory"],
    ),
    # 17. Digital Door Lock (Yale YDM7116A) Manual, PIN Code Setup & Yale Home App
    (
        re.compile(
            r"\b(yale|door lock|digital lock|main door lock|yale lock|ydm7116a)\b.*\b(manual|code|pin|app|download|ios|apple|android|user manual|change|set|reset|battery|jumpstart|flat)\b|\b(set|change|reset)\b.*\b(code|pin|password)\b|\b(user manual|manual)\b.*\b(lock|door)\b|\bis there an app for this lock\b|\blink to the app store\b|\bhow to (set|change|reset).*(door|lock|pin|code)\b",
            re.IGNORECASE,
        ),
        (
            "🚪 *Main Door Digital Lock (Yale YDM7116A)*\n\n"
            "🔑 *How to Set or Change Your User PIN Code:*\n"
            "1. Remove the battery cover on the *inside (interior)* of your main door.\n"
            "2. Press the physical *`[I]` (Registration)* button once.\n"
            "3. On the exterior keypad, enter your new *4 to 10-digit User PIN code*.\n"
            "4. Press the *`[I]` (Registration)* button again on the interior body to complete registration.\n"
            "   _(If in Master Mode: Press `[I]` ➔ Enter Master PIN ➔ `#` ➔ Press `1` ➔ Enter New PIN ➔ `*` ➔ Press `[I]` to confirm)_\n\n"
            "📱 *Mobile App (Yale Home):*\n"
            "• The official app for Singapore is **Yale Home** (Assa Abloy). _Note: The older 'Yale Access' app was discontinued in Singapore in mid-2023._\n"
            "• 🍏 [Apple App Store (iOS)](https://apps.apple.com/sg/app/yale-home/id1436055535)\n"
            "• 🤖 [Google Play Store (Android)](https://play.google.com/store/apps/details?id=com.assaabloy.yale)\n"
            "• _Note:_ Mobile phone pairing requires the Yale Bluetooth/BLE module installed in the slot behind the battery cover.\n\n"
            "📖 *Official User Manual (PDF):*\n"
            "• [Download Yale YDM7116A User Manual](https://www.yalehome.com/content/dam/yale-home/apac/products/digital-door-lock/ydm7116a/Yale%20YDM7116A%20User%20Manual.pdf)\n\n"
            "🔋 *Emergency Battery Jumpstart:*\n"
            "• If batteries are completely flat and you are locked out, touch a standard *9V rectangular battery* to the emergency terminals at the bottom of the exterior handle, then enter your PIN or scan fingerprint.\n\n"
            "📞 *Assa Abloy (Yale Singapore Hotline):* `+65 6591 8868` | `support.sg@yalesmart.com`"
        ),
        ["search_bylaws_and_handbook"],
    ),
]

DISCOUNT_KEYWORDS = re.compile(
    r"\b(discount|discounts|promo|promos|promotion|promotions|perk|perks|offer|offers|deal|deals|cheaper|voucher|vouchers|privilege|privileges)\b",
    re.IGNORECASE,
)


def _normalize_text(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ASCII", "ignore").decode("utf-8").lower()


def _format_store_discount(store: Dict[str, Any]) -> str:
    name = store.get("name", "Store")
    unit = store.get("unit", "")
    disc = store.get("resident_discount")
    terms = store.get("discount_terms") or "Flash Lentor Modern Resident Access Card prior to payment. Valid until 31 Dec 2026. Not valid with other promotions."
    hours = store.get("opening_hours", "Daily")
    order_url = store.get("order_url")

    cat = (store.get("category") or "").lower()
    emoji = "🛍️"
    if "hair" in cat or "hair" in name.lower() or "nail" in cat:
        emoji = "✂️"
    elif any(k in cat for k in ["f&b", "food", "restaurant", "dining", "cafe"]):
        emoji = "🍽️"
    elif any(k in cat for k in ["clinic", "medical", "dental", "health", "tcm"]):
        emoji = "🩺"
    elif any(k in cat for k in ["enrichment", "school", "music", "education"]):
        emoji = "📚"
    elif "supermarket" in cat:
        emoji = "🛒"

    if disc:
        lines = [
            f"{emoji} *{name} ({unit})*\n",
            f"• *Resident Discount:* {disc}",
            f"• *How to Redeem:* Flash your physical *Lentor Modern Resident Access Card* prior to making payment.",
            f"• *Terms:* {terms}",
            f"• *Operating Hours:* {hours}",
        ]
        if order_url:
            if "qb" in name.lower():
                lines.append(f"• 💡 *Live Queue:* Check live queue and get digital queue ticket online before walking down:\n  {order_url}")
            else:
                lines.append(f"• 💡 *Order / Queue Online:* {order_url}")
        return "\n".join(lines)
    else:
        lines = [
            f"{emoji} *{name} ({unit})*\n",
            f"• *Resident Discount:* Does not currently offer a specific resident discount.",
            f"• *Operating Hours:* {hours}",
            f"• *Floor:* {store.get('floor', '')}",
            f"• _Tip:_ You can check mall customer service or the Lentor Modern directory for seasonal atrium promotions!",
        ]
        return "\n".join(lines)


def match_store_discount(clean_q: str) -> Optional[Tuple[str, List[str]]]:
    """Dynamically matches any store resident discount question across all stores in mall_directory.json."""
    if not _MALL_STORES:
        return None

    norm_q = _normalize_text(clean_q)
    if not DISCOUNT_KEYWORDS.search(norm_q):
        return None

    for store in _MALL_STORES:
        name = store.get("name", "")
        norm_name = _normalize_text(name)

        aliases = [norm_name]
        simplified = re.sub(r"\s*\([^)]*\)", "", norm_name)
        simplified = re.sub(r":.*$", "", simplified)
        simplified = re.sub(r"\s+by\s+.*$", "", simplified)
        if simplified != norm_name and len(simplified) >= 3:
            aliases.append(simplified)

        if "chicken rice" in norm_name:
            aliases.append("jew kit")
        if "tcm" in norm_name:
            aliases.append("ma kuang")
        if "qb premium" in norm_name:
            aliases.extend(["qb", "qb house", "qb premium"])
        if "tim hortons" in norm_name:
            aliases.extend(["tim horton", "tims", "tim hortons"])
        if "burger king" in norm_name:
            aliases.extend(["bk", "burger king"])
        if "cs fresh" in norm_name or "cold storage" in norm_name:
            aliases.extend(["cs fresh", "cold storage"])

        for alias in sorted(set(aliases), key=len, reverse=True):
            if len(alias) < 3:
                continue
            pattern = r"\b" + re.escape(alias) + r"\b"
            if re.search(pattern, norm_q):
                return _format_store_discount(store), ["search_mall_directory"]

    return None


def match_fast_faq(user_query: str) -> Optional[Tuple[str, List[str]]]:
    """Matches common high-frequency resident questions against the fast zero-shot index.
    Returns (response_text, tools_called) if matched, or None if Gemini should handle it.
    """
    clean_q = (user_query or "").strip()
    if len(clean_q) < 3 or len(clean_q) > 150:
        return None

    # 1. Check explicit FAQ rules first
    for pattern, response_text, tools_called in FAQ_RULES:
        if pattern.search(clean_q):
            return response_text, tools_called

    # 2. Check dynamic mall store discount matcher across all stores
    store_match = match_store_discount(clean_q)
    if store_match:
        return store_match

    return None
