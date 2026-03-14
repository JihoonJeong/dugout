"""MLB 30개 팀 데이터."""

# 팀 약어 → 팀명 + 구장
TEAM_MAPPING = {
    "ARI": {"name": "Arizona Diamondbacks", "park": "Chase Field"},
    "ATL": {"name": "Atlanta Braves", "park": "Truist Park"},
    "BAL": {"name": "Baltimore Orioles", "park": "Oriole Park at Camden Yards"},
    "BOS": {"name": "Boston Red Sox", "park": "Fenway Park"},
    "CHC": {"name": "Chicago Cubs", "park": "Wrigley Field"},
    "CHW": {"name": "Chicago White Sox", "park": "Guaranteed Rate Field"},
    "CIN": {"name": "Cincinnati Reds", "park": "Great American Ball Park"},
    "CLE": {"name": "Cleveland Guardians", "park": "Progressive Field"},
    "COL": {"name": "Colorado Rockies", "park": "Coors Field"},
    "DET": {"name": "Detroit Tigers", "park": "Comerica Park"},
    "HOU": {"name": "Houston Astros", "park": "Minute Maid Park"},
    "KCR": {"name": "Kansas City Royals", "park": "Kauffman Stadium"},
    "LAA": {"name": "Los Angeles Angels", "park": "Angel Stadium"},
    "LAD": {"name": "Los Angeles Dodgers", "park": "Dodger Stadium"},
    "MIA": {"name": "Miami Marlins", "park": "loanDepot Park"},
    "MIL": {"name": "Milwaukee Brewers", "park": "American Family Field"},
    "MIN": {"name": "Minnesota Twins", "park": "Target Field"},
    "NYM": {"name": "New York Mets", "park": "Citi Field"},
    "NYY": {"name": "New York Yankees", "park": "Yankee Stadium"},
    "ATH": {"name": "Athletics", "park": "Sutter Health Park"},
    "PHI": {"name": "Philadelphia Phillies", "park": "Citizens Bank Park"},
    "PIT": {"name": "Pittsburgh Pirates", "park": "PNC Park"},
    "SDP": {"name": "San Diego Padres", "park": "Petco Park"},
    "SFG": {"name": "San Francisco Giants", "park": "Oracle Park"},
    "SEA": {"name": "Seattle Mariners", "park": "T-Mobile Park"},
    "STL": {"name": "St. Louis Cardinals", "park": "Busch Stadium"},
    "TBR": {"name": "Tampa Bay Rays", "park": "Tropicana Field"},
    "TEX": {"name": "Texas Rangers", "park": "Globe Life Field"},
    "TOR": {"name": "Toronto Blue Jays", "park": "Rogers Centre"},
    "WSN": {"name": "Washington Nationals", "park": "Nationals Park"},
}

# MLB Stats API team IDs
TEAM_IDS = {
    "ARI": 109, "ATL": 144, "BAL": 110, "BOS": 111,
    "CHC": 112, "CHW": 145, "CIN": 113, "CLE": 114,
    "COL": 115, "DET": 116, "HOU": 117, "KCR": 118,
    "LAA": 108, "LAD": 119, "MIA": 146, "MIL": 158,
    "MIN": 142, "NYM": 121, "NYY": 147, "ATH": 133,
    "PHI": 143, "PIT": 134, "SDP": 135, "SFG": 137,
    "SEA": 136, "STL": 138, "TBR": 139, "TEX": 140,
    "TOR": 141, "WSN": 120,
}

# 팀명 약칭 (프론트엔드 표시용)
TEAM_SHORT_NAMES = {k: v["name"].split()[-1] if " " in v["name"] else v["name"] for k, v in TEAM_MAPPING.items()}
# 수동 보정
TEAM_SHORT_NAMES["CHW"] = "White Sox"
TEAM_SHORT_NAMES["BOS"] = "Red Sox"
TEAM_SHORT_NAMES["TBR"] = "Rays"
TEAM_SHORT_NAMES["ARI"] = "D-backs"
TEAM_SHORT_NAMES["SFG"] = "Giants"
TEAM_SHORT_NAMES["SDP"] = "Padres"
