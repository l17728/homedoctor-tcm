"""Seasonal Health router — 24 solar terms detailed wellness guidance.

Provides per-term health advice including diet, lifestyle, exercise,
acupressure points, seasonal herbs, and recommended formulas.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends

from app.auth import get_current_user
from app.solar_terms import SOLAR_TERMS, TERM_SEASON, get_next_term, get_season, get_solar_term

router = APIRouter(prefix="/api/seasonal-health", tags=["seasonal-health"])


TERM_DETAIL: dict[str, dict] = {
    "立春": {
        "principle": "春季始，万物复苏，肝气升发",
        "diet": ["多吃辛温发散食物：葱、姜、韭菜", "少酸增甘，养脾气", "宜饮玫瑰花茶疏肝"],
        "lifestyle": ["夜卧早起，广步于庭", "被发缓形，以使志生", "防风寒，春捂秋冻"],
        "exercise": ["散步、慢跑", "八段锦「调理脾胃须单举」", "放风筝、踏青"],
        "acupoints": [{"name": "太冲", "location": "足背第1-2跖骨间", "effect": "疏肝理气"}],
        "herbs": [{"name": "柴胡", "reason": "疏肝解郁"}, {"name": "薄荷", "reason": "疏散风热"}],
        "formulas": ["逍遥散", "桂枝汤"],
    },
    "雨水": {
        "principle": "雨水至，湿气渐重，健脾祛湿",
        "diet": ["薏仁粥健脾祛湿", "山药、红枣补脾", "少食生冷"],
        "lifestyle": ["注意保暖防湿", "保持室内通风干燥", "勿过早减衣"],
        "exercise": ["太极拳", "慢走", "五禽戏"],
        "acupoints": [{"name": "阴陵泉", "location": "小腿内侧，膝下", "effect": "健脾利湿"}],
        "herbs": [{"name": "茯苓", "reason": "利水渗湿"}, {"name": "薏苡仁", "reason": "健脾止泻"}],
        "formulas": ["参苓白术散"],
    },
    "惊蛰": {
        "principle": "惊蛰至，万物复苏，养肝护肝",
        "diet": ["多吃绿色蔬菜养肝", "菊花茶清肝明目", "少食油腻"],
        "lifestyle": ["早起迎阳气", "保持心情舒畅", "防春寒"],
        "exercise": ["户外踏青", "瑜伽拉伸肝经", "慢跑"],
        "acupoints": [{"name": "期门", "location": "乳头直下第六肋间", "effect": "疏肝健脾"}],
        "herbs": [{"name": "菊花", "reason": "清肝明目"}, {"name": "决明子", "reason": "清肝润肠"}],
        "formulas": ["杞菊地黄丸"],
    },
    "春分": {
        "principle": "阴阳平衡，调和气血",
        "diet": ["饮食均衡不偏食", "多吃芽菜助升发", "忌大寒大热"],
        "lifestyle": ["起居有常", "保持心态平和", "春游赏花"],
        "exercise": ["广播体操", "快步走", "骑行"],
        "acupoints": [{"name": "足三里", "location": "外膝眼下四横指", "effect": "调理脾胃，强身健体"}],
        "herbs": [{"name": "黄芪", "reason": "补气固表"}, {"name": "当归", "reason": "补血活血"}],
        "formulas": ["四君子汤", "四物汤"],
    },
    "清明": {
        "principle": "气候温和，疏肝养肝",
        "diet": ["清淡饮食", "多吃时令蔬菜：荠菜、香椿", "饮明前茶"],
        "lifestyle": ["踏青郊游", "扫墓追思，调节情绪", "早睡早起"],
        "exercise": ["登山", "太极拳", "垂钓"],
        "acupoints": [{"name": "阳陵泉", "location": "小腿外侧腓骨小头前下方", "effect": "疏肝利胆"}],
        "herbs": [{"name": "桑叶", "reason": "疏散风热"}, {"name": "菊花", "reason": "清肝明目"}],
        "formulas": ["桑菊饮"],
    },
    "谷雨": {
        "principle": "春末湿气加重，祛湿健脾",
        "diet": ["薏仁赤小豆汤", "扁豆、山药健脾", "忌寒凉生冷"],
        "lifestyle": ["注意防潮", "保持心情舒畅", "适当午休"],
        "exercise": ["游泳", "瑜伽", "散步"],
        "acupoints": [{"name": "丰隆", "location": "小腿前外侧", "effect": "化痰祛湿"}],
        "herbs": [{"name": "藿香", "reason": "化湿解表"}, {"name": "陈皮", "reason": "理气化痰"}],
        "formulas": ["藿香正气散"],
    },
    "立夏": {
        "principle": "夏季始，养心安神",
        "diet": ["清淡饮食，少油腻", "适当食苦味清热：苦瓜、莲子心", "多饮温水"],
        "lifestyle": ["晚睡早起加午休", "避免大汗淋漓", "保持心平气和"],
        "exercise": ["散步、慢跑（清晨或傍晚）", "太极拳", "瑜伽"],
        "acupoints": [{"name": "神门", "location": "腕横纹尺侧端", "effect": "宁心安神"}],
        "herbs": [{"name": "莲子", "reason": "养心安神"}, {"name": "酸枣仁", "reason": "养心益肝"}],
        "formulas": ["天王补心丹"],
    },
    "小满": {
        "principle": "天气渐热，清热利湿",
        "diet": ["多食蔬果：黄瓜、西瓜", "绿豆汤清热解暑", "少食辛辣油腻"],
        "lifestyle": ["注意防暑降温", "保持充足睡眠", "勿贪凉"],
        "exercise": ["游泳", "清晨慢跑", "羽毛球"],
        "acupoints": [{"name": "曲池", "location": "肘横纹外侧端", "effect": "清热泻火"}],
        "herbs": [{"name": "绿豆", "reason": "清热解毒"}, {"name": "荷叶", "reason": "清暑利湿"}],
        "formulas": ["清暑益气汤"],
    },
    "芒种": {
        "principle": "暑湿渐重，清热解暑养心",
        "diet": ["多饮水", "西瓜、绿豆汤解暑", "山药、薏仁健脾", "少食冰饮冷食"],
        "lifestyle": ["保证充足睡眠", "午休30分钟", "避免烈日下久留"],
        "exercise": ["游泳", "清晨或傍晚散步", "八段锦"],
        "acupoints": [{"name": "内关", "location": "腕横纹上三横指", "effect": "宁心安神，和胃止呕"}],
        "herbs": [{"name": "金银花", "reason": "清热解毒，夏季防暑"}, {"name": "荷叶", "reason": "清暑利湿"}],
        "formulas": ["清络饮", "生脉散"],
    },
    "夏至": {
        "principle": "阳气最旺，养心护阳",
        "diet": ["宜清淡，多食苦味：苦瓜、莲子", "忌冰冷伤脾", "酸梅汤生津止渴"],
        "lifestyle": ["晚睡早起加午休", "避免烈日下久留", "适度使用空调"],
        "exercise": ["游泳最佳", "清晨慢跑", "瑜伽"],
        "acupoints": [{"name": "涌泉", "location": "足底前三分之一处", "effect": "引火归元，滋阴降火"}],
        "herbs": [{"name": "西洋参", "reason": "益气养阴，清火生津"}, {"name": "麦冬", "reason": "养阴润肺"}],
        "formulas": ["生脉散", "清暑益气汤"],
    },
    "小暑": {
        "principle": "天气炎热，防暑养心",
        "diet": ["多饮水和淡盐水", "西瓜、绿豆解暑", "冬瓜利湿", "少食辛辣"],
        "lifestyle": ["避免午间外出", "保持室内通风", "午休30-60分钟"],
        "exercise": ["室内瑜伽", "游泳", "清晨散步"],
        "acupoints": [{"name": "大椎", "location": "第七颈椎棘突下", "effect": "清热解表"}],
        "herbs": [{"name": "藿香", "reason": "化湿解暑"}, {"name": "佩兰", "reason": "化湿醒脾"}],
        "formulas": ["藿香正气散", "新加香薷饮"],
    },
    "大暑": {
        "principle": "一年最热，静养避暑",
        "diet": ["绿豆汤、酸梅汤", "丝瓜、苦瓜清热", "薏仁红豆汤祛湿", "忌冰饮伤脾"],
        "lifestyle": ["减少户外活动", "保持心态平和", "充足睡眠"],
        "exercise": ["室内活动为主", "游泳", "清晨太极"],
        "acupoints": [{"name": "足三里", "location": "外膝眼下四横指", "effect": "调理脾胃，增强免疫"}],
        "herbs": [{"name": "荷叶", "reason": "清暑利湿"}, {"name": "西瓜翠衣", "reason": "清热解暑"}],
        "formulas": ["清暑益气汤", "桂苓甘露散"],
    },
    "立秋": {
        "principle": "秋季始，养肺润燥",
        "diet": ["多食白色食物：百合、银耳、雪梨", "蜂蜜润燥", "少食辛辣：姜、葱、蒜"],
        "lifestyle": ["早睡早起", "适当秋冻锻炼", "保持室内湿润"],
        "exercise": ["登高爬山", "慢跑", "深呼吸练肺"],
        "acupoints": [{"name": "列缺", "location": "腕横纹上1.5寸", "effect": "宣肺止咳"}],
        "herbs": [{"name": "百合", "reason": "润肺止咳，养阴"}, {"name": "沙参", "reason": "养阴清肺"}],
        "formulas": ["百合固金汤", "沙参麦冬汤"],
    },
    "处暑": {
        "principle": "暑气渐消，调整作息",
        "diet": ["滋阴润燥：梨、蜂蜜", "适当酸味收敛：乌梅、山楂", "少食寒凉"],
        "lifestyle": ["早睡早起", "增加运动量", "防秋乏"],
        "exercise": ["快步走", "骑行", "登山"],
        "acupoints": [{"name": "尺泽", "location": "肘横纹中肱二头肌腱桡侧", "effect": "清肺泻火"}],
        "herbs": [{"name": "麦冬", "reason": "养阴润肺"}, {"name": "玉竹", "reason": "滋阴润燥"}],
        "formulas": ["麦门冬汤"],
    },
    "白露": {
        "principle": "天气转凉，润燥养肺",
        "diet": ["梨、百合润肺", "蜂蜜润肠", "山药、莲子健脾", "忌生冷"],
        "lifestyle": ["注意保暖，白露不露身", "早睡早起", "适当秋冻"],
        "exercise": ["慢跑", "太极拳", "爬山"],
        "acupoints": [{"name": "鱼际", "location": "第一掌骨中点", "effect": "清肺利咽"}],
        "herbs": [{"name": "川贝", "reason": "润肺化痰"}, {"name": "杏仁", "reason": "止咳平喘"}],
        "formulas": ["桑杏汤", "川贝枇杷膏"],
    },
    "秋分": {
        "principle": "阴阳平衡，养阴润燥",
        "diet": ["均衡饮食", "多食润燥食物：芝麻、糯米", "少食辛辣燥热"],
        "lifestyle": ["起居有常", "保持心态平和", "防秋悲"],
        "exercise": ["广播体操", "慢跑", "骑行"],
        "acupoints": [{"name": "合谷", "location": "手背虎口处", "effect": "疏风解表，镇痛"}],
        "herbs": [{"name": "天冬", "reason": "滋阴润燥"}, {"name": "石斛", "reason": "滋阴清热"}],
        "formulas": ["益胃汤"],
    },
    "寒露": {
        "principle": "寒气渐重，保暖润燥",
        "diet": ["温热食物为主", "板栗、核桃温补", "白萝卜顺气", "忌寒凉"],
        "lifestyle": ["注意保暖", "泡脚驱寒", "早睡早起"],
        "exercise": ["快步走", "爬山", "太极拳"],
        "acupoints": [{"name": "肾俞", "location": "腰部第二腰椎旁", "effect": "温补肾阳"}],
        "herbs": [{"name": "沙参", "reason": "养阴清肺"}, {"name": "百合", "reason": "润肺安神"}],
        "formulas": ["杏苏散"],
    },
    "霜降": {
        "principle": "深秋时节，进补养阴",
        "diet": ["适当进补：羊肉、板栗", "白萝卜、冬瓜利湿", "柿子润肺"],
        "lifestyle": ["注意保暖", "早睡早起", "泡脚养生"],
        "exercise": ["慢跑", "爬山", "太极拳"],
        "acupoints": [{"name": "三阴交", "location": "小腿内侧踝上四横指", "effect": "健脾益肾"}],
        "herbs": [{"name": "枸杞", "reason": "滋补肝肾"}, {"name": "黄精", "reason": "补气养阴"}],
        "formulas": ["六味地黄丸"],
    },
    "立冬": {
        "principle": "冬季始，温补养藏",
        "diet": ["温热食物：羊肉汤、牛肉", "黑色食物补肾：黑豆、黑芝麻", "核桃、板栗温补"],
        "lifestyle": ["早睡晚起", "注意保暖防寒", "泡脚温通经络"],
        "exercise": ["室内运动", "慢跑（午后）", "八段锦"],
        "acupoints": [{"name": "关元", "location": "脐下四横指", "effect": "温肾壮阳"}],
        "herbs": [{"name": "黄芪", "reason": "补气升阳，增强免疫"}, {"name": "肉桂", "reason": "温肾壮阳"}],
        "formulas": ["金匮肾气丸", "当归生姜羊肉汤"],
    },
    "小雪": {
        "principle": "天气渐寒，温补御寒",
        "diet": ["羊肉、牛肉温补", "生姜、桂圆暖身", "黑芝麻、黑豆补肾", "忌生冷"],
        "lifestyle": ["注意防寒保暖", "泡脚驱寒", "保持心情愉悦防冬郁"],
        "exercise": ["室内瑜伽", "慢跑", "跳绳"],
        "acupoints": [{"name": "命门", "location": "腰部后正中线第二腰椎下", "effect": "温肾壮阳"}],
        "herbs": [{"name": "杜仲", "reason": "补肝肾强筋骨"}, {"name": "续断", "reason": "补肝肾"}],
        "formulas": ["右归丸"],
    },
    "大雪": {
        "principle": "寒冷加剧，温补进补",
        "diet": ["当归生姜羊肉汤", "阿胶补血", "枸杞、核桃温补", "多饮温水"],
        "lifestyle": ["保暖为重点", "早睡晚起", "泡脚加艾叶"],
        "exercise": ["室内太极", "慢走", "拉伸"],
        "acupoints": [{"name": "气海", "location": "脐下二横指", "effect": "温补元气"}],
        "herbs": [{"name": "人参", "reason": "大补元气"}, {"name": "鹿茸", "reason": "补肾壮阳"}],
        "formulas": ["十全大补汤"],
    },
    "冬至": {
        "principle": "阴极阳生，温补养藏",
        "diet": ["饺子、汤圆传统食物", "羊肉汤温补", "阿胶、红枣补血", "忌寒凉"],
        "lifestyle": ["早睡晚起", "保暖防寒", "静养", "艾灸关元穴"],
        "exercise": ["室内八段锦", "太极", "慢走"],
        "acupoints": [{"name": "神阙", "location": "肚脐", "effect": "温阳救逆"}],
        "herbs": [{"name": "附子", "reason": "回阳救逆"}, {"name": "干姜", "reason": "温中散寒"}],
        "formulas": ["四逆汤", "参附汤"],
    },
    "小寒": {
        "principle": "寒冷时节，温补御寒",
        "diet": ["羊肉、牛肉温补", "生姜红枣茶暖身", "黑米、黑豆粥补肾", "忌冰冷"],
        "lifestyle": ["注意防寒保暖", "早睡晚起", "泡脚艾灸"],
        "exercise": ["室内运动", "慢跑（午后）", "瑜伽"],
        "acupoints": [{"name": "太溪", "location": "内踝与跟腱之间凹陷", "effect": "滋补肾阴"}],
        "herbs": [{"name": "菟丝子", "reason": "补肾固精"}, {"name": "肉苁蓉", "reason": "补肾壮阳"}],
        "formulas": ["左归丸"],
    },
    "大寒": {
        "principle": "一年最冷，大补养藏",
        "diet": ["温热滋补食物", "八宝粥补气血", "当归羊肉汤", "多饮温水"],
        "lifestyle": ["保暖为主", "早睡晚起", "静养", "为春季升发做准备"],
        "exercise": ["室内太极", "八段锦", "慢走"],
        "acupoints": [{"name": "涌泉", "location": "足底前三分之一", "effect": "引火归元，温补肾阳"}],
        "herbs": [{"name": "核桃", "reason": "补肾固精"}, {"name": "黑芝麻", "reason": "补肝肾"}],
        "formulas": ["肾气丸"],
    },
}


@router.get("")
async def get_seasonal_health(
    term: str | None = None,
    current_user: dict = Depends(get_current_user),
):
    """Get detailed seasonal health guidance.

    Args:
        term: Optional solar term name. If omitted, returns current term.
    """
    today = date.today()

    if term and term in TERM_DETAIL:
        solar_term = term
    else:
        solar_term = get_solar_term(today)

    season = get_season(solar_term)
    next_term_name, days_to_next = get_next_term(today)
    detail = TERM_DETAIL.get(solar_term, {})

    all_terms = [
        {
            "name": name,
            "season": TERM_SEASON.get(name, ""),
            "month": month,
            "is_current": name == solar_term,
        }
        for name, month, _ in SOLAR_TERMS
    ]

    return {
        "current_term": solar_term,
        "season": season,
        "next_term": next_term_name,
        "days_to_next_term": days_to_next,
        "principle": detail.get("principle", ""),
        "diet": detail.get("diet", []),
        "lifestyle": detail.get("lifestyle", []),
        "exercise": detail.get("exercise", []),
        "acupoints": detail.get("acupoints", []),
        "herbs": detail.get("herbs", []),
        "formulas": detail.get("formulas", []),
        "all_terms": all_terms,
    }
