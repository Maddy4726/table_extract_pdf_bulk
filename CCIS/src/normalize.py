"""Normalize airport/city names across issuer lounge lists."""

from __future__ import annotations

import re

CITY_ALIASES: dict[str, str] = {
    "bangalore": "Bengaluru",
    "bengaluru": "Bengaluru",
    "blr": "Bengaluru",
    "new delhi": "New Delhi",
    "delhi": "New Delhi",
    "cochin": "Kochi",
    "kochi": "Kochi",
    "goa": "Goa",
    "pernem": "Goa",
    "dabolim": "Goa",
    "manohar international": "Goa",
    "allahabad": "Prayagraj",
    "prayagraj": "Prayagraj",
    "thiruvananthapuram": "Trivandrum",
    "trivandrum": "Trivandrum",
    "vizag": "Visakhapatnam",
    "visakhapatnam": "Visakhapatnam",
    "bhubaneshwar": "Bhubaneswar",
    "bhubaneswar": "Bhubaneswar",
    "siliguri": "Bagdogra",
    "bagdogra": "Bagdogra",
    "calicut": "Calicut",
    "kozhikode": "Calicut",
    "dehra dun": "Dehradun",
    "dehradun": "Dehradun",
    "mumbai": "Mumbai",
    "chennai": "Chennai",
    "hyderabad": "Hyderabad",
    "kolkata": "Kolkata",
    "ahmedabad": "Ahmedabad",
    "jaipur": "Jaipur",
    "lucknow": "Lucknow",
    "pune": "Pune",
    "raipur": "Raipur",
    "ranchi": "Ranchi",
    "nagpur": "Nagpur",
    "indore": "Indore",
    "chandigarh": "Chandigarh",
    "amritsar": "Amritsar",
    "guwahati": "Guwahati",
    "srinagar": "Srinagar",
    "varanasi": "Varanasi",
    "vadodara": "Vadodara",
    "coimbatore": "Coimbatore",
    "madurai": "Madurai",
    "jammu": "Jammu",
    "gwalior": "Gwalior",
    "bhopal": "Bhopal",
    "agartala": "Agartala",
    "ayodhya": "Ayodhya",
    "dibrugarh": "Dibrugarh",
    "kannur": "Kannur",
    "rajkot": "Rajkot",
    "patna": "Patna",
}


def normalize_city(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return ""
    key = text.lower()
    if key in CITY_ALIASES:
        return CITY_ALIASES[key]
    # Strip airport suffix noise
    for suffix in (" International Airport", " Airport", " Intl"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
            key = text.lower()
            if key in CITY_ALIASES:
                return CITY_ALIASES[key]
    return text.title() if text.islower() else text


def slug_city(value: str) -> str:
    city = normalize_city(value)
    return re.sub(r"[^a-z0-9]+", "_", city.lower()).strip("_")
