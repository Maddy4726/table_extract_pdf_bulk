"""Official lounge list data compiled from issuer sources."""

from __future__ import annotations

from src.normalize import normalize_city

# Axis Rewards — Set A (official Axis PDF, May 2024 program)
AXIS_SET_A_LOUNGES = [
    ("Bengaluru", "BLR Domestic Lounge", "T1", "Domestic"),
    ("Bengaluru", "080 Domestic Lounge", "T2", "Domestic"),
    ("Chennai", "Travel Club Lounge A/B", "T1", "Domestic"),
    ("Chennai", "Travel Club Lounge", "T4", "Domestic"),
    ("Mumbai", "Travel Club Lounge", "T1C", "Domestic"),
    ("Mumbai", "Adani Lounge", "T2", "Domestic"),
    ("Kolkata", "Travel Club Lounge", "T1", "Domestic"),
    ("Hyderabad", "Encalm Lounge", "T1", "Domestic"),
    ("New Delhi", "Encalm Lounge", "T1", "Domestic"),
    ("New Delhi", "Encalm Lounge", "T2", "Domestic"),
    ("New Delhi", "Encalm Lounge", "T3", "Domestic"),
]

# DBS SuperCard — official T&C page (DreamFolks domestic list)
DBS_SUPERCARD_LOUNGES = [
    ("Agartala", "Primus Lounge", "Main Terminal", "Domestic"),
    ("Ahmedabad", "The Lounge", "T1", "Domestic"),
    ("Prayagraj", "Zesto Lounge", "T1", "Domestic"),
    ("Amritsar", "Primus Lounge", "T1", "Domestic"),
    ("Bengaluru", "080 Dom T1 Departure", "T1", "Domestic"),
    ("Bengaluru", "080 Dom T2 Departure", "T2", "Domestic"),
    ("Bengaluru", "Blr Dom T1 Departure", "T1", "Domestic"),
    ("Bhopal", "Primus Lounge", "T1", "Domestic"),
    ("Bhubaneswar", "Bird Lounge", "T1", "Domestic"),
    ("Calicut", "Bird Lounge", "T1", "International"),
    ("Chandigarh", "Primus Lounge", "Main Terminal", "Domestic"),
    ("Chennai", "Travel Club Lounge A Dom T1", "T1", "Domestic"),
    ("Chennai", "Travel Club Lounge B Dom T1", "T1", "Domestic"),
    ("Chennai", "Travel Club Lounge Dom T4", "T4", "Domestic"),
    ("Coimbatore", "Blackberry Lounge", "T1", "Domestic"),
    ("Dehradun", "Bird Lounge", "T1", "Domestic"),
    ("Dibrugarh", "Saptagiri Restaurant", "T1", "Domestic"),
    ("Goa", "Encalm Lounge Dom T1", "T1", "Domestic"),
    ("Guwahati", "The Lounge", "T1", "Domestic"),
    ("Gwalior", "Paahun Executive Lounge", "Main Terminal", "Domestic"),
    ("Hyderabad", "Encalm Lounge Dom T1", "T1", "Domestic"),
    ("Indore", "Primus Lounge", "T1", "Domestic"),
    ("Jaipur", "The Lounge", "T2", "Domestic"),
    ("Jammu", "Paahun The Executive Lounge", "T1", "Domestic"),
    ("Kannur", "Pearl Lounge Dom T1", "Main Terminal", "Domestic"),
    ("Kochi", "Earth Lounge Dom T1", "T1", "Domestic"),
    ("Kolkata", "Travel Club Lounge Dom T1", "T1", "Domestic"),
    ("Lucknow", "Cip Lounge", "T3", "Domestic"),
    ("Madurai", "Primus Lounge", "T1", "Domestic"),
    ("Mumbai", "Adani Lounge", "T2", "Domestic"),
    ("Mumbai", "Oasis Lounge", "T1B", "Domestic"),
    ("Mumbai", "Travel Club Lounge", "T1C", "Domestic"),
    ("Nagpur", "Mandarin Lounge", "T1", "Domestic"),
    ("Nagpur", "The Airr Lounge And Bar", "Main Terminal", "Domestic"),
    ("New Delhi", "Encalm Lounge Dom T1", "T1", "Domestic"),
    ("New Delhi", "Encalm Lounge Dom T2", "T2", "Domestic"),
    ("New Delhi", "Encalm Lounge Dom T3", "T3", "Domestic"),
    ("Patna", "Zesto Executive Lounge", "T1", "Domestic"),
    ("Pune", "Earth Lounge", "T1", "Domestic"),
    ("Pune", "Elysian Lounge", "New Terminal", "Domestic"),
    ("Ranchi", "Airr Lounge", "Main Terminal", "Domestic"),
    ("Bagdogra", "Take Off Bar And Lounge", "Main Terminal", "Domestic"),
    ("Srinagar", "Paahun The Executive Lounge", "T1", "Domestic"),
    ("Trivandrum", "The Lounge", "Main Terminal", "Domestic"),
    ("Vadodara", "Premium Lounge", "Main Terminal", "Domestic"),
    ("Varanasi", "Take Off Bar", "Main Terminal", "Domestic"),
    ("Visakhapatnam", "Airr Lounge", "Main Terminal", "Domestic"),
]

