"""外治理疗知识库种子数据 (spec §9.6).

33 therapies across 6 categories: 刮痧/推拿/艾灸/拔罐/针刺/刺血.
All data in Chinese domain language (AGENTS.md §1.7).
"""

from __future__ import annotations


import logging

logger = logging.getLogger(__name__)
from typing import Any


THERAPIES: list[dict[str, Any]] = [
    # ===================================================================
    # 刮痧 (guasha) — risk_level: medium
    # ===================================================================
    {
        "id": "therapy-guasha-001", "name": "感冒刮痧", "category": "刮痧",
        "risk_level": "medium", "home_use_safe": 1, "display_only": 0,
        "description": "在背部督脉及膀胱经刮痧，疏风解表、发散邪气，适用于风寒或风热感冒初起。",
        "indications": "风寒感冒、风热感冒初起、恶寒发热、头痛无汗、鼻塞流涕。",
        "contraindications": "皮肤破损、感染、出血性疾病、孕妇腹部腰骶部、醉酒疲劳、严重心脑血管疾病。",
        "operation_steps": "1. 涂抹刮痧油于背部；2. 用刮板以45°角沿督脉从大椎向下单向刮至腰骶；3. 刮膀胱经第一侧线（大杼至大肠俞）；4. 每部位刮20-30次至出痧；5. 刮后饮温水，避风保暖。",
        "duration": "15-20分钟", "frequency": "同部位间隔3-5天",
        "precautions": "刮痧力度由轻渐重，单向刮拭不可往返；出痧后4小时内不宜洗澡；避风寒。",
        "properties": {"tools": ["水牛角刮板", "砭石刮板"], "medium": "刮痧油", "direction": "单向刮拭"},
        "acupoints": [
            {"acupoint_name": "大椎", "location": "第7颈椎棘突下", "function": "疏风解表退热", "meridian": "督脉", "is_primary": 1},
            {"acupoint_name": "风门", "location": "第2胸椎棘突下旁开1.5寸", "function": "祛风散寒", "meridian": "足太阳膀胱经", "is_primary": 1},
            {"acupoint_name": "肺俞", "location": "第3胸椎棘突下旁开1.5寸", "function": "宣肺解表", "meridian": "足太阳膀胱经", "is_primary": 0},
        ],
    },
    {
        "id": "therapy-guasha-002", "name": "颈肩刮痧", "category": "刮痧",
        "risk_level": "medium", "home_use_safe": 1, "display_only": 0,
        "description": "在颈部及肩部刮痧，舒筋通络，缓解颈肩僵硬疼痛。",
        "indications": "颈椎病、落枕、颈肩综合征、长期伏案工作颈肩酸痛。",
        "contraindications": "颈部皮肤破损、颈椎骨折、严重颈椎病伴神经压迫、孕妇肩井穴。",
        "operation_steps": "1. 涂刮痧油；2. 从风池穴沿颈侧刮至肩井；3. 刮天柱至大椎；4. 肩部从肩井向外刮；5. 每部位20-30次。",
        "duration": "15-20分钟", "frequency": "同部位间隔3-5天",
        "precautions": "颈部力度宜轻，避免压迫颈动脉窦；单向刮拭。",
        "properties": {"tools": ["水牛角刮板"], "medium": "刮痧油"},
        "acupoints": [
            {"acupoint_name": "风池", "location": "枕骨下，斜方肌外侧凹陷中", "function": "祛风解表通络", "meridian": "足少阳胆经", "is_primary": 1},
            {"acupoint_name": "肩井", "location": "大椎与肩峰连线中点", "function": "舒筋活络", "meridian": "足少阳胆经", "is_primary": 1},
            {"acupoint_name": "天柱", "location": "后发际正中旁开1.3寸", "function": "舒筋通络", "meridian": "足太阳膀胱经", "is_primary": 0},
        ],
    },
    {
        "id": "therapy-guasha-003", "name": "背部刮痧", "category": "刮痧",
        "risk_level": "medium", "home_use_safe": 1, "display_only": 0,
        "description": "沿背部督脉和膀胱经刮痧，调理脏腑功能，促进气血运行。",
        "indications": "疲劳综合征、背痛、脏腑功能失调、亚健康调理。",
        "contraindications": "背部皮肤破损、脊柱骨折、出血性疾病、孕妇背部特定穴位。",
        "operation_steps": "1. 涂刮痧油；2. 督脉从大椎至长强；3. 膀胱经第一侧线及第二侧线；4. 逐段刮至出痧。",
        "duration": "20-30分钟", "frequency": "同部位间隔3-5天",
        "precautions": "力度均匀，背部正中线（棘突）不宜直接刮；单向操作。",
        "properties": {"tools": ["水牛角刮板"], "medium": "刮痧油"},
        "acupoints": [
            {"acupoint_name": "大椎", "location": "第7颈椎棘突下", "function": "清热解表", "meridian": "督脉", "is_primary": 1},
            {"acupoint_name": "至阳", "location": "第7胸椎棘突下", "function": "宽胸理气", "meridian": "督脉", "is_primary": 0},
            {"acupoint_name": "命门", "location": "第2腰椎棘突下", "function": "温肾壮阳", "meridian": "督脉", "is_primary": 0},
        ],
    },
    {
        "id": "therapy-guasha-004", "name": "中暑刮痧", "category": "刮痧",
        "risk_level": "medium", "home_use_safe": 1, "display_only": 0,
        "description": "刮痧用于中暑急救辅助，清热解暑、疏通经络。",
        "indications": "中暑先兆、轻度中暑、暑热头晕胸闷、恶心乏力。",
        "contraindications": "重度中暑需立即就医不可仅用刮痧、皮肤破损、昏迷患者。",
        "operation_steps": "1. 将患者移至阴凉处；2. 刮大椎、曲池、委中；3. 颈部及背部膀胱经；4. 力度适中，至痧痕出现。",
        "duration": "10-15分钟", "frequency": "按需",
        "precautions": "重度中暑为急症须立即就医；刮痧仅作辅助。",
        "properties": {"tools": ["瓷勺（替代工具）"], "medium": "清水或植物油"},
        "acupoints": [
            {"acupoint_name": "大椎", "location": "第7颈椎棘突下", "function": "清热解暑", "meridian": "督脉", "is_primary": 1},
            {"acupoint_name": "曲池", "location": "肘横纹外侧端", "function": "清热退热", "meridian": "手阳明大肠经", "is_primary": 1},
            {"acupoint_name": "委中", "location": "腘窝横纹中点", "function": "清暑泄热", "meridian": "足太阳膀胱经", "is_primary": 0},
        ],
    },
    {
        "id": "therapy-guasha-005", "name": "头痛刮痧", "category": "刮痧",
        "risk_level": "medium", "home_use_safe": 1, "display_only": 0,
        "description": "在头颈部刮痧，疏风通络止痛，适用于外感及紧张性头痛。",
        "indications": "风寒头痛、紧张性头痛、血管性头痛（非急性发作期）。",
        "contraindications": "颅内病变所致头痛需就医、头皮破损、皮肤感染、严重高血压。",
        "operation_steps": "1. 涂刮痧油；2. 从太阳穴向后刮至风池；3. 风池至肩井；4. 头部以梳理法轻刮。",
        "duration": "10-15分钟", "frequency": "同部位间隔3-5天",
        "precautions": "头部刮痧力度宜轻；不明原因持续头痛应及时就医。",
        "properties": {"tools": ["砭石梳", "水牛角刮板"], "medium": "刮痧油"},
        "acupoints": [
            {"acupoint_name": "太阳", "location": "眉梢与目外眦之间向后约1寸凹陷处", "function": "疏风清热止痛", "meridian": "经外奇穴", "is_primary": 1},
            {"acupoint_name": "风池", "location": "枕骨下凹陷中", "function": "祛风通络", "meridian": "足少阳胆经", "is_primary": 1},
            {"acupoint_name": "百会", "location": "头顶正中线与前发际交点向后5寸", "function": "升阳举陷醒脑", "meridian": "督脉", "is_primary": 0},
        ],
    },
    # ===================================================================
    # 推拿 (tuina) — risk_level: low (self-massage) / medium (full body)
    # ===================================================================
    {
        "id": "therapy-tuina-001", "name": "颈椎推拿", "category": "推拿",
        "risk_level": "low", "home_use_safe": 1, "display_only": 0,
        "description": "自我按摩颈部肌群，舒筋活络，缓解颈部疲劳僵硬。",
        "indications": "颈椎疲劳、落枕、颈肩综合征、长期低头颈部不适。",
        "contraindications": "颈椎骨折、脱位、严重颈椎管狭窄、颈椎肿瘤、急性炎症期。",
        "operation_steps": "1. 用拇指揉风池穴1分钟；2. 拿捏颈后肌群（斜方肌）3-5遍；3. 按揉肩井穴；4. 轻柔前后左右活动颈部。",
        "duration": "10-15分钟", "frequency": "每日1-2次",
        "precautions": "力度由轻到重，酸胀舒适为度；切忌暴力扳颈；如出现头晕手麻立即停止并就医。",
        "properties": {"techniques": ["按法", "揉法", "拿法"], "selfApplicable": True},
        "acupoints": [
            {"acupoint_name": "风池", "location": "枕骨下凹陷中", "function": "舒筋通络止痛", "meridian": "足少阳胆经", "is_primary": 1},
            {"acupoint_name": "肩井", "location": "大椎与肩峰连线中点", "function": "舒筋解痉", "meridian": "足少阳胆经", "is_primary": 1},
            {"acupoint_name": "天宗", "location": "肩胛骨冈下窝中央", "function": "舒筋活络", "meridian": "手太阳小肠经", "is_primary": 0},
        ],
    },
    {
        "id": "therapy-tuina-002", "name": "肩周推拿", "category": "推拿",
        "risk_level": "low", "home_use_safe": 1, "display_only": 0,
        "description": "按摩肩部肌群及穴位，松解粘连，改善肩关节活动度。",
        "indications": "肩周炎（五十肩）、肩部酸痛、肩关节活动受限。",
        "contraindications": "肩关节骨折、脱位、肩部急性化脓性炎症、肩袖撕裂急性期。",
        "operation_steps": "1. 揉肩前（肩髃穴）及肩后（肩髎穴）；2. 拿三角肌；3. 按天宗、肩贞；4. 配合肩关节被动活动。",
        "duration": "15-20分钟", "frequency": "每日1次",
        "precautions": "以患者能耐受为度；肩周炎急性期以轻柔手法为主。",
        "properties": {"techniques": ["按法", "揉法", "摇法"], "selfApplicable": True},
        "acupoints": [
            {"acupoint_name": "肩髃", "location": "肩部三角肌上，肩峰前下方凹陷处", "function": "疏通肩部经络", "meridian": "手阳明大肠经", "is_primary": 1},
            {"acupoint_name": "肩髎", "location": "肩峰后下方凹陷处", "function": "祛风通络", "meridian": "手少阳三焦经", "is_primary": 1},
            {"acupoint_name": "肩贞", "location": "腋后皱襞上1寸", "function": "舒筋止痛", "meridian": "手太阳小肠经", "is_primary": 0},
        ],
    },
    {
        "id": "therapy-tuina-003", "name": "小儿推拿", "category": "推拿",
        "risk_level": "low", "home_use_safe": 1, "display_only": 0,
        "description": "适用于小儿的特定推拿手法，如补脾经、揉板门、捏脊，调理脾胃、增强免疫。",
        "indications": "小儿消化不良、积食、腹泻、便秘、免疫力低下、夜啼。",
        "contraindications": "小儿皮肤破损感染、骨折、急性传染病发热期、恶性肿瘤。",
        "operation_steps": "1. 补脾经：旋推拇指末节螺纹面100-300次；2. 揉板门：揉手掌大鱼际100-200次；3. 捏脊：从长强至大椎，双手交替捏推3-5遍；4. 顺时针摩腹2-3分钟。",
        "duration": "10-20分钟", "frequency": "每日1次",
        "precautions": "手法轻柔，使用滑石粉或爽身粉作介质；小儿哭闹不配合时暂停；仅适用6个月以上婴幼儿。",
        "properties": {"techniques": ["推法", "揉法", "捏法", "摩法"], "selfApplicable": True, "ageRange": "6个月-7岁"},
        "acupoints": [
            {"acupoint_name": "脾经", "location": "拇指末节螺纹面", "function": "健脾和胃", "meridian": "小儿特定穴位", "is_primary": 1},
            {"acupoint_name": "板门", "location": "手掌大鱼际平面", "function": "消食化滞", "meridian": "小儿特定穴位", "is_primary": 1},
            {"acupoint_name": "脊柱", "location": "后正中线，自第1胸椎至尾椎", "function": "调和阴阳健脾强身", "meridian": "督脉", "is_primary": 0},
        ],
    },
    {
        "id": "therapy-tuina-004", "name": "腰部推拿", "category": "推拿",
        "risk_level": "low", "home_use_safe": 1, "display_only": 0,
        "description": "按摩腰部穴位和肌群，温经散寒、舒筋止痛。",
        "indications": "慢性腰肌劳损、腰酸痛、肾虚腰痛、轻度腰椎间盘突出缓解期。",
        "contraindications": "腰椎骨折、急性腰椎间盘突出压迫神经、腰部肿瘤、严重骨质疏松。",
        "operation_steps": "1. 擦肾俞至温热；2. 揉腰眼（肾俞旁开）；3. 按压大肠俞；4. 拨揉竖脊肌；5. 叩击腰部。",
        "duration": "15-20分钟", "frequency": "每日1次",
        "precautions": "避免暴力按压脊柱正中；如有下肢放射痛应就医。",
        "properties": {"techniques": ["按法", "揉法", "擦法", "拨法"], "selfApplicable": True},
        "acupoints": [
            {"acupoint_name": "肾俞", "location": "第2腰椎棘突下旁开1.5寸", "function": "温肾壮腰", "meridian": "足太阳膀胱经", "is_primary": 1},
            {"acupoint_name": "大肠俞", "location": "第4腰椎棘突下旁开1.5寸", "function": "舒筋活络", "meridian": "足太阳膀胱经", "is_primary": 0},
            {"acupoint_name": "腰眼", "location": "第4腰椎棘突下旁开3.5寸", "function": "强腰壮肾", "meridian": "经外奇穴", "is_primary": 0},
        ],
    },
    {
        "id": "therapy-tuina-005", "name": "头面部推拿", "category": "推拿",
        "risk_level": "low", "home_use_safe": 1, "display_only": 0,
        "description": "按摩头面部穴位，安神醒脑、疏风止痛，适合日常保健。",
        "indications": "头痛头晕、失眠、眼疲劳、面部痉挛、精神紧张。",
        "contraindications": "面部皮肤感染、急性炎症、面神经麻痹急性期。",
        "operation_steps": "1. 开天门（从印堂推至神庭）24次；2. 推坎宫（眉弓）24次；3. 揉太阳穴；4. 按百会、四神聪；5. 梳理头皮。",
        "duration": "10-15分钟", "frequency": "每日1-2次",
        "precautions": "面部皮肤薄，力度轻柔；眼周避开直接按压眼球。",
        "properties": {"techniques": ["推法", "揉法", "按法"], "selfApplicable": True},
        "acupoints": [
            {"acupoint_name": "太阳", "location": "眉梢与目外眦之间向后约1寸凹陷处", "function": "疏风清热止痛", "meridian": "经外奇穴", "is_primary": 1},
            {"acupoint_name": "百会", "location": "头顶正中", "function": "升阳醒脑安神", "meridian": "督脉", "is_primary": 1},
            {"acupoint_name": "印堂", "location": "两眉头连线中点", "function": "安神定志", "meridian": "经外奇穴", "is_primary": 0},
        ],
    },
    {
        "id": "therapy-tuina-006", "name": "腹部推拿", "category": "推拿",
        "risk_level": "low", "home_use_safe": 1, "display_only": 0,
        "description": "顺时针摩腹配合穴位按揉，健脾和胃、通调肠腑。",
        "indications": "消化不良、腹胀、便秘、脾虚泄泻、失眠。",
        "contraindications": "急腹症、腹部手术后未愈、肠梗阻、孕妇腹部、腹腔肿瘤。",
        "operation_steps": "1. 顺时针摩腹3-5分钟；2. 揉中脘穴；3. 按天枢穴（双侧）；4. 按气海、关元。",
        "duration": "10-15分钟", "frequency": "每日1次，睡前或晨起",
        "precautions": "饭后1小时内不宜操作；力度以腹部微温为度。",
        "properties": {"techniques": ["摩法", "揉法", "按法"], "selfApplicable": True},
        "acupoints": [
            {"acupoint_name": "中脘", "location": "脐上4寸", "function": "健脾和胃降逆", "meridian": "任脉", "is_primary": 1},
            {"acupoint_name": "天枢", "location": "脐中旁开2寸", "function": "调中和胃通便", "meridian": "足阳明胃经", "is_primary": 1},
            {"acupoint_name": "关元", "location": "脐下3寸", "function": "温补下元", "meridian": "任脉", "is_primary": 0},
        ],
    },
    # ===================================================================
    # 艾灸 (moxibustion) — risk_level: medium
    # ===================================================================
    {
        "id": "therapy-moxa-001", "name": "足三里艾灸", "category": "艾灸",
        "risk_level": "medium", "home_use_safe": 1, "display_only": 0,
        "description": "艾灸足三里穴，健脾和胃、扶正培元，为保健要穴。",
        "indications": "脾胃虚弱、免疫力低下、疲劳乏力、慢性腹泻、虚劳诸证。",
        "contraindications": "阴虚火旺、阴虚质、孕妇、皮肤过敏、糖尿病感觉减退者需他人协助。",
        "operation_steps": "1. 定位足三里（犊鼻下3寸，胫骨前嵴外开一横指）；2. 点燃艾条，距皮肤2-3cm悬灸；3. 以局部温热不烫为度；4. 每穴10-20分钟。",
        "duration": "每穴10-20分钟", "frequency": "每日或隔日1次",
        "precautions": "单穴不超过20分钟；每次艾灸不超过3穴；灸后饮温水；避免烫伤。",
        "properties": {"moxaType": "温和灸", "distance": "2-3cm", "maxPointsPerSession": 3},
        "acupoints": [
            {"acupoint_name": "足三里", "location": "犊鼻下3寸，胫骨前嵴外开一横指", "function": "健脾和胃扶正培元", "meridian": "足阳明胃经", "is_primary": 1},
        ],
    },
    {
        "id": "therapy-moxa-002", "name": "关元艾灸", "category": "艾灸",
        "risk_level": "medium", "home_use_safe": 1, "display_only": 0,
        "description": "艾灸关元穴，温补下元、培肾固本，适用于阳虚畏寒体质。",
        "indications": "阳虚畏寒、宫寒不孕、月经不调、遗尿遗精、慢性腹泻。",
        "contraindications": "阴虚火旺、孕妇腹部、皮肤破损、过饥过饱。",
        "operation_steps": "1. 定位关元（脐下3寸）；2. 艾条悬灸或隔姜灸；3. 温热感为度；4. 10-20分钟。",
        "duration": "10-20分钟", "frequency": "每日或隔日1次",
        "precautions": "孕妇禁灸关元；避免烫伤；灸后注意保暖避风。",
        "properties": {"moxaType": "温和灸/隔姜灸", "distance": "2-3cm", "maxPointsPerSession": 3},
        "acupoints": [
            {"acupoint_name": "关元", "location": "前正中线上，脐下3寸", "function": "温补下元培肾固本", "meridian": "任脉", "is_primary": 1},
        ],
    },
    {
        "id": "therapy-moxa-003", "name": "神阙艾灸", "category": "艾灸",
        "risk_level": "medium", "home_use_safe": 1, "display_only": 0,
        "description": "艾灸神阙（肚脐），温阳散寒、回阳救逆，多用隔盐灸或隔姜灸。",
        "indications": "脾肾阳虚、五更泻、腹冷痛、脱证、虚脱。",
        "contraindications": "阴虚火旺、孕妇、脐部感染、皮肤破损。",
        "operation_steps": "1. 患者仰卧；2. 脐中填食盐或放姜片；3. 上置艾炷灸之；4. 每次3-7壮。",
        "duration": "15-20分钟", "frequency": "每日或隔日1次",
        "precautions": "禁直接灸神阙（易感染）；隔盐灸或隔姜灸为宜。",
        "properties": {"moxaType": "隔盐灸/隔姜灸", "maxPointsPerSession": 1},
        "acupoints": [
            {"acupoint_name": "神阙", "location": "肚脐中央", "function": "温阳散寒回阳固脱", "meridian": "任脉", "is_primary": 1},
        ],
    },
    {
        "id": "therapy-moxa-004", "name": "命门艾灸", "category": "艾灸",
        "risk_level": "medium", "home_use_safe": 1, "display_only": 0,
        "description": "艾灸命门穴，温肾壮阳、强腰固本，适用于肾阳虚证。",
        "indications": "肾阳虚畏寒、腰膝酸软、阳痿早泄、五更泄泻、夜尿频多。",
        "contraindications": "阴虚火旺、皮肤破损、孕妇、过饥过饱。",
        "operation_steps": "1. 定位命门（第2腰椎棘突下）；2. 艾条悬灸或隔附子饼灸；3. 局部温热；4. 15-20分钟。",
        "duration": "15-20分钟", "frequency": "每日或隔日1次",
        "precautions": "避免烫伤；灸后保暖。",
        "properties": {"moxaType": "温和灸/隔附子灸", "distance": "2-3cm"},
        "acupoints": [
            {"acupoint_name": "命门", "location": "后正中线第2腰椎棘突下", "function": "温肾壮阳强腰固本", "meridian": "督脉", "is_primary": 1},
            {"acupoint_name": "肾俞", "location": "第2腰椎棘突下旁开1.5寸", "function": "补肾壮阳", "meridian": "足太阳膀胱经", "is_primary": 0},
        ],
    },
    {
        "id": "therapy-moxa-005", "name": "三阴交艾灸", "category": "艾灸",
        "risk_level": "medium", "home_use_safe": 1, "display_only": 0,
        "description": "艾灸三阴交，调经养血、健脾益肾，为妇科要穴。",
        "indications": "月经不调、痛经、带下、失眠、脾虚血弱。",
        "contraindications": "孕妇绝对禁灸三阴交（可能引发流产）、阴虚火旺。",
        "operation_steps": "1. 定位三阴交（内踝尖上3寸，胫骨内侧后缘）；2. 艾条悬灸；3. 温热为度；4. 10-15分钟。",
        "duration": "10-15分钟", "frequency": "隔日1次",
        "precautions": "孕妇绝对禁用；经期慎用。",
        "properties": {"moxaType": "温和灸", "distance": "2-3cm"},
        "acupoints": [
            {"acupoint_name": "三阴交", "location": "内踝尖上3寸，胫骨内侧后缘", "function": "调经养血健脾益肾", "meridian": "足太阴脾经", "is_primary": 1},
        ],
    },
    {
        "id": "therapy-moxa-006", "name": "中脘艾灸", "category": "艾灸",
        "risk_level": "medium", "home_use_safe": 1, "display_only": 0,
        "description": "艾灸中脘穴，健脾和胃、降逆止呕，适用于脾胃虚寒证。",
        "indications": "胃寒疼痛、慢性胃炎、呕吐、消化不良、腹胀。",
        "contraindications": "阴虚火旺、孕妇腹部、皮肤破损、过饥过饱。",
        "operation_steps": "1. 定位中脘（脐上4寸）；2. 艾条悬灸或隔姜灸；3. 局部温热舒适；4. 15-20分钟。",
        "duration": "15-20分钟", "frequency": "每日或隔日1次",
        "precautions": "饭后1小时内不宜灸；避免烫伤。",
        "properties": {"moxaType": "温和灸/隔姜灸", "distance": "2-3cm"},
        "acupoints": [
            {"acupoint_name": "中脘", "location": "前正中线上，脐上4寸", "function": "健脾和胃降逆止呕", "meridian": "任脉", "is_primary": 1},
        ],
    },
    # ===================================================================
    # 拔罐 (cupping) — risk_level: medium
    # ===================================================================
    {
        "id": "therapy-cupping-001", "name": "背部拔罐", "category": "拔罐",
        "risk_level": "medium", "home_use_safe": 1, "display_only": 0,
        "description": "在背部膀胱经走罐或留罐，疏通经络、祛湿散寒。",
        "indications": "背痛、感冒、湿气重、疲劳、脏腑功能调理。",
        "contraindications": "皮肤破损、出血性疾病、孕妇背部、水肿、高热抽搐。",
        "operation_steps": "1. 涂润滑油于背部；2. 在膀胱经走罐（来回推动火罐）至皮肤潮红；3. 或在肺俞、膈俞留罐5-10分钟；4. 起罐后擦拭。",
        "duration": "留罐5-10分钟", "frequency": "间隔3-5天",
        "precautions": "避免起泡；走罐力度均匀；皮肤过敏者慎用。",
        "properties": {"cuppingType": "走罐/留罐", "retentionTime": "5-10分钟"},
        "acupoints": [
            {"acupoint_name": "肺俞", "location": "第3胸椎棘突下旁开1.5寸", "function": "宣肺解表", "meridian": "足太阳膀胱经", "is_primary": 1},
            {"acupoint_name": "膈俞", "location": "第7胸椎棘突下旁开1.5寸", "function": "理血宽胸", "meridian": "足太阳膀胱经", "is_primary": 0},
            {"acupoint_name": "脾俞", "location": "第11胸椎棘突下旁开1.5寸", "function": "健脾祛湿", "meridian": "足太阳膀胱经", "is_primary": 0},
        ],
    },
    {
        "id": "therapy-cupping-002", "name": "肩部拔罐", "category": "拔罐",
        "risk_level": "medium", "home_use_safe": 1, "display_only": 0,
        "description": "在肩部穴位留罐，舒筋活络、祛风止痛。",
        "indications": "肩周炎、颈肩综合征、肩部酸痛。",
        "contraindications": "肩部皮肤破损、出血性疾病、孕妇肩部特定穴位。",
        "operation_steps": "1. 在肩井、天髎拔罐；2. 留罐5-10分钟；3. 或走罐至潮红。",
        "duration": "留罐5-10分钟", "frequency": "间隔3-5天",
        "precautions": "避免起泡；力度适中。",
        "properties": {"cuppingType": "留罐", "retentionTime": "5-10分钟"},
        "acupoints": [
            {"acupoint_name": "肩井", "location": "大椎与肩峰连线中点", "function": "舒筋祛风", "meridian": "足少阳胆经", "is_primary": 1},
            {"acupoint_name": "天髎", "location": "肩胛骨上角", "function": "舒筋止痛", "meridian": "手少阳三焦经", "is_primary": 0},
        ],
    },
    {
        "id": "therapy-cupping-003", "name": "腰部拔罐", "category": "拔罐",
        "risk_level": "medium", "home_use_safe": 1, "display_only": 0,
        "description": "在腰部穴位留罐，温经通络、散寒止痛。",
        "indications": "慢性腰肌劳损、寒湿腰痛、腰椎间盘突出缓解期。",
        "contraindications": "腰椎骨折、皮肤破损、出血性疾病、孕妇腰骶部。",
        "operation_steps": "1. 在肾俞、大肠俞、腰眼拔罐；2. 留罐5-10分钟。",
        "duration": "留罐5-10分钟", "frequency": "间隔3-5天",
        "precautions": "避免起泡；脊柱正中不宜拔罐。",
        "properties": {"cuppingType": "留罐", "retentionTime": "5-10分钟"},
        "acupoints": [
            {"acupoint_name": "肾俞", "location": "第2腰椎棘突下旁开1.5寸", "function": "温肾壮腰", "meridian": "足太阳膀胱经", "is_primary": 1},
            {"acupoint_name": "大肠俞", "location": "第4腰椎棘突下旁开1.5寸", "function": "舒筋通络", "meridian": "足太阳膀胱经", "is_primary": 0},
        ],
    },
    {
        "id": "therapy-cupping-004", "name": "感冒拔罐", "category": "拔罐",
        "risk_level": "medium", "home_use_safe": 1, "display_only": 0,
        "description": "在大椎、肺俞拔罐，祛风解表、宣肺散寒。",
        "indications": "风寒感冒、风热感冒初起、咳嗽。",
        "contraindications": "高热、皮肤破损、孕妇、出血性疾病。",
        "operation_steps": "1. 大椎穴拔罐留5-10分钟；2. 肺俞双侧拔罐；3. 或走罐背部膀胱经。",
        "duration": "留罐5-10分钟", "frequency": "间隔3-5天",
        "precautions": "拔罐后避风寒；不宜在同一部位反复拔。",
        "properties": {"cuppingType": "留罐", "retentionTime": "5-10分钟"},
        "acupoints": [
            {"acupoint_name": "大椎", "location": "第7颈椎棘突下", "function": "祛风解表", "meridian": "督脉", "is_primary": 1},
            {"acupoint_name": "肺俞", "location": "第3胸椎棘突下旁开1.5寸", "function": "宣肺止咳", "meridian": "足太阳膀胱经", "is_primary": 1},
        ],
    },
    {
        "id": "therapy-cupping-005", "name": "湿气拔罐", "category": "拔罐",
        "risk_level": "medium", "home_use_safe": 1, "display_only": 0,
        "description": "在脾俞、足三里、阴陵泉等穴拔罐，健脾祛湿。",
        "indications": "湿气重、困倦乏力、食欲不振、大便黏腻、痰湿体质。",
        "contraindications": "皮肤破损、出血性疾病、孕妇、阴虚体质慎用。",
        "operation_steps": "1. 背部脾俞、胃俞拔罐；2. 足三里、阴陵泉拔罐；3. 留罐5-10分钟。",
        "duration": "留罐5-10分钟", "frequency": "间隔3-5天",
        "precautions": "痰湿体质效果较好；阴虚体质不宜频繁拔罐。",
        "properties": {"cuppingType": "留罐", "retentionTime": "5-10分钟"},
        "acupoints": [
            {"acupoint_name": "脾俞", "location": "第11胸椎棘突下旁开1.5寸", "function": "健脾祛湿", "meridian": "足太阳膀胱经", "is_primary": 1},
            {"acupoint_name": "阴陵泉", "location": "胫骨内侧髁后下方凹陷处", "function": "健脾利湿", "meridian": "足太阴脾经", "is_primary": 0},
        ],
    },
    # ===================================================================
    # 针刺 (acupuncture) — risk_level: professional_only, display_only: 1
    # 仅知识展示，永不推荐自行操作
    # ===================================================================
    {
        "id": "therapy-acup-001", "name": "足三里针刺", "category": "针刺",
        "risk_level": "professional_only", "home_use_safe": 0, "display_only": 1,
        "description": "针刺足三里穴，健脾和胃、扶正培元。【仅知识展示，须由执业中医师操作，严禁自行针刺】",
        "indications": "胃痛、呕吐、腹胀、腹泻、虚劳、保健强身（仅限执业中医师操作）。",
        "contraindications": "非执业人员严禁操作；孕妇慎刺；局部皮肤感染；出血性疾病。",
        "operation_steps": "【仅供知识了解】直刺1-1.5寸，可灸。具体操作须由执业中医师执行。",
        "duration": "留针20-30分钟", "frequency": "由医师决定",
        "precautions": "针刺须由执业中医师操作，严禁自行操作；需严格消毒防感染。",
        "properties": {"depth": "直刺1-1.5寸", "professionalOnly": True, "neverRecommendHomeUse": True},
        "acupoints": [
            {"acupoint_name": "足三里", "location": "犊鼻下3寸，胫骨前嵴外开一横指", "function": "健脾和胃扶正培元", "meridian": "足阳明胃经", "is_primary": 1},
        ],
    },
    {
        "id": "therapy-acup-002", "name": "合谷针刺", "category": "针刺",
        "risk_level": "professional_only", "home_use_safe": 0, "display_only": 1,
        "description": "针刺合谷穴，疏风解表、镇痛通络。【仅知识展示，须由执业中医师操作，严禁自行针刺】",
        "indications": "头痛、牙痛、面瘫、咽喉肿痛、感冒（仅限执业中医师操作）。",
        "contraindications": "非执业人员严禁操作；孕妇禁刺合谷（可能引发流产）。",
        "operation_steps": "【仅供知识了解】直刺0.5-1寸，孕妇禁针。具体操作须由执业中医师执行。",
        "duration": "留针20-30分钟", "frequency": "由医师决定",
        "precautions": "针刺须由执业中医师操作；孕妇绝对禁针合谷。",
        "properties": {"depth": "直刺0.5-1寸", "professionalOnly": True, "neverRecommendHomeUse": True},
        "acupoints": [
            {"acupoint_name": "合谷", "location": "手背第1、2掌骨间，第2掌骨桡侧中点", "function": "疏风解表镇痛通络", "meridian": "手阳明大肠经", "is_primary": 1},
        ],
    },
    {
        "id": "therapy-acup-003", "name": "百会针刺", "category": "针刺",
        "risk_level": "professional_only", "home_use_safe": 0, "display_only": 1,
        "description": "针刺百会穴，升阳举陷、醒脑开窍。【仅知识展示，须由执业中医师操作，严禁自行针刺】",
        "indications": "头痛、眩晕、失眠、脱肛、中风后遗症（仅限执业中医师操作）。",
        "contraindications": "非执业人员严禁操作；头皮感染；婴幼儿囟门未闭者禁刺。",
        "operation_steps": "【仅供知识了解】平刺0.5-0.8寸。具体操作须由执业中医师执行。",
        "duration": "留针20-30分钟", "frequency": "由医师决定",
        "precautions": "针刺须由执业中医师操作；婴幼儿囟门未闭禁刺。",
        "properties": {"depth": "平刺0.5-0.8寸", "professionalOnly": True, "neverRecommendHomeUse": True},
        "acupoints": [
            {"acupoint_name": "百会", "location": "后发际正中直上7寸", "function": "升阳举陷醒脑开窍", "meridian": "督脉", "is_primary": 1},
        ],
    },
    {
        "id": "therapy-acup-004", "name": "三阴交针刺", "category": "针刺",
        "risk_level": "professional_only", "home_use_safe": 0, "display_only": 1,
        "description": "针刺三阴交穴，调经养血、健脾益肾。【仅知识展示，须由执业中医师操作，严禁自行针刺】",
        "indications": "月经不调、痛经、带下、遗精、失眠（仅限执业中医师操作）。",
        "contraindications": "非执业人员严禁操作；孕妇禁针三阴交。",
        "operation_steps": "【仅供知识了解】直刺1-1.5寸，孕妇禁针。具体操作须由执业中医师执行。",
        "duration": "留针20-30分钟", "frequency": "由医师决定",
        "precautions": "针刺须由执业中医师操作；孕妇绝对禁针三阴交。",
        "properties": {"depth": "直刺1-1.5寸", "professionalOnly": True, "neverRecommendHomeUse": True},
        "acupoints": [
            {"acupoint_name": "三阴交", "location": "内踝尖上3寸，胫骨内侧后缘", "function": "调经养血健脾益肾", "meridian": "足太阴脾经", "is_primary": 1},
        ],
    },
    {
        "id": "therapy-acup-005", "name": "大椎针刺", "category": "针刺",
        "risk_level": "professional_only", "home_use_safe": 0, "display_only": 1,
        "description": "针刺大椎穴，清热解表、截疟退热。【仅知识展示，须由执业中医师操作，严禁自行针刺】",
        "indications": "发热、感冒、咳喘、疟疾、颈项强痛（仅限执业中医师操作）。",
        "contraindications": "非执业人员严禁操作；局部皮肤感染。",
        "operation_steps": "【仅供知识了解】斜刺0.5-1寸（不可深刺以免伤及脊髓）。具体操作须由执业中医师执行。",
        "duration": "留针20-30分钟", "frequency": "由医师决定",
        "precautions": "针刺须由执业中医师操作；大椎穴不可深刺。",
        "properties": {"depth": "斜刺0.5-1寸", "professionalOnly": True, "neverRecommendHomeUse": True},
        "acupoints": [
            {"acupoint_name": "大椎", "location": "第7颈椎棘突下", "function": "清热解表截疟退热", "meridian": "督脉", "is_primary": 1},
        ],
    },
    # ===================================================================
    # 刺血 (pricking) — risk_level: high, display_only: 1
    # 仅知识展示，需专业医师操作
    # ===================================================================
    {
        "id": "therapy-pricking-001", "name": "耳尖刺血", "category": "刺血",
        "risk_level": "high", "home_use_safe": 0, "display_only": 1,
        "description": "耳尖穴点刺放血，清热退热明目。【仅知识展示，须由专业医师操作】",
        "indications": "高热、急性结膜炎、高血压头痛、麦粒肿（仅限专业医师操作）。",
        "contraindications": "非专业人员严禁操作；孕妇、出血性疾病、严重贫血、体质虚弱。",
        "operation_steps": "【仅供知识了解】揉搓耳尖充血后，三棱针点刺挤出3-5滴血。须由专业医师操作。",
        "duration": "数分钟", "frequency": "由医师决定",
        "precautions": "须由专业医师操作；严格消毒；术后按压止血。",
        "properties": {"bloodVolume": "3-5滴", "professionalOnly": True, "neverRecommendHomeUse": True},
        "acupoints": [
            {"acupoint_name": "耳尖", "location": "折耳向前，耳廓上端尖处", "function": "清热退热明目", "meridian": "经外奇穴", "is_primary": 1},
        ],
    },
    {
        "id": "therapy-pricking-002", "name": "少商刺血", "category": "刺血",
        "risk_level": "high", "home_use_safe": 0, "display_only": 1,
        "description": "少商穴点刺放血，清热利咽开窍。【仅知识展示，须由专业医师操作】",
        "indications": "咽喉肿痛、急性扁桃体炎、发热、昏迷（仅限专业医师操作）。",
        "contraindications": "非专业人员严禁操作；孕妇、出血性疾病、严重贫血。",
        "operation_steps": "【仅供知识了解】三棱针点刺少商穴，挤出3-5滴血。须由专业医师操作。",
        "duration": "数分钟", "frequency": "由医师决定",
        "precautions": "须由专业医师操作；严格消毒防感染。",
        "properties": {"bloodVolume": "3-5滴", "professionalOnly": True, "neverRecommendHomeUse": True},
        "acupoints": [
            {"acupoint_name": "少商", "location": "拇指桡侧指甲根角旁约0.1寸", "function": "清热利咽开窍", "meridian": "手太阴肺经", "is_primary": 1},
        ],
    },
    {
        "id": "therapy-pricking-003", "name": "十宣刺血", "category": "刺血",
        "risk_level": "high", "home_use_safe": 0, "display_only": 1,
        "description": "十宣穴（十指尖）点刺放血，清热开窍、醒神急救。【仅知识展示，须由专业医师操作】",
        "indications": "高热惊厥、昏迷、中暑、癫痫发作（仅限专业医师操作）。",
        "contraindications": "非专业人员严禁操作；孕妇、出血性疾病、严重贫血、体质极度虚弱。",
        "operation_steps": "【仅供知识了解】双手十指尖端（十宣穴），三棱针点刺各挤出3-5滴血。须由专业医师操作。",
        "duration": "数分钟", "frequency": "由医师决定",
        "precautions": "须由专业医师操作；为急救辅助手段；高热惊厥需同时拨打急救电话。",
        "properties": {"bloodVolume": "每穴3-5滴", "professionalOnly": True, "neverRecommendHomeUse": True},
        "acupoints": [
            {"acupoint_name": "十宣", "location": "双手十指尖端，距指甲游离缘0.1寸", "function": "清热开窍醒神", "meridian": "经外奇穴", "is_primary": 1},
        ],
    },
    {
        "id": "therapy-pricking-004", "name": "委中刺血", "category": "刺血",
        "risk_level": "high", "home_use_safe": 0, "display_only": 1,
        "description": "委中穴刺络放血，活血消肿、舒筋止痛。【仅知识展示，须由专业医师操作】",
        "indications": "急性腰扭伤、中暑、丹毒（仅限专业医师操作）。",
        "contraindications": "非专业人员严禁操作；孕妇、出血性疾病、腘窝静脉曲张。",
        "operation_steps": "【仅供知识了解】委中处暴露浅静脉，刺络拔罐放血。须由专业医师操作。",
        "duration": "数分钟", "frequency": "由医师决定",
        "precautions": "须由专业医师操作；避免刺伤深层腘动脉。",
        "properties": {"bloodVolume": "数滴至数毫升", "professionalOnly": True, "neverRecommendHomeUse": True},
        "acupoints": [
            {"acupoint_name": "委中", "location": "腘窝横纹中点", "function": "活血消肿舒筋止痛", "meridian": "足太阳膀胱经", "is_primary": 1},
        ],
    },
    {
        "id": "therapy-pricking-005", "name": "太阳刺血", "category": "刺血",
        "risk_level": "high", "home_use_safe": 0, "display_only": 1,
        "description": "太阳穴点刺放血，疏风清热止痛。【仅知识展示，须由专业医师操作】",
        "indications": "偏头痛、急性结膜炎、高血压头痛（仅限专业医师操作）。",
        "contraindications": "非专业人员严禁操作；孕妇、出血性疾病、严重贫血。",
        "operation_steps": "【仅供知识了解】太阳穴区显露浅静脉，点刺放血2-3滴。须由专业医师操作。",
        "duration": "数分钟", "frequency": "由医师决定",
        "precautions": "须由专业医师操作；太阳穴区域避免深刺。",
        "properties": {"bloodVolume": "2-3滴", "professionalOnly": True, "neverRecommendHomeUse": True},
        "acupoints": [
            {"acupoint_name": "太阳", "location": "眉梢与目外眦之间向后约1寸凹陷处", "function": "疏风清热止痛", "meridian": "经外奇穴", "is_primary": 1},
        ],
    },
]


