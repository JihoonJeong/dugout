"""NPB 12개 팀 데이터 (Central 6 + Pacific 6)."""

TEAM_MAPPING = {
    # Central League
    "巨人":   {"name": "読売ジャイアンツ", "name_en": "Yomiuri Giants", "park": "東京ドーム", "league": "central"},
    "阪神":   {"name": "阪神タイガース", "name_en": "Hanshin Tigers", "park": "甲子園球場", "league": "central"},
    "中日":   {"name": "中日ドラゴンズ", "name_en": "Chunichi Dragons", "park": "バンテリンドーム", "league": "central"},
    "DeNA":   {"name": "横浜DeNAベイスターズ", "name_en": "Yokohama DeNA BayStars", "park": "横浜スタジアム", "league": "central"},
    "広島":   {"name": "広島東洋カープ", "name_en": "Hiroshima Carp", "park": "MAZDA Zoom-Zoom スタジアム広島", "league": "central"},
    "ヤクルト": {"name": "東京ヤクルトスワローズ", "name_en": "Tokyo Yakult Swallows", "park": "明治神宮野球場", "league": "central"},
    # Pacific League
    "オリックス": {"name": "オリックス・バファローズ", "name_en": "Orix Buffaloes", "park": "京セラドーム大阪", "league": "pacific"},
    "ソフトバンク": {"name": "福岡ソフトバンクホークス", "name_en": "Fukuoka SoftBank Hawks", "park": "みずほPayPayドーム福岡", "league": "pacific"},
    "西武":   {"name": "埼玉西武ライオンズ", "name_en": "Saitama Seibu Lions", "park": "ベルーナドーム", "league": "pacific"},
    "楽天":   {"name": "東北楽天ゴールデンイーグルス", "name_en": "Tohoku Rakuten Golden Eagles", "park": "楽天モバイルパーク宮城", "league": "pacific"},
    "ロッテ": {"name": "千葉ロッテマリーンズ", "name_en": "Chiba Lotte Marines", "park": "ZOZOマリンスタジアム", "league": "pacific"},
    "日本ハム": {"name": "北海道日本ハムファイターズ", "name_en": "Hokkaido Nippon-Ham Fighters", "park": "エスコンフィールドHOKKAIDO", "league": "pacific"},
}

TEAM_SHORT_NAMES = {
    "巨人": "Giants", "阪神": "Tigers", "中日": "Dragons",
    "DeNA": "BayStars", "広島": "Carp", "ヤクルト": "Swallows",
    "オリックス": "Buffaloes", "ソフトバンク": "Hawks", "西武": "Lions",
    "楽天": "Eagles", "ロッテ": "Marines", "日本ハム": "Fighters",
}