# IndusInd Tiger — official IndusInd PDF (Bajaj Tiger eligible list, domestic departure focus)
INDUSIND_TIGER_LOUNGES = [
    ("Agartala", "Primus Lounge", "Domestic Terminal", "Domestic"),
    ("Ahmedabad", "The Lounge", "T1", "Domestic"),
    ("Bagdogra", "Take of Bar", "T1", "Domestic"),
    ("Bengaluru", "080 Lounge", "T2", "Domestic"),
    ("Bengaluru", "080 Lounge", "T1", "Domestic"),
    ("Bhopal", "Primus Lounge", "T1", "Domestic"),
    ("Bhubaneswar", "Bird Lounge", "T1", "Domestic"),
    ("Chandigarh", "Plaza Premium", "Domestic Terminal", "Domestic"),
    ("Chennai", "Travel Club", "T1", "Domestic"),
    ("Chennai", "Travel Club", "T4", "Domestic"),
    ("Coimbatore", "Blackberry Lounge", "T1", "Domestic"),
    ("Dehradun", "Bird Lounge", "T1", "Domestic"),
    ("Dibrugarh", "Primus Lounge", "Domestic Terminal", "Domestic"),
    ("Goa", "Travel Club Lounge", "T1", "Domestic"),
    ("Goa", "Encalm Lounge", "T1", "Domestic"),
    ("Guwahati", "The Lounge", "T1", "Domestic"),
    ("Gwalior", "Pahun Lounge", "T1", "Domestic"),
    ("Hyderabad", "Encalm Lounge Domestic T1", "T1", "Domestic"),
    ("Indore", "Primus Lounge", "T1", "Domestic"),
    ("Jaipur", "Adani Lounge", "T1", "Domestic"),
    ("Jammu", "Pahun Lounge", "T1", "Domestic"),
    ("Kannur", "Pearl Lounge", "T1", "Domestic"),
    ("Kolkata", "Travel Club", "T1", "Domestic"),
    ("Lucknow", "Adani Lounge", "T3", "Domestic"),
    ("Madurai", "Primus Lounge", "Main Terminal", "Domestic"),
    ("Mumbai", "Travel Club", "T1C", "Domestic"),
    ("Mumbai", "Adani Lounge", "T1B", "Domestic"),
    ("Mumbai", "Travel Club", "T2", "Domestic"),
    ("Nagpur", "Airr Lounge", "T1", "Domestic"),
    ("Nagpur", "Mandarin Lounge", "T1", "Domestic"),
    ("New Delhi", "Encalm Lounge Domestic T1", "T1", "Domestic"),
    ("New Delhi", "Encalm Lounge Domestic T3", "T3", "Domestic"),
    ("Prayagraj", "Zesto Lounge", "T1", "Domestic"),
    ("Ranchi", "Airr Lounge", "T1", "Domestic"),
    ("Srinagar", "Pahun Lounge", "T1", "Domestic"),
    ("Trivandrum", "The Lounge", "T2", "International"),
    ("Vadodara", "Premium Lounge", "Domestic Terminal", "Domestic"),
    ("Varanasi", "Take off Bar and Lounge", "T1", "Domestic"),
    ("Visakhapatnam", "Airr Lounge", "T1", "Domestic"),
]