THERAPY_SAFETY_RULES: list[dict[str, Any]] = [
    # --- 通用规则（适用全部疗法） ---
    {"id": "tsr-all-001", "therapy_category": "all", "rule_type": "absolute_contraindication",
     "condition_text": "孕妇腹部及腰骶部", "action": "禁止在该部位操作任何外治理疗", "severity": "critical"},
    {"id": "tsr-all-002", "therapy_category": "all", "rule_type": "absolute_contraindication",
     "condition_text": "皮肤破损或感染部位", "action": "禁止在破损处操作", "severity": "critical"},
    {"id": "tsr-all-003", "therapy_category": "all", "rule_type": "absolute_contraindication",
     "condition_text": "出血性疾病（血友病、血小板减少等）", "action": "全身禁止刮痧、拔罐、刺血、针刺等有创操作", "severity": "critical"},
    {"id": "tsr-all-004", "therapy_category": "all", "rule_type": "relative_contraindication",
     "condition_text": "过饥或过饱状态", "action": "不宜立即操作腹部及全身性理疗", "severity": "medium"},
    {"id": "tsr-all-005", "therapy_category": "all", "rule_type": "caution",
     "condition_text": "严重心脑血管疾病", "action": "须在医师指导下进行，避免强刺激", "severity": "high"},
    {"id": "tsr-all-006", "therapy_category": "all", "rule_type": "caution",
     "condition_text": "醉酒或极度疲劳", "action": "不宜进行刮痧、拔罐等强刺激理疗", "severity": "medium"},
    # --- 刮痧专用 ---
    {"id": "tsr-guasha-001", "therapy_category": "刮痧", "rule_type": "absolute_contraindication",
     "condition_text": "孕妇腹部、腰骶部", "action": "禁止在该部位刮痧", "severity": "critical"},
    {"id": "tsr-guasha-002", "therapy_category": "刮痧", "rule_type": "caution",
     "condition_text": "婴幼儿皮肤娇嫩", "action": "3岁以下不宜刮痧，3-7岁力度极轻", "severity": "medium"},
    {"id": "tsr-guasha-003", "therapy_category": "刮痧", "rule_type": "duration_limit",
     "condition_text": "同一部位刮痧间隔", "action": "同部位间隔3-5天，待痧退后再刮", "severity": "medium"},
    # --- 艾灸专用 ---
    {"id": "tsr-moxa-001", "therapy_category": "艾灸", "rule_type": "absolute_contraindication",
     "condition_text": "阴虚火旺、阴虚质体质", "action": "禁忌艾灸，推荐推拿替代", "severity": "high"},
    {"id": "tsr-moxa-002", "therapy_category": "艾灸", "rule_type": "absolute_contraindication",
     "condition_text": "孕妇腹部、三阴交穴", "action": "绝对禁止艾灸", "severity": "critical"},
    {"id": "tsr-moxa-003", "therapy_category": "艾灸", "rule_type": "duration_limit",
     "condition_text": "单穴艾灸超过20分钟", "action": "限制单穴10-20分钟，避免烫伤", "severity": "medium"},
    {"id": "tsr-moxa-004", "therapy_category": "艾灸", "rule_type": "duration_limit",
     "condition_text": "每次艾灸超过3个穴位", "action": "每次不超过3穴", "severity": "medium"},
    {"id": "tsr-moxa-005", "therapy_category": "艾灸", "rule_type": "population_restriction",
     "condition_text": "糖尿病感觉减退者", "action": "需他人协助观察温度，防烫伤", "severity": "high"},
    # --- 推拿专用 ---
    {"id": "tsr-tuina-001", "therapy_category": "推拿", "rule_type": "absolute_contraindication",
     "condition_text": "骨折或脱位部位", "action": "禁止在该部位操作推拿", "severity": "critical"},
    {"id": "tsr-tuina-002", "therapy_category": "推拿", "rule_type": "area_restriction",
     "condition_text": "关节扳法、脊柱正骨手法", "action": "仅限持证推拿医师操作，禁止自行正骨", "severity": "high"},
    {"id": "tsr-tuina-003", "therapy_category": "推拿", "rule_type": "relative_contraindication",
     "condition_text": "急性炎症、化脓性感染", "action": "局部禁止推拿", "severity": "high"},
    # --- 拔罐专用 ---
    {"id": "tsr-cupping-001", "therapy_category": "拔罐", "rule_type": "absolute_contraindication",
     "condition_text": "孕妇腰骶及腹部", "action": "禁止该部位拔罐", "severity": "critical"},
    {"id": "tsr-cupping-002", "therapy_category": "拔罐", "rule_type": "caution",
     "condition_text": "皮肤过敏或水肿部位", "action": "不宜拔罐", "severity": "medium"},
    {"id": "tsr-cupping-003", "therapy_category": "拔罐", "rule_type": "duration_limit",
     "condition_text": "留罐超过10分钟", "action": "留罐5-10分钟为宜，避免起泡", "severity": "medium"},
    # --- 刺血专用 ---
    {"id": "tsr-pricking-001", "therapy_category": "刺血", "rule_type": "absolute_contraindication",
     "condition_text": "所有条件", "action": "刺血疗法仅限知识展示，永不推荐自行操作，须由专业医师执行", "severity": "critical"},
    {"id": "tsr-pricking-002", "therapy_category": "刺血", "rule_type": "population_restriction",
     "condition_text": "孕妇、贫血、体质虚弱", "action": "严禁刺血操作", "severity": "critical"},
    # --- 针刺专用 ---
    {"id": "tsr-acupuncture-001", "therapy_category": "针刺", "rule_type": "absolute_contraindication",
     "condition_text": "所有条件", "action": "针刺疗法仅限知识展示，永不推荐自行操作，须由执业中医师执行", "severity": "critical"},
    {"id": "tsr-acupuncture-002", "therapy_category": "针刺", "rule_type": "population_restriction",
     "condition_text": "孕妇（合谷、三阴交、肩井等穴）", "action": "禁针穴位严禁针刺", "severity": "critical"},
    {"id": "tsr-acupuncture-003", "therapy_category": "针刺", "rule_type": "area_restriction",
     "condition_text": "婴幼儿囟门未闭、大椎等危险穴位", "action": "禁针或不可深刺", "severity": "critical"},
]


THERAPY_CATEGORIES = ["刮痧", "推拿", "艾灸", "拔罐", "针刺", "刺血"]
