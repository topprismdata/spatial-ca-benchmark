"""City terrain taxonomy and calibrated road-network circuity factors.

Empirical anchors: Newell (1980) on network circuity; Ballou, Magazine & Rao
(2002) on road-vs-Euclidean inflation ratios; calibrated against real OSM
drive-network distance matrices for Chinese cities.
"""

from __future__ import annotations

from typing import Dict, Tuple

CIRCUITY_PRESETS: Dict[str, float] = {
    "urban_plain_grid": 1.22,    # flat chessboard grids (Chengdu, Beijing, ...)
    "suburban_mix": 1.27,        # default mixed urban-fringe (golden median)
    "waterway_delta": 1.29,      # river/bay fragmented deltas (Guangzhou, ...)
    "mountainous_rugged": 1.35,  # valley/ridge constrained (Chongqing, ...)
}

PLAIN_GRID_CITIES = {
    "成都市", "北京市", "西安市", "郑州市", "石家庄市", "太原市", "济南市",
    "天津市", "长春市", "哈尔滨市", "沈阳市", "合肥市", "南京市", "南昌市",
    "长沙市", "上海市", "苏州市", "无锡市", "常州市", "徐州市", "南通市",
    "保定市", "唐山市", "邯郸市", "沧州市", "廊坊市", "德州市", "聊城市",
    "临沂市", "菏泽市", "商丘市", "新乡市", "安阳市", "焦作市", "许昌市",
    "大庆市", "鞍山市", "锦州市", "吉林市", "开封市", "洛阳市", "平顶山市",
}

MOUNTAIN_CITIES = {
    "重庆市", "贵阳市", "昆明市", "大连市", "青岛市", "烟台市", "威海市",
    "兰州市", "西宁市", "银川市", "乌鲁木齐市", "延安市", "遵义市", "安顺市",
    "六盘水市", "曲靖市", "玉溪市", "大理白族自治州", "攀枝花市", "绵阳市",
    "宜宾市", "泸州市", "乐山市", "南充市", "达州市", "广元市", "巴中市",
    "承德市", "张家口市", "秦皇岛市", "朔州市", "大同市", "阳泉市", "长治市",
    "呼和浩特市", "包头市", "鄂尔多斯市", "通化市", "延边朝鲜族自治州",
    "西双版纳傣族自治州",
}

WATER_DELTA_CITIES = {
    "广州市", "深圳市", "佛山市", "东莞市", "中山市", "珠海市", "江门市",
    "惠州市", "汕头市", "湛江市", "海口市", "三亚市", "福州市", "厦门市",
    "泉州市", "漳州市", "莆田市", "杭州市", "宁波市", "温州市", "绍兴市",
    "嘉兴市", "湖州市", "金华市", "台州市", "武汉市", "荆州市", "宜昌市",
    "襄阳市", "岳阳市", "常德市", "九江市", "芜湖市", "马鞍山市", "安庆市",
    "潮州市", "揭阳市",
}


def get_city_terrain_and_circuity(city_name: str) -> Tuple[str, float]:
    """Map a Chinese city name to (terrain_type, calibrated circuity factor)."""
    if not city_name:
        return "suburban_mix", CIRCUITY_PRESETS["suburban_mix"]
    for name in PLAIN_GRID_CITIES:
        if name in city_name or city_name in name:
            return "urban_plain_grid", CIRCUITY_PRESETS["urban_plain_grid"]
    for name in MOUNTAIN_CITIES:
        if name in city_name or city_name in name:
            return "mountainous_rugged", CIRCUITY_PRESETS["mountainous_rugged"]
    for name in WATER_DELTA_CITIES:
        if name in city_name or city_name in name:
            return "waterway_delta", CIRCUITY_PRESETS["waterway_delta"]
    return "suburban_mix", CIRCUITY_PRESETS["suburban_mix"]
