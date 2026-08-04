"""Pinyin mapping for herb name characters (spec §2.4 — 拼音搜索).

No external packages. Covers characters used in the 203 seeded herb names.
"""

from __future__ import annotations


import logging

logger = logging.getLogger(__name__)
HERB_PINYIN: dict[str, str] = {
    # 补虚药
    "黄": "huang", "芪": "qi", "参": "shen", "术": "zhu", "甘": "gan", "草": "cao",
    "当": "dang", "归": "gui", "白": "bai", "芍": "shao", "熟": "shu", "地": "di",
    "何": "he", "首": "shou", "阿": "a", "胶": "jiao", "龙": "long", "眼": "yan",
    "北": "bei", "沙": "sha", "麦": "mai", "冬": "dong", "天": "tian", "石": "shi",
    "斛": "hu", "玉": "yu", "竹": "zhu", "百": "bai", "合": "he",
    "龟": "gui", "鳖": "bie", "甲": "jia",
    "鹿": "lu", "茸": "rong", "淫": "yin", "羊": "yang", "藿": "huo", "巴": "ba",
    "戟": "ji", "仙": "xian", "茅": "mao", "杜": "du", "仲": "zhong",
    "续": "xu", "断": "duan", "肉": "rou", "苁": "cong", "蓉": "rong",
    "锁": "suo", "阳": "yang", "菟": "tu", "丝": "si", "子": "zi",
    "虫": "chong", "草": "cao",
    # 解表药
    "麻": "ma", "黄": "huang", "桂": "gui", "枝": "zhi", "紫": "zi", "苏": "su",
    "叶": "ye", "荆": "jing", "芥": "jie", "防": "fang", "风": "feng",
    "羌": "qiang", "活": "huo", "白": "bai", "芷": "zhi", "藁": "gao", "本": "ben",
    "苍": "cang", "耳": "er", "辛": "xin", "夷": "yi", "薄": "bo", "荷": "he",
    "牛": "niu", "蒡": "bang", "蝉": "chan", "蜕": "tui", "桑": "sang",
    "菊": "ju", "蔓": "man", "荆": "jing", "柴": "chai", "葛": "ge",
    "升": "sheng", "浮": "fu", "萍": "ping", "木": "mu", "贼": "zei",
    "豆": "dou", "豉": "chi",
    # 清热药
    "石": "shi", "膏": "gao", "知": "zhi", "母": "mu", "芦": "lu", "根": "gen",
    "天": "tian", "花": "hua", "粉": "fen", "竹": "zhu", "茹": "ru",
    "栀": "zhi", "子": "zi", "夏": "xia", "枯": "ku", "黄": "huang", "芩": "qin",
    "连": "lian", "翘": "qiao", "龙": "long", "胆": "dan", "苦": "ku",
    "穿": "chuan", "心": "xin", "莲": "lian", "秦": "qin", "皮": "pi",
    "银": "yin", "藤": "teng", "蒲": "pu", "公": "gong", "英": "ying",
    "紫": "zi", "花": "hua", "地": "di", "丁": "ding", "大": "da",
    "青": "qing", "黛": "dai", "鱼": "yu", "腥": "xing", "射": "she",
    "干": "gan", "山": "shan", "豆": "dou", "根": "gen", "马": "ma",
    "勃": "bo", "白": "bai", "头": "tou", "翁": "weng", "鸦": "ya",
    "贯": "guan", "众": "zhong", "金": "jin", "银": "yin", "花": "hua",
    "生": "sheng", "玄": "xuan", "赤": "chi", "牡": "mu", "丹": "dan",
    "紫": "zi", "草": "cao", "水": "shui", "牛": "niu", "角": "jiao",
    "青": "qing", "蒿": "hao", "地": "di", "骨": "gu", "皮": "pi",
    "银": "yin", "胡": "hu", "胡": "hu", "黄": "huang", "连": "lian",
    "白": "bai", "薇": "wei",
    # 泻下药
    "大": "da", "黄": "huang", "芒": "mang", "硝": "xiao",
    "番": "fan", "泻": "xie", "叶": "ye", "芦": "lu", "荟": "hui",
    "火": "huo", "麻": "ma", "仁": "ren", "郁": "yu", "李": "li",
    "松": "song", "子": "zi", "甘": "gan", "遂": "sui", "京": "jing",
    "大": "da", "戟": "ji", "芫": "yuan", "花": "hua", "牵": "qian",
    "牛": "niu", "子": "zi", "商": "shang", "陆": "lu",
    # 祛风湿药
    "独": "du", "威": "wei", "灵": "ling", "仙": "xian",
    "川": "chuan", "乌": "wu", "草": "cao", "乌": "wu", "蕲": "qi",
    "蛇": "she", "木": "mu", "瓜": "gua", "乌": "wu", "梢": "shao",
    "蛇": "she", "伸": "shen", "筋": "jin", "草": "cao", "透": "tou",
    "骨": "gu", "草": "cao", "寻": "xun", "骨": "gu", "风": "feng",
    "海": "hai", "风": "feng", "藤": "teng", "络": "luo", "石": "shi",
    "藤": "teng", "雷": "lei", "公": "gong", "藤": "teng",
    "五": "wu", "加": "jia", "皮": "pi", "桑": "sang", "寄": "ji",
    "生": "sheng", "狗": "gou", "脊": "ji", "千": "qian", "年": "nian",
    "健": "jian", "鹿": "lu", "衔": "xian", "草": "cao",
    # 化湿药
    "苍": "cang", "术": "zhu", "厚": "hou", "朴": "po", "藿": "huo",
    "香": "xiang", "佩": "pei", "兰": "lan", "砂": "sha", "仁": "ren",
    "白": "bai", "豆": "dou", "蔻": "kou", "草": "cao", "豆": "dou",
    "蔻": "kou", "草": "cao", "果": "guo",
    # 利水渗湿药
    "茯": "fu", "苓": "ling", "猪": "zhu", "苓": "ling",
    "泽": "ze", "泻": "xie", "薏": "yi", "苡": "yi", "仁": "ren",
    "车": "che", "前": "qian", "子": "zi", "滑": "hua", "石": "shi",
    "木": "mu", "通": "tong", "通": "tong", "草": "cao",
    "瞿": "qu", "麦": "mai", "萹": "bian", "蓄": "xu", "地": "di",
    "肤": "fu", "子": "zi", "海": "hai", "金": "jin", "沙": "sha",
    "石": "shi", "韦": "wei", "萆": "bie", "薢": "xie",
    "茵": "yin", "陈": "chen", "蒿": "hao", "金": "jin", "钱": "qian",
    "草": "cao", "虎": "hu", "杖": "zhang", "地": "di", "耳": "er",
    "草": "cao",
    # 温里药
    "附": "fu", "干": "gan", "姜": "jiang", "肉": "rou", "桂": "gui",
    "吴": "wu", "茱": "zhu", "萸": "yu", "小": "xiao", "茴": "hui",
    "香": "xiang", "丁": "ding", "公": "gong", "母": "mu",
    "高": "gao", "良": "liang", "胡": "hu", "椒": "jiao",
    "花": "hua", "椒": "jiao", "荜": "bi", "茇": "ba",
    "澄": "cheng", "茄": "qie",
    # 理气药
    "陈": "chen", "皮": "pi", "青": "qing", "皮": "pi", "枳": "zhi",
    "实": "shi", "枳": "zhi", "壳": "ke", "木": "mu", "香": "xiang",
    "沉": "chen", "檀": "tan", "川": "chuan", "楝": "lian",
    "子": "zi", "乌": "wu", "药": "yao", "佛": "fo", "手": "shou",
    "香": "xiang", "橼": "yuan", "玫": "mei", "瑰": "gui",
    "花": "hua", "绿": "lv", "萼": "e", "梅": "mei",
    "薤": "xie", "白": "bai", "刀": "dao", "豆": "dou",
    "柿": "shi", "蒂": "di", "甘": "gan", "松": "song",
    "九": "jiu", "里": "li", "香": "xiang",
    # 消食药
    "山": "shan", "楂": "zha", "神": "shen", "曲": "qu",
    "麦": "mai", "芽": "ya", "稻": "dao", "芽": "ya",
    "谷": "gu", "芽": "ya", "鸡": "ji", "内": "nei", "金": "jin",
    "莱": "lai", "菔": "fu", "子": "zi",
    # 驱虫药
    "使": "shi", "君": "jun", "苦": "ku", "楝": "lian", "皮": "pi",
    "槟": "bing", "榔": "lang", "南": "nan", "瓜": "gua",
    "子": "zi", "鹤": "he", "草": "cao", "芽": "ya",
    "雷": "lei", "丸": "wan", "榧": "fei", "芜": "wu", "荑": "yi",
    # 止血药
    "大": "da", "蓟": "ji", "小": "xiao", "蓟": "ji",
    "地": "di", "榆": "yu", "槐": "huai", "花": "hua",
    "侧": "ce", "柏": "bai", "叶": "ye", "白": "bai",
    "茅": "mao", "根": "gen", "苎": "zhu", "麻": "ma",
    "根": "gen", "仙": "xian", "鹤": "he", "草": "cao",
    "棕": "zong", "榈": "lv", "炭": "tan", "血": "xue",
    "余": "yu", "炭": "tan", "藕": "ou", "节": "jie",
    "炮": "pao", "姜": "jiang", "艾": "ai", "叶": "ye",
    "灶": "zao", "心": "xin", "土": "tu", "三": "san",
    "七": "qi", "蒲": "pu", "黄": "huang",
    # 活血化瘀药
    "川": "chuan", "芎": "xiong", "延": "yan", "胡": "hu",
    "索": "suo", "郁": "yu", "金": "jin", "姜": "jiang",
    "黄": "huang", "乳": "ru", "香": "xiang", "没": "mo",
    "药": "yao", "五": "wu", "灵": "ling", "脂": "zhi",
    "丹": "dan", "参": "shen", "红": "hong", "花": "hua",
    "桃": "tao", "仁": "ren", "益": "yi", "母": "mu",
    "草": "cao", "泽": "ze", "兰": "lan", "牛": "niu",
    "膝": "xi", "鸡": "ji", "血": "xue", "藤": "teng",
    "穿": "chuan", "山": "shan", "甲": "jia", "王": "wang",
    "不": "bu", "留": "liu", "行": "xing", "土": "tu",
    "鳖": "bie", "虫": "chong", "苏": "su", "木": "mu",
    "骨": "gu", "碎": "sui", "补": "bu", "自": "zi",
    "然": "ran", "铜": "tong",
    # 化痰止咳平喘药
    "半": "ban", "夏": "xia", "天": "tian", "南": "nan",
    "白": "bai", "附": "fu", "子": "zi", "芥": "jie",
    "子": "zi", "旋": "xuan", "覆": "fu", "花": "hua",
    "白": "bai", "前": "qian", "前": "qian", "胡": "hu",
    "桔": "jie", "梗": "geng", "川": "chuan", "贝": "bei",
    "母": "mu", "浙": "zhe", "贝": "bei", "瓜": "gua",
    "蒌": "lou", "竹": "zhu", "茹": "ru", "天": "tian",
    "竺": "zhu", "黄": "huang", "海": "hai", "藻": "zao",
    "昆": "kun", "布": "bu", "黄": "huang", "药": "yao",
    "子": "zi", "胖": "pang", "大": "da", "海": "hai",
    "木": "mu", "蝴": "hu", "蝶": "die", "礞": "meng",
    "石": "shi", "杏": "xing", "仁": "ren", "百": "bai",
    "部": "bu", "紫": "zi", "菀": "wan", "款": "kuan",
    "冬": "dong", "花": "hua", "枇": "pi", "杷": "pa",
    "叶": "ye", "桑": "sang", "白": "bai", "皮": "pi",
    "葶": "ting", "苈": "li", "子": "zi", "白": "bai",
    "果": "guo", "洋": "yang", "金": "jin", "花": "hua",
    # 安神药
    "朱": "zhu", "砂": "sha", "磁": "ci", "石": "shi",
    "龙": "long", "骨": "gu", "琥": "hu", "珀": "po",
    "酸": "suan", "枣": "zao", "仁": "ren", "柏": "bai",
    "子": "zi", "远": "yuan", "志": "zhi", "合": "he",
    "欢": "huan", "皮": "pi", "首": "shou", "乌": "wu",
    "藤": "teng",
    # 平肝息风药
    "石": "shi", "决": "jue", "明": "ming", "珍": "zhen",
    "珠": "zhu", "母": "mu", "牡": "mu", "蛎": "li",
    "代": "dai", "赭": "zhe", "石": "shi", "刺": "ci",
    "蒺": "ji", "藜": "li", "罗": "luo", "布": "bu",
    "麻": "ma", "叶": "ye", "牛": "niu", "黄": "huang",
    "钩": "gou", "藤": "teng", "天": "tian", "麻": "ma",
    "地": "di", "龙": "long", "全": "quan", "蝎": "xie",
    "蜈": "wu", "蚣": "gong", "僵": "jiang", "蚕": "can",
    "蝉": "chan", "蜕": "tui",
    # 开窍药
    "麝": "she", "香": "xiang", "冰": "bing", "片": "pian",
    "苏": "su", "合": "he", "香": "xiang", "石": "shi",
    "菖": "chang", "蒲": "pu", "蟾": "chan", "酥": "su",
    # 收涩药
    "麻": "ma", "黄": "huang", "根": "gen", "浮": "fu",
    "小": "xiao", "麦": "mai", "五": "wu", "味": "wei",
    "子": "zi", "乌": "wu", "梅": "mei", "五": "wu",
    "倍": "bei", "子": "zi", "罂": "ying", "粟": "su",
    "壳": "ke", "诃": "he", "子": "zi", "石": "shi",
    "榴": "liu", "皮": "pi", "肉": "rou", "豆": "dou",
    "蔻": "kou", "赤": "chi", "石": "shi", "脂": "zhi",
    "禹": "yu", "余": "yu", "粮": "liang", "山": "shan",
    "茱": "zhu", "萸": "yu", "覆": "fu", "盆": "pen",
    "子": "zi", "桑": "sang", "螵": "piao", "蛸": "xiao",
    "海": "hai", "螵": "piao", "蛸": "xiao", "莲": "lian",
    "须": "xu", "芡": "qian", "实": "shi",
    # 攻毒杀虫止痒药
    "雄": "xiong", "硫": "liu", "磺": "huang", "白": "bai",
    "矾": "fan", "蛇": "she", "床": "chuang", "子": "zi",
    "土": "tu", "荆": "jing", "皮": "pi", "蜂": "feng",
    "房": "fang", "大": "da", "蒜": "suan",
    # Numbers and common suffixes
    "一": "yi", "二": "er", "三": "san", "四": "si",
    "五": "wu", "六": "liu", "七": "qi", "八": "ba",
    "九": "jiu", "十": "shi",
}


def to_pinyin(text: str) -> str:
    """Convert Chinese text to pinyin (simple lookup, no tones).

    Characters not in HERB_PINYIN are passed through unchanged.
    """
    parts: list[str] = []
    for char in text:
        parts.append(HERB_PINYIN.get(char, char))
    return "".join(parts)


def to_pinyin_abbrev(text: str) -> str:
    """Convert Chinese text to pinyin abbreviation (first letters only).

    For "黄芪" returns "hq". Characters not in HERB_PINYIN are skipped.
    """
    parts: list[str] = []
    for char in text:
        pinyin = HERB_PINYIN.get(char)
        if pinyin:
            parts.append(pinyin[0])
    return "".join(parts)