# HDFC Diners — HOI official list (city names from portal)
HDFC_DINERS_CITIES = [
    "Agartala", "Ahmedabad", "Prayagraj", "Amritsar", "Bengaluru", "Bhopal", "Bhubaneswar",
    "Calicut", "Chandigarh", "Chennai", "Kochi", "Coimbatore", "Dehradun", "Dibrugarh",
    "Guwahati", "Gwalior", "Hyderabad", "Indore", "Jaipur", "Jammu", "Kannur", "Kolkata",
    "Lucknow", "Madurai", "Mumbai", "Goa", "Pune", "Ranchi", "Bagdogra", "Srinagar",
    "Trivandrum", "Vadodara", "Varanasi", "Visakhapatnam", "Ayodhya", "New Delhi",
]

# ICICI Rubyx — domestic cities from official consolidated PDF (April 2026)
ICICI_RUBYX_CITIES = [
    "Agartala", "Ahmedabad", "Prayagraj", "Amritsar", "Ayodhya", "Bengaluru", "Bhopal",
    "Bhubaneswar", "Calicut", "Chandigarh", "Chennai", "Kochi", "Coimbatore", "Goa",
    "Dehradun", "Dibrugarh", "Guwahati", "Gwalior", "Hyderabad", "Indore", "Jaipur",
    "Jammu", "Kannur", "Kolkata", "Lucknow", "Madurai", "Mumbai", "Nagpur", "New Delhi",
    "Pune", "Ranchi", "Raipur", "Bagdogra", "Srinagar", "Trivandrum", "Trichy", "Vadodara",
    "Varanasi", "Visakhapatnam",
]

# AU Spont — HOI official list
AU_SPONT_CITIES = [
    "Ahmedabad", "Amritsar", "Vadodara", "Bhopal", "Bengaluru", "Mumbai", "Kolkata",
    "Coimbatore", "Kannur", "Kochi", "New Delhi", "Dibrugarh", "Guwahati", "Goa",
    "Gwalior", "Hyderabad", "Indore", "Agartala", "Chandigarh", "Jammu", "Madurai",
    "Ranchi", "Jaipur", "Lucknow", "Chennai", "Nagpur", "Bhubaneswar", "Srinagar",
    "Trivandrum", "Varanasi", "Visakhapatnam",
]

CARD_LOUNGE_SOURCES: dict[str, list[tuple[str, str, str, str]] | list[str]] = {
    "axis_rewards": AXIS_SET_A_LOUNGES,
    "dbs_supercard": DBS_SUPERCARD_LOUNGES,
    "indusind_tiger": INDUSIND_TIGER_LOUNGES,
    "hdfc_diners_privilege": HDFC_DINERS_CITIES,
    "icici_rubyx": ICICI_RUBYX_CITIES,
    "au_spont": AU_SPONT_CITIES,
}


def lounges_to_airports(entries: list[tuple[str, str, str, str]] | list[str]) -> set[str]:
    airports: set[str] = set()
    for item in entries:
        if isinstance(item, str):
            airports.add(normalize_city(item))
        else:
            airports.add(normalize_city(item[0]))
    return airports
