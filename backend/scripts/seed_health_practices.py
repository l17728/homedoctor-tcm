#!/usr/bin/env python3
"""Seed ~40 养生功法 (health practice) entities into knowledge_entities.

Inserts:
- 15 core 功法 (entity_type="health_practice") — 太极拳/八段锦/金刚功/长寿功/站桩/打坐/...
- 10 门派 (entity_type="practice_school") — 武当/少林/全真/峨眉/正一/...
- 15 流派变体 (entity_type="health_practice") — 陈/杨/吴/武/孙式太极拳, 少林/道家/医家八段锦, ...
- relationships: derived_from / belongs_to_school / complementary_to

Idempotent via INSERT OR REPLACE. Uses aiosqlite directly (no app.* imports).

Usage:
    python3 scripts/seed_health_practices.py [--db PATH]

Default DB path: data/homedoctor.db  (env: HOMEDOCTOR_DATABASE_URL)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

import aiosqlite

from datetime import datetime, timedelta, timezone

CST = timezone(timedelta(hours=8))

# ---------------------------------------------------------------------------
# SQL templates (idempotent)
# ---------------------------------------------------------------------------

_INSERT_ENTITY = """INSERT OR REPLACE INTO knowledge_entities
    (id, entity_type, source_table, source_id, title, summary, keywords,
     tags, category, content_preview, properties, source_type, status,
     view_count, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)"""

_INSERT_REL = """INSERT OR REPLACE INTO entity_relationships
    (id, source_entity_id, target_entity_id, relationship_type,
     properties, weight, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)"""

# Create tables if missing (standalone safety net — matches app/database.py DDL)
_DDL = [
    """CREATE TABLE IF NOT EXISTS knowledge_entities (
        id TEXT PRIMARY KEY,
        entity_type TEXT NOT NULL,
        source_table TEXT NOT NULL,
        source_id TEXT,
        title TEXT NOT NULL,
        summary TEXT,
        keywords TEXT DEFAULT '[]',
        tags TEXT DEFAULT '[]',
        category TEXT,
        content_preview TEXT,
        properties TEXT DEFAULT '{}',
        source_type TEXT DEFAULT 'system',
        status TEXT DEFAULT 'active',
        tenant_id TEXT DEFAULT NULL,
        view_count INTEGER DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_ke_type ON knowledge_entities(entity_type)",
    "CREATE INDEX IF NOT EXISTS idx_ke_category ON knowledge_entities(category)",
    """CREATE TABLE IF NOT EXISTS entity_relationships (
        id TEXT PRIMARY KEY,
        source_entity_id TEXT NOT NULL,
        target_entity_id TEXT NOT NULL,
        relationship_type TEXT NOT NULL,
        properties TEXT DEFAULT '{}',
        weight REAL DEFAULT 1.0,
        tenant_id TEXT DEFAULT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (source_entity_id) REFERENCES knowledge_entities(id),
        FOREIGN KEY (target_entity_id) REFERENCES knowledge_entities(id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_er_source ON entity_relationships(source_entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_er_target ON entity_relationships(target_entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_er_type ON entity_relationships(relationship_type)",
]


def _now() -> str:
    return datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")


# ===========================================================================
# 15 CORE PRACTICES (entity_type="health_practice")
# ===========================================================================

CORE_PRACTICES: list[dict] = [
    {
        "id": "hp-taiji",
        "title": "太极拳",
        "summary": "内家拳法代表，以柔克刚、以静制动，动静结合的养生名拳。",
        "category": "内家拳法",
        "properties": {
            "pinyin": "tai ji quan",
            "origin": "相传由张三丰创于武当山，后经陈王廷发展成陈式太极拳，流传至今",
            "founder": "张三丰（传说），陈王廷（陈式）",
            "difficulty": "进阶",
            "practice_type": "动静结合",
            "duration_minutes": "20-40分钟",
            "best_time": "清晨或傍晚",
            "core_essence": "以柔克刚，以静制动，内外兼修；以意导气，以气运身。",
            "key_points": ["松静自然", "意气相随", "圆活连贯", "虚实分明", "上下相随"],
            "breathing": "腹式呼吸，动作与呼吸配合，讲究深、长、细、匀，开吸合呼",
            "mental_focus": "心静体松，意守丹田，神形合一，用意不用力",
            "steps": [
                {"name": "预备式", "points": "两脚并拢，身体中正，含胸拔背，意守丹田"},
                {"name": "起势", "points": "两脚开立与肩同宽，两臂徐徐上抬，与肩同高后下按"},
                {"name": "揽雀尾", "points": "掤、捋、挤、按四正手，体现太极拳核心劲法"},
                {"name": "单鞭", "points": "勾手与推掌配合，身法中正，力由脊发"},
                {"name": "云手", "points": "两手如云流转，腰为轴带动四肢，连绵不断"},
                {"name": "收势", "points": "两手缓缓下按，气沉丹田，静立片刻"},
            ],
            "indications": ["强身健体", "调节气血", "安神定志", "改善平衡", "延缓衰老"],
            "cautions": "膝关节有疾者动作宜高架子；练后不可立即冷水浴；饭后一小时内不宜练习",
            "benefits": "太极拳通过缓慢柔和的圆弧动作配合深长呼吸，调和阴阳、疏通经络，长期练习可强身健体、调节身心、改善平衡能力、延缓衰老，是老少皆宜的养生运动。",
        },
    },
    {
        "id": "hp-baduanjin",
        "title": "八段锦",
        "summary": "民间流传最广的导引功法，八式动作调理五脏六腑，简便易学。",
        "category": "导引功法",
        "properties": {
            "pinyin": "ba duan jin",
            "origin": "起源于宋代，由民间流传整理而成，历经多代完善",
            "founder": "民间流传（无单一创始人）",
            "difficulty": "入门",
            "practice_type": "动功",
            "duration_minutes": "15-30分钟",
            "best_time": "清晨起床后或睡前",
            "core_essence": "八式动作，每式针对一脏腑，意气形结合，简便易学。",
            "key_points": ["意气形结合", "动作舒展柔和", "呼吸自然", "循序渐进"],
            "breathing": "自然呼吸为主，配合动作升降开合，起吸落呼",
            "mental_focus": "意守丹田，神随形动，心静体松",
            "steps": [
                {"name": "两手托天理三焦", "points": "十指交叉上托，拔伸躯干，调理三焦气机"},
                {"name": "左右开弓似射雕", "points": "马步开弓，扩胸展臂，疏肝理气"},
                {"name": "调理脾胃须单举", "points": "单臂上举下按，调理脾胃升降"},
                {"name": "五劳七伤往后瞧", "points": "转头后视，刺激颈项，防治劳伤"},
                {"name": "摇头摆尾去心火", "points": "马步俯身摇摆，引心火下行"},
                {"name": "两手攀足固肾腰", "points": "前屈两手攀足，强腰固肾"},
                {"name": "攒拳怒目增气力", "points": "马步冲拳怒目，增力气、疏肝气"},
                {"name": "背后七颠百病消", "points": "足跟上提下颠，震荡全身，收功理气"},
            ],
            "indications": ["调理脏腑", "疏通经络", "强身健体", "改善消化", "安神助眠"],
            "cautions": "动作幅度循序渐进，腰膝有疾者量力而行；空腹或过饱不宜",
            "benefits": "八段锦八式动作分别对应五脏六腑，通过伸展、旋转、屈伸等动作疏通经络、调理气血，长期练习可增强体质、改善消化、安神助眠，是大众养生首选功法。",
        },
    },
    {
        "id": "hp-jingang",
        "title": "金刚功",
        "summary": "道教全真龙门派秘传功法，刚柔并济，以力催气，打通经脉。",
        "category": "道家功法",
        "properties": {
            "pinyin": "jin gang gong",
            "origin": "道教全真龙门派秘传，由张至顺道长公开传授",
            "founder": "张至顺道长（传授者）",
            "difficulty": "进阶",
            "practice_type": "动功",
            "duration_minutes": "20-30分钟",
            "best_time": "清晨面向东方",
            "core_essence": "刚柔并济，以力催气，以气运身，打通十二经脉。",
            "key_points": ["力从地起", "意守下丹田", "刚中带柔", "气贯四梢"],
            "breathing": "自然呼吸，动作发力时闭气或配合呼吸，劲达四梢",
            "mental_focus": "意守下丹田，力从地起，神气合一",
            "steps": [
                {"name": "双手插顶利三焦", "points": "双手上插，拔伸三焦"},
                {"name": "手足前后固肾腰", "points": "前后手足交替，强腰固肾"},
                {"name": "调理脾肤需单举", "points": "单臂上举，调理脾胃"},
                {"name": "左肝右肺如射雕", "points": "左右开弓，疏肝理肺"},
                {"name": "回头望足去心疾", "points": "回头望足，去心火"},
                {"name": "五劳七伤向后瞧", "points": "向后转头，调理劳伤"},
                {"name": "凤凰展翅周身力", "points": "展翅发力，强壮周身"},
                {"name": "两足顿顿饮嗜消", "points": "两足顿地，消食化滞"},
            ],
            "indications": ["强筋健骨", "疏通经脉", "培补元气", "强身健体"],
            "cautions": "动作发力需循序渐进，不可蛮力；高血压、心脏病患者宜柔和练习",
            "benefits": "金刚功以刚为主、刚柔并济，通过发力动作催动气血运行，打通十二经脉，强筋健骨、培补元气，是道家修身养性的上乘功法。",
        },
    },
    {
        "id": "hp-changshou",
        "title": "长寿功",
        "summary": "道教全真龙门派内练功法，配合金刚功练习，内练一口气。",
        "category": "道家功法",
        "properties": {
            "pinyin": "chang shou gong",
            "origin": "道教全真龙门派秘传，由张至顺道长公开传授",
            "founder": "张至顺道长（传授者）",
            "difficulty": "高级",
            "practice_type": "动静结合",
            "duration_minutes": "20-40分钟",
            "best_time": "子时（夜半）或清晨",
            "core_essence": "内练一口气，意行气行，神气合一，培补先天元气。",
            "key_points": ["意行气行", "神气合一", "松静自然", "内观返听"],
            "breathing": "胎息为主，绵绵若存，若有若无",
            "mental_focus": "意行气行，神气合一，内观返听，返本归元",
            "steps": [
                {"name": "第一段", "points": "长生开合，开合气机，启动内气"},
                {"name": "第二段", "points": "内气上行，气贯百会"},
                {"name": "第三段", "points": "内气下行，气沉丹田"},
                {"name": "第四段", "points": "大转乾坤，气行周天"},
            ],
            "indications": ["延年益寿", "培补元气", "安神定志", "修身养性"],
            "cautions": "需有金刚功基础；忌急功近利；练功期间清心寡欲",
            "benefits": "长寿功为内练秘法，通过意念引导内气运行，培补先天元气、延年益寿，与金刚功一外一内、相辅相成。",
        },
    },
    {
        "id": "hp-zhanzhuang",
        "title": "站桩",
        "summary": "外形不动、内气运行的静功桩法，培本固元的养生要法。",
        "category": "静功",
        "properties": {
            "pinyin": "zhan zhuang",
            "origin": "源于古代养生术与武术基本功，各家均有传承",
            "founder": "无单一创始人，武术与养生家共同发展",
            "difficulty": "入门",
            "practice_type": "静功",
            "duration_minutes": "15-45分钟（循序渐进）",
            "best_time": "清晨或傍晚",
            "core_essence": "外形不动，内气运行，以固定姿势激发经气，培本固元。",
            "key_points": ["松静自然", "意守丹田", "含胸拔背", "虚灵顶劲", "沉肩坠肘"],
            "breathing": "自然呼吸，渐进胎息，绵绵若存",
            "mental_focus": "松静自然，意守丹田，似守非守，若有若无",
            "steps": [
                {"name": "调身", "points": "两脚与肩同宽，屈膝松胯，两臂环抱胸前"},
                {"name": "调息", "points": "自然呼吸，逐渐过渡到腹式呼吸"},
                {"name": "调心", "points": "意守丹田，排除杂念，松静站立"},
                {"name": "收功", "points": "搓手浴面，拍打全身，气归丹田"},
            ],
            "indications": ["培本固元", "强健腿力", "养生治病", "调节神经", "增强免疫"],
            "cautions": "膝关节不适者不宜久站；高血压患者头部不宜过分前倾；循序渐进增加时长",
            "benefits": "站桩以静制动，外形不动而内气运行，通过特定姿势调动全身气血、培补元气，长期练习可强健腿力、增强免疫、养生治病。",
        },
    },
    {
        "id": "hp-dazuo",
        "title": "打坐",
        "summary": "又称静坐，调身、调息、调心三调合一的静功基础功法。",
        "category": "静功",
        "properties": {
            "pinyin": "da zuo",
            "origin": "源于古代养生术，佛道儒三家皆有静坐传统",
            "founder": "无单一创始人，释道儒三家共同发展",
            "difficulty": "入门",
            "practice_type": "静功",
            "duration_minutes": "20-60分钟（循序渐进）",
            "best_time": "子时（23-1点）、午时（11-13点）或清晨",
            "core_essence": "调身、调息、调心三调合一，由静入定，由定生慧。",
            "key_points": ["身正体松", "呼吸绵绵", "心无所住", "循序渐进"],
            "breathing": "自然呼吸→腹式呼吸→胎息，循序渐进",
            "mental_focus": "数息、随息、止观，由专注一境到心如止水",
            "steps": [
                {"name": "调身", "points": "散盘、单盘或双盘，脊柱正直，手结定印"},
                {"name": "调息", "points": "由粗到细，由短到长，绵绵若存"},
                {"name": "调心", "points": "数息（1-10）或随息，排除杂念"},
                {"name": "收功", "points": "搓手浴面，缓缓起身，气归丹田"},
            ],
            "indications": ["安神定志", "培补元气", "开发智慧", "缓解压力", "改善睡眠"],
            "cautions": "忌饱食后立即打坐；意念不可过重；出现幻境不可执着；循序渐进",
            "benefits": "打坐通过三调合一达到身心安宁，可安神定志、培补元气、开发智慧，是各派修行的共同基础功法。",
        },
    },
    {
        "id": "hp-wuqinxi",
        "title": "五禽戏",
        "summary": "华佗模仿虎鹿熊猿鸟五种动物创编的导引功法，强身健体名方。",
        "category": "导引功法",
        "properties": {
            "pinyin": "wu qin xi",
            "origin": "东汉末年华佗创编，依据《庄子》二禽戏发展而来",
            "founder": "华佗",
            "difficulty": "入门",
            "practice_type": "动功",
            "duration_minutes": "15-30分钟",
            "best_time": "清晨或傍晚",
            "core_essence": "模仿虎之威猛、鹿之安舒、熊之沉稳、猿之灵巧、鸟之轻捷，疏通经络。",
            "key_points": ["形神兼备", "意气相随", "动静相兼", "模仿神态"],
            "breathing": "自然呼吸，配合动作起伏，呼吸均匀",
            "mental_focus": "意随形动，神似为主，形神合一",
            "steps": [
                {"name": "虎戏", "points": "虎举、虎扑，威猛有力，疏通肝经"},
                {"name": "鹿戏", "points": "鹿抵、鹿奔，安舒舒展，益肾固腰"},
                {"name": "熊戏", "points": "熊运、熊晃，沉稳厚重，健脾和胃"},
                {"name": "猿戏", "points": "猿提、猿摘，灵巧敏捷，灵活心神"},
                {"name": "鸟戏", "points": "鸟伸、鸟飞，轻捷舒展，调畅肺气"},
            ],
            "indications": ["强身健体", "疏通气血", "调理脏腑", "灵活关节"],
            "cautions": "动作量力而行，关节炎患者幅度宜小；饭后不宜立即练习",
            "benefits": "五禽戏模仿五种动物的神态动作，全面锻炼身体各部位，疏通经络、调理脏腑，是历史最悠久的导引养生功法之一。",
        },
    },
    {
        "id": "hp-yijinjing",
        "title": "易筋经",
        "summary": "相传达摩祖师所传，易筋换骨、强健筋骨的导引名功。",
        "category": "导引功法",
        "properties": {
            "pinyin": "yi jin jing",
            "origin": "相传为达摩祖师在少林寺所传，见《易筋经》一书",
            "founder": "达摩祖师（传说）",
            "difficulty": "进阶",
            "practice_type": "动功",
            "duration_minutes": "20-30分钟",
            "best_time": "清晨或午后",
            "core_essence": "易筋换骨，通过特定姿势和呼吸变换筋骨，强壮体魄。",
            "key_points": ["动作舒展", "用力暗劲", "呼吸配合", "意守丹田"],
            "breathing": "腹式呼吸，配合动作发力，讲究深长有力",
            "mental_focus": "意守丹田，以意领气，以气运身",
            "steps": [
                {"name": "韦驮献杵第一势", "points": "立身中正，两掌合十，定心凝神"},
                {"name": "韦驮献杵第二势", "points": "两足分开，两掌平推，舒展筋骨"},
                {"name": "韦驮献杵第三势", "points": "两掌上托，拔伸全身"},
                {"name": "摘星换斗势", "points": "单手上举，回头视手"},
                {"name": "倒拽九牛尾势", "points": "弓步拽拳，用力暗劲"},
                {"name": "出爪亮翅势", "points": "两掌前推，亮翅发力"},
            ],
            "indications": ["强健筋骨", "疏通经脉", "增强体力", "改善体态"],
            "cautions": "发力动作需循序渐进；高血压、心脏病患者宜柔和练习",
            "benefits": "易筋经通过特定的伸筋拔骨动作配合呼吸，变换筋骨、强壮体魄，长期练习可强健筋骨、疏通经脉、增强体力。",
        },
    },
    {
        "id": "hp-liuzijue",
        "title": "六字诀",
        "summary": "以嘘呵呼呬吹嘻六字发音吐纳，对应肝心脾肺肾三焦的吐纳功法。",
        "category": "吐纳功法",
        "properties": {
            "pinyin": "liu zi jue",
            "origin": "南北朝陶弘景《养性延命录》已有记载，唐代孙思邈等传承发展",
            "founder": "陶弘景（最早记载）",
            "difficulty": "入门",
            "practice_type": "动静结合（以静为主）",
            "duration_minutes": "15-30分钟",
            "best_time": "清晨面向东方",
            "core_essence": "嘘呵呼呬吹嘻六字发音吐纳，分别对应肝心脾肺肾三焦，调理五脏六腑。",
            "key_points": ["发音准确", "吐气缓长", "吸气自然", "意守对应脏腑"],
            "breathing": "口吐鼻吸，吐气时发对应字音，缓、长、匀、细",
            "mental_focus": "意守对应脏腑，吐故纳新",
            "steps": [
                {"name": "嘘字诀（xū）", "points": "对应肝，平肝气，疏肝理气"},
                {"name": "呵字诀（hē）", "points": "对应心，清心火，宁心安神"},
                {"name": "呼字诀（hū）", "points": "对应脾，健脾胃，消食化滞"},
                {"name": "呬字诀（sī）", "points": "对应肺，润肺气，止咳平喘"},
                {"name": "吹字诀（chuī）", "points": "对应肾，固肾气，强腰固本"},
                {"name": "嘻字诀（xī）", "points": "对应三焦，理三焦，通调水道"},
            ],
            "indications": ["调理五脏六腑", "疏肝理气", "安神助眠", "强身健体"],
            "cautions": "吐气不可过度，以免伤气；练后宜饮温水；空腹不宜",
            "benefits": "六字诀通过六种发音吐纳分别调理五脏六腑，简便易学，可疏肝理气、安神助眠、强身健体。",
        },
    },
    {
        "id": "hp-qigong",
        "title": "内丹功",
        "summary": "道家内丹修炼，炼精化气、炼气化神、炼神还虚的内功体系。",
        "category": "内功",
        "properties": {
            "pinyin": "nei dan gong",
            "origin": "源于道家内丹术，魏伯阳《周易参同契》为万古丹经王",
            "founder": "魏伯阳、张伯端、丘处机等历代丹家",
            "difficulty": "高级",
            "practice_type": "静功",
            "duration_minutes": "30-60分钟",
            "best_time": "子时（活子时）",
            "core_essence": "炼精化气，炼气化神，炼神还虚，三关修炼，返本归元。",
            "key_points": ["凝神入气穴", "火候适当", "性命双修", "清静无为"],
            "breathing": "胎息为主，若有若无，绵绵若存",
            "mental_focus": "凝神入气穴，意守下丹田，火候适当",
            "steps": [
                {"name": "初关·炼精化气", "points": "小周天，精气沿任督二脉循环"},
                {"name": "中关·炼气化神", "points": "大周天，气通十二经脉"},
                {"name": "上关·炼神还虚", "points": "出神入化，返本归元"},
            ],
            "indications": ["培补元气", "修身养性", "延年益寿", "开发智慧"],
            "cautions": "需明师指点；忌盲目意守导致偏差；火候不可过重",
            "benefits": "内丹功是道家修行的核心，通过精气神三宝的转化修炼，培补元气、修身养性、延年益寿。",
        },
    },
    {
        "id": "hp-shierduanjin",
        "title": "十二段锦",
        "summary": "又称坐式八段锦，坐式导引十二段动作，防病治病、延年益寿。",
        "category": "导引功法",
        "properties": {
            "pinyin": "shi er duan jin",
            "origin": "由八段锦发展而来，明清时期广泛流传",
            "founder": "无单一创始人",
            "difficulty": "入门",
            "practice_type": "动静结合",
            "duration_minutes": "20-30分钟",
            "best_time": "清晨或睡前",
            "core_essence": "坐式导引，十二段动作依次练习，防病治病。",
            "key_points": ["坐式练习", "动作柔和", "呼吸配合", "意守丹田"],
            "breathing": "自然呼吸为主，配合动作",
            "mental_focus": "意守丹田，心静体松",
            "steps": [
                {"name": "第一段", "points": "闭目冥心坐，握固静思神"},
                {"name": "第二段", "points": "叩齿三十六，两手抱昆仑"},
                {"name": "第三段", "points": "左右鸣天鼓，二十四度闻"},
                {"name": "后续各段", "points": "微摆撼天柱、赤龙搅水津、闭气搓手热、背摩后精门、尽钩攀足、左右辘轳转、河车搬运、想发火烧身"},
            ],
            "indications": ["防病治病", "延年益寿", "安神助眠", "强身健体"],
            "cautions": "坐式练习注意脊柱正直；动作柔和，不可用蛮力",
            "benefits": "十二段锦以坐式为主，动作柔和，适合体弱者或老年人练习，可防病治病、延年益寿。",
        },
    },
    {
        "id": "hp-mawangdui",
        "title": "马王堆导引术",
        "summary": "依据马王堆汉墓出土导引图复原整理的古代导引功法。",
        "category": "导引功法",
        "properties": {
            "pinyin": "ma wang dui dao yin shu",
            "origin": "依据1973年长沙马王堆三号汉墓出土的《导引图》复原整理",
            "founder": "无单一创始人（古代导引图复原）",
            "difficulty": "进阶",
            "practice_type": "动功",
            "duration_minutes": "20-30分钟",
            "best_time": "清晨",
            "core_essence": "模仿出土导引图动作，结合现代运动学整理，疏通经络。",
            "key_points": ["动作仿古", "形意结合", "呼吸自然", "意守丹田"],
            "breathing": "腹式呼吸，配合动作起伏",
            "mental_focus": "意随形动，神形合一",
            "steps": [
                {"name": "引腰痛", "points": "前俯后仰，强腰固肾"},
                {"name": "引膝痛", "points": "屈伸膝部，灵活关节"},
                {"name": "引腹中", "points": "扭转躯干，调理腹部"},
                {"name": "引聋", "points": "鸣天鼓等，聪耳开窍"},
            ],
            "indications": ["疏通经络", "强身健体", "灵活关节", "调理脏腑"],
            "cautions": "动作幅度循序渐进；关节炎患者量力而行",
            "benefits": "马王堆导引术复原了西汉时期的导引养生法，动作古朴自然，可疏通经络、强身健体、灵活关节。",
        },
    },
    {
        "id": "hp-dawu",
        "title": "大舞",
        "summary": "上古时期以舞宣导、疏通经络的导引功法，历史悠久。",
        "category": "古代导引",
        "properties": {
            "pinyin": "da wu",
            "origin": "源于上古时代，《吕氏春秋》记载“阴康氏作舞”宣导气机",
            "founder": "阴康氏（传说）",
            "difficulty": "进阶",
            "practice_type": "动功",
            "duration_minutes": "20-30分钟",
            "best_time": "清晨",
            "core_essence": "以舞宣导，通过舞蹈动作疏通经络、调和气血。",
            "key_points": ["舞姿舒展", "气机宣畅", "形神合一", "节奏鲜明"],
            "breathing": "自然呼吸，配合舞姿节奏",
            "mental_focus": "意随舞动，神形合一",
            "steps": [
                {"name": "昂首势", "points": "昂首挺胸，宣发气机"},
                {"name": "开胯势", "points": "开胯旋腰，疏通下焦"},
                {"name": "抻腰势", "points": "抻拉腰背，强腰固肾"},
                {"name": "震体势", "points": "震荡全身，疏通经脉"},
            ],
            "indications": ["疏通经络", "调和气血", "强身健体", "舒缓情志"],
            "cautions": "舞姿幅度循序渐进；关节有疾者量力而行",
            "benefits": "大舞是历史最悠久的导引功法之一，以舞宣导，可疏通经络、调和气血、舒缓情志。",
        },
    },
    {
        "id": "hp-yigugong",
        "title": "缩骨功",
        "summary": "又称易骨功，内家秘传，骨节开合、筋骨变换的功法。",
        "category": "内家功法",
        "properties": {
            "pinyin": "suo gu gong",
            "origin": "内家拳法秘传，各派均有传承",
            "founder": "无单一创始人",
            "difficulty": "高级",
            "practice_type": "动静结合",
            "duration_minutes": "30-60分钟",
            "best_time": "清晨",
            "core_essence": "骨节开合，筋骨变换，通过特定功法锻炼筋骨柔韧性。",
            "key_points": ["骨节开合", "筋骨柔韧", "呼吸配合", "意守骨节"],
            "breathing": "腹式呼吸，配合骨节开合",
            "mental_focus": "意守骨节，引导开合",
            "steps": [
                {"name": "拔骨", "points": "拔伸各关节，增加间隙"},
                {"name": "缩骨", "points": "收缩骨节，锻炼筋膜"},
                {"name": "易筋", "points": "变换筋骨柔韧性"},
            ],
            "indications": ["强健筋骨", "增加柔韧", "疏通经脉"],
            "cautions": "需明师指点；切忌蛮力；循序渐进",
            "benefits": "缩骨功通过骨节开合锻炼筋骨柔韧性，可强健筋骨、疏通经脉，是内家拳法的高级功法。",
        },
    },
    {
        "id": "hp-tongbeiquan",
        "title": "通背拳",
        "summary": "内家拳法，通背通达、以背催臂，兼具武术与养生价值。",
        "category": "内家拳法",
        "properties": {
            "pinyin": "tong bei quan",
            "origin": "相传始于战国白猿，明清时期流传，祁家通背最为著名",
            "founder": "白猿（传说），祁信（祁家通背）",
            "difficulty": "进阶",
            "practice_type": "动静结合",
            "duration_minutes": "20-40分钟",
            "best_time": "清晨或傍晚",
            "core_essence": "通背通达，以背催臂，探臂拔长，发力通达。",
            "key_points": ["以背催臂", "探臂拔长", "松肩活背", "发力通达"],
            "breathing": "腹式呼吸，配合发力，气沉丹田",
            "mental_focus": "意守丹田，以意领气，以背催臂",
            "steps": [
                {"name": "活背", "points": "活动背脊，松肩活背"},
                {"name": "探臂", "points": "探臂拔长，以背催臂"},
                {"name": "发力", "points": "力由脊发，通达四梢"},
            ],
            "indications": ["强身健体", "灵活肩背", "疏通经脉", "增强体力"],
            "cautions": "探臂动作循序渐进，防止拉伤；肩背有伤者量力而行",
            "benefits": "通背拳通过以背催臂、探臂拔长的动作，灵活肩背、疏通经脉，兼具武术技击与养生价值。",
        },
    },
]

# ===========================================================================
# 10 SCHOOLS / LINEAGES (entity_type="practice_school")
# ===========================================================================

SCHOOLS: list[dict] = [
    {
        "id": "ps-wudang",
        "title": "武当派",
        "summary": "道教内家拳法代表门派，以柔克刚、以内养外。",
        "category": "道门",
        "properties": {
            "pinyin": "wu dang pai",
            "founder": "张三丰（传说）",
            "era": "元末明初",
            "location": "湖北武当山",
            "characteristics": "以柔克刚，以静制动，后发制人，内外兼修",
            "core_theory": "太极阴阳、五行八卦之理融入拳法，内练一口气，外练筋骨皮",
            "representative_practices": ["太极拳", "武当剑", "太乙五行拳"],
        },
    },
    {
        "id": "ps-shaolin",
        "title": "少林派",
        "summary": "佛教武术代表门派，刚健有力，外家拳法之宗。",
        "category": "佛门",
        "properties": {
            "pinyin": "shao lin pai",
            "founder": "达摩祖师（传说）",
            "era": "南北朝",
            "location": "河南嵩山少林寺",
            "characteristics": "刚健有力，刚柔并济，禅武合一",
            "core_theory": "禅武合一，以武修禅，外练筋骨，内修禅心",
            "representative_practices": ["易筋经", "少林拳", "少林八段锦"],
        },
    },
    {
        "id": "ps-quanzhen",
        "title": "全真道·龙门派",
        "summary": "道教内丹修炼代表门派，主张性命双修。",
        "category": "道门",
        "properties": {
            "pinyin": "quan zhen dao long men pai",
            "founder": "王重阳（创教），丘处机（创龙门派）",
            "era": "金元时期",
            "location": "陕西重阳宫 / 北京白云观",
            "characteristics": "性命双修，先性后命，清静无为，内丹修炼",
            "core_theory": "三教合一（儒释道），内丹修炼，炼精化气、炼气化神、炼神还虚",
            "representative_practices": ["金刚功", "长寿功", "内丹功"],
        },
    },
    {
        "id": "ps-emei",
        "title": "峨眉派",
        "summary": "四川峨眉山武术门派，动静结合、刚柔并济。",
        "category": "武术门派",
        "properties": {
            "pinyin": "e mei pai",
            "founder": "司徒玄空（传说），后经各代发展",
            "era": "春秋战国（起源传说）",
            "location": "四川峨眉山",
            "characteristics": "动静结合，刚柔并济，融合佛道两家",
            "core_theory": "动静相兼，内外合一，融合释道武医",
            "representative_practices": ["峨眉十二桩", "峨眉剑"],
        },
    },
    {
        "id": "ps-zhengyi",
        "title": "正一道",
        "summary": "道教符箓派代表，符箓与养生并重。",
        "category": "道门",
        "properties": {
            "pinyin": "zheng yi dao",
            "founder": "张道陵（张天师）",
            "era": "东汉",
            "location": "江西龙虎山",
            "characteristics": "符箓与养生并重，斋醮科仪，可以婚娶",
            "core_theory": "以符水治病，养生延年，天人感应",
            "representative_practices": ["正一养生功", "符箓科仪"],
        },
    },
    {
        "id": "ps-taiji-schools",
        "title": "太极拳流派",
        "summary": "陈、杨、吴、武、孙五大流派太极拳的统称。",
        "category": "武术门派",
        "properties": {
            "pinyin": "tai ji quan liu pai",
            "founder": "陈王廷（陈式），杨露禅（杨式），吴鉴泉（吴式），武禹襄（武式），孙禄堂（孙式）",
            "era": "明末清初至今",
            "location": "河南温县陈家沟（发源地）",
            "characteristics": "五式各有特色：陈式刚柔并济、杨式舒展大方、吴式紧凑细腻、武式紧凑灵活、孙式步活身灵",
            "core_theory": "以太极阴阳之理为指导，以柔克刚，以静制动",
            "representative_practices": ["陈式太极拳", "杨式太极拳", "吴式太极拳", "武式太极拳", "孙式太极拳"],
        },
    },
    {
        "id": "ps-yijia-daoyin",
        "title": "医家导引",
        "summary": "历代医家创编传承的养生导引功法，以养生治病为目的。",
        "category": "医家",
        "properties": {
            "pinyin": "yi jia dao yin",
            "founder": "华佗、孙思邈、陶弘景等历代医家",
            "era": "东汉至唐宋",
            "location": "无固定地点（历代医家传承）",
            "characteristics": "以养生治病为目的，结合医学理论，简便易学",
            "core_theory": "以中医经络学说为指导，导引行气，调理脏腑，防治疾病",
            "representative_practices": ["五禽戏", "六字诀", "医家八段锦"],
        },
    },
    {
        "id": "ps-minjian",
        "title": "民间功法",
        "summary": "民间广泛流传的养生功法，通俗易懂、简便易学。",
        "category": "民间",
        "properties": {
            "pinyin": "min jian gong fa",
            "founder": "无单一创始人（民间集体智慧）",
            "era": "历代",
            "location": "全国各地",
            "characteristics": "通俗易懂，简便易学，流传广泛，老少皆宜",
            "core_theory": "以实用养生为目的，动作简单，效果显著",
            "representative_practices": ["八段锦", "十二段锦", "回春功"],
        },
    },
    {
        "id": "ps-chanxiu",
        "title": "佛家禅修",
        "summary": "佛教禅宗静坐修行方法，以禅定为核心。",
        "category": "佛门",
        "properties": {
            "pinyin": "fo jia chan xiu",
            "founder": "达摩祖师（中土禅宗初祖）",
            "era": "南北朝（中土禅宗创立）",
            "location": "河南少林寺（初祖） / 各禅宗寺院",
            "characteristics": "以禅定为核心，明心见性，见性成佛",
            "core_theory": "戒定慧三学，由定生慧，明心见性",
            "representative_practices": ["禅坐", "数息观", "内观"],
        },
    },
    {
        "id": "ps-neidan",
        "title": "道家内丹派",
        "summary": "道教内丹修炼流派，以精气神三宝修炼为核心。",
        "category": "道门",
        "properties": {
            "pinyin": "dao jia nei dan pai",
            "founder": "魏伯阳、张伯端（南宗）、王重阳（北宗）",
            "era": "东汉至宋元",
            "location": "无固定地点（各派传承）",
            "characteristics": "以精气神三宝为药物，以丹田为炉鼎，以意念为火候，修炼内丹",
            "core_theory": "炼精化气、炼气化神、炼神还虚、炼虚合道，四步功法",
            "representative_practices": ["内丹功", "小周天", "大周天"],
        },
    },
]

# ===========================================================================
# 15 PRACTICE VARIANTS (entity_type="health_practice")
# ===========================================================================

VARIANTS: list[dict] = [
    {
        "id": "hp-taiji-chen",
        "title": "陈式太极拳",
        "summary": "太极拳发源流派，刚柔并济、快慢相间，含缠丝劲。",
        "category": "内家拳法",
        "parent": "hp-taiji",
        "school": "ps-taiji-schools",
        "properties": {
            "pinyin": "chen shi tai ji quan",
            "origin": "明末清初河南温县陈家沟，陈王廷创编",
            "founder": "陈王廷",
            "difficulty": "高级",
            "practice_type": "动静结合",
            "duration_minutes": "20-40分钟",
            "core_essence": "刚柔并济，快慢相间，缠丝劲为核心，发劲刚猛。",
            "key_points": ["缠丝劲", "刚柔并济", "快慢相间", "发劲完整", "螺旋缠绕"],
            "characteristics": "动作中有发劲、跳跃、震脚等刚猛动作，老架、新架之分",
            "representative_form": "老架一路、老架二路（炮捶）",
        },
    },
    {
        "id": "hp-taiji-yang",
        "title": "杨式太极拳",
        "summary": "流传最广的太极拳流派，舒展大方、柔和缓慢。",
        "category": "内家拳法",
        "parent": "hp-taiji",
        "school": "ps-taiji-schools",
        "properties": {
            "pinyin": "yang shi tai ji quan",
            "origin": "杨露禅由陈式太极拳演化而成",
            "founder": "杨露禅",
            "difficulty": "入门",
            "practice_type": "动静结合",
            "duration_minutes": "20-40分钟",
            "core_essence": "舒展大方，柔和缓慢，老少皆宜，流传最广。",
            "key_points": ["舒展大方", "柔和缓慢", "虚实分明", "连绵不断", "中正安舒"],
            "characteristics": "去除发劲动作，动作舒展柔和，是最普及的太极拳流派",
            "representative_form": "85式、103式、24式简化太极拳",
        },
    },
    {
        "id": "hp-taiji-wu",
        "title": "吴式太极拳",
        "summary": "紧凑细腻、斜中寓正的太极拳流派。",
        "category": "内家拳法",
        "parent": "hp-taiji",
        "school": "ps-taiji-schools",
        "properties": {
            "pinyin": "wu shi tai ji quan",
            "origin": "吴鉴泉由杨式太极拳演化而成",
            "founder": "吴鉴泉",
            "difficulty": "进阶",
            "practice_type": "动静结合",
            "duration_minutes": "20-40分钟",
            "core_essence": "紧凑细腻，斜中寓正，柔化为主。",
            "key_points": ["紧凑细腻", "斜中寓正", "柔化为主", "川字步型", "立身中正"],
            "characteristics": "架式紧凑，身形前倾（斜中寓正），以柔化见长",
            "representative_form": "吴式83式",
        },
    },
    {
        "id": "hp-taiji-wu-style",
        "title": "武式太极拳",
        "summary": "紧凑灵活、虚实分明的太极拳流派。",
        "category": "内家拳法",
        "parent": "hp-taiji",
        "school": "ps-taiji-schools",
        "properties": {
            "pinyin": "wu shi tai ji quan (wu yu xiang)",
            "origin": "武禹襄由陈式和赵堡太极拳演化而成",
            "founder": "武禹襄",
            "difficulty": "进阶",
            "practice_type": "动静结合",
            "duration_minutes": "20-40分钟",
            "core_essence": "紧凑灵活，虚实分明，注重内劲。",
            "key_points": ["紧凑灵活", "虚实分明", "注重内劲", "步法轻灵", "架式小巧"],
            "characteristics": "架式紧凑小巧，动作幅度小，注重内劲修炼",
            "representative_form": "武式108式",
        },
    },
    {
        "id": "hp-taiji-sun",
        "title": "孙式太极拳",
        "summary": "步活身灵、融形意八卦于一体的太极拳流派。",
        "category": "内家拳法",
        "parent": "hp-taiji",
        "school": "ps-taiji-schools",
        "properties": {
            "pinyin": "sun shi tai ji quan",
            "origin": "孙禄堂融合形意拳、八卦掌、太极拳而成",
            "founder": "孙禄堂",
            "difficulty": "进阶",
            "practice_type": "动静结合",
            "duration_minutes": "20-40分钟",
            "core_essence": "步活身灵，融形意八卦于一体，进退相随。",
            "key_points": ["步活身灵", "进退相随", "融三派于一体", "架高步活", "转换灵活"],
            "characteristics": "融合形意拳之整劲、八卦掌之步法、太极拳之柔化",
            "representative_form": "孙式97式",
        },
    },
    {
        "id": "hp-baduanjin-shaolin",
        "title": "少林八段锦",
        "summary": "少林寺传承的八段锦，刚健有力，禅武合一。",
        "category": "导引功法",
        "parent": "hp-baduanjin",
        "school": "ps-shaolin",
        "properties": {
            "pinyin": "shao lin ba duan jin",
            "origin": "少林寺传承的八段锦版本",
            "founder": "少林寺历代僧人",
            "difficulty": "进阶",
            "practice_type": "动功",
            "core_essence": "刚健有力，禅武合一，配合少林拳法练习。",
            "key_points": ["刚健有力", "禅武合一", "配合拳法", "发力完整"],
            "characteristics": "动作比一般八段锦更为刚健有力，强调发力",
        },
    },
    {
        "id": "hp-baduanjin-daoist",
        "title": "道家八段锦",
        "summary": "道家传承的八段锦，配合内丹修炼，柔和大方。",
        "category": "导引功法",
        "parent": "hp-baduanjin",
        "school": "ps-quanzhen",
        "properties": {
            "pinyin": "dao jia ba duan jin",
            "origin": "道教全真龙门派传承",
            "founder": "道家历代传承",
            "difficulty": "进阶",
            "practice_type": "动功",
            "core_essence": "柔和大方，配合内丹修炼，内外兼修。",
            "key_points": ["柔和大方", "内外兼修", "配合内丹", "意气相随"],
            "characteristics": "动作柔和，注重内气运行，常作为内丹修炼的基础功法",
        },
    },
    {
        "id": "hp-baduanjin-medical",
        "title": "医家八段锦",
        "summary": "医家整理传承的八段锦，侧重防病治病、调理脏腑。",
        "category": "导引功法",
        "parent": "hp-baduanjin",
        "school": "ps-yijia-daoyin",
        "properties": {
            "pinyin": "yi jia ba duan jin",
            "origin": "历代医家整理传承",
            "founder": "历代医家",
            "difficulty": "入门",
            "practice_type": "动功",
            "core_essence": "侧重防病治病，每式针对脏腑，医学指导性强。",
            "key_points": ["防病治病", "针对脏腑", "医学指导", "简便易学"],
            "characteristics": "以中医经络脏腑理论为指导，侧重防病治病，是流传最广的版本",
        },
    },
    {
        "id": "hp-baduanjin-wen",
        "title": "文八段锦",
        "summary": "坐式八段锦，又称文八段，适合体弱者练习。",
        "category": "导引功法",
        "parent": "hp-baduanjin",
        "school": "ps-minjian",
        "properties": {
            "pinyin": "wen ba duan jin",
            "origin": "民间流传的坐式八段锦",
            "founder": "无单一创始人",
            "difficulty": "入门",
            "practice_type": "动静结合",
            "core_essence": "坐式练习，适合体弱者，动作柔和。",
            "key_points": ["坐式练习", "适合体弱", "动作柔和", "简便易学"],
            "characteristics": "以坐式为主，动作柔和，适合体弱者或老年人练习",
        },
    },
    {
        "id": "hp-baduanjin-wu",
        "title": "武八段锦",
        "summary": "站式八段锦，又称武八段，动作舒展、刚健有力。",
        "category": "导引功法",
        "parent": "hp-baduanjin",
        "school": "ps-minjian",
        "properties": {
            "pinyin": "wu ba duan jin",
            "origin": "民间流传的站式八段锦",
            "founder": "无单一创始人",
            "difficulty": "入门",
            "practice_type": "动功",
            "core_essence": "站式练习，动作舒展，刚健有力。",
            "key_points": ["站式练习", "动作舒展", "刚健有力", "马步稳固"],
            "characteristics": "以站式为主，包含马步等下肢动作，是流传最广的版本",
        },
    },
    {
        "id": "hp-zhanzhuang-hunyuan",
        "title": "浑圆桩",
        "summary": "站桩基础桩法，两手环抱如浑圆一气，培本固元。",
        "category": "静功",
        "parent": "hp-zhanzhuang",
        "school": "ps-minjian",
        "properties": {
            "pinyin": "hun yuan zhuang",
            "origin": "各武术养生门派共有桩法",
            "founder": "无单一创始人",
            "difficulty": "入门",
            "practice_type": "静功",
            "core_essence": "两手环抱胸前，如抱一浑圆气球，松静自然。",
            "key_points": ["两臂环抱", "松静自然", "意守丹田", "似抱非抱", "虚灵顶劲"],
            "characteristics": "两手环抱胸前，十指相对，如抱气球，是站桩最基础的桩法",
            "posture": "两脚与肩同宽，屈膝松胯，两臂环抱胸前，十指相对相距约一尺",
        },
    },
    {
        "id": "hp-zhanzhuang-santi",
        "title": "三体式",
        "summary": "形意拳基础桩法，又称三才桩，技击与养生兼备。",
        "category": "静功",
        "parent": "hp-zhanzhuang",
        "school": "ps-minjian",
        "properties": {
            "pinyin": "san ti shi",
            "origin": "形意拳基础桩法",
            "founder": "形意拳历代传承",
            "difficulty": "进阶",
            "practice_type": "静功",
            "core_essence": "前三后七重心分配，手脚齐到，六合合一。",
            "key_points": ["前三后七", "手脚齐到", "六合合一", "三尖相照", "沉肩坠肘"],
            "characteristics": "前三后七重心分配，一手前伸一手护裆，是形意拳万法之本",
            "posture": "前三后七步型，前手前伸与肩同高，后手置于腹部",
        },
    },
    {
        "id": "hp-dazuo-shuxi",
        "title": "数息法",
        "summary": "打坐入门方法，通过默数呼吸使心念专一。",
        "category": "静功",
        "parent": "hp-dazuo",
        "school": "ps-chanxiu",
        "properties": {
            "pinyin": "shu xi fa",
            "origin": "佛教数息观（安那般那念）",
            "founder": "佛教历代传承",
            "difficulty": "入门",
            "practice_type": "静功",
            "core_essence": "默数呼吸（1-10），心息相依，使心念专一。",
            "key_points": ["默数呼吸", "1至10循环", "心息相依", "杂念即重来", "专注一境"],
            "characteristics": "打坐最基础的方法，通过数息收摄心念，适合初学者",
            "method": "从1数到10，再从1开始，若杂念生起则重新从1数起",
        },
    },
    {
        "id": "hp-dazuo-guanxi",
        "title": "观息法",
        "summary": "打坐进阶方法，观察呼吸出入而不干预，培养觉知。",
        "category": "静功",
        "parent": "hp-dazuo",
        "school": "ps-chanxiu",
        "properties": {
            "pinyin": "guan xi fa",
            "origin": "佛教内观（毗钵舍那）",
            "founder": "佛教历代传承",
            "difficulty": "进阶",
            "practice_type": "静功",
            "core_essence": "观察呼吸出入而不干预，培养觉知，如实观照。",
            "key_points": ["如实观照", "不干预呼吸", "培养觉知", "了了分明", "平等心"],
            "characteristics": "数息法之后的进阶方法，从专注呼吸转向如实观察身心",
            "method": "注意力集中于鼻端或腹部，观察呼吸的自然出入而不加干预",
        },
    },
    {
        "id": "hp-neidan-xiao",
        "title": "小周天功",
        "summary": "内丹初关，精气沿任督二脉循环，又称河车搬运。",
        "category": "内功",
        "parent": "hp-qigong",
        "school": "ps-neidan",
        "properties": {
            "pinyin": "xiao zhou tian gong",
            "origin": "道家内丹术基础功法",
            "founder": "历代丹家",
            "difficulty": "高级",
            "practice_type": "静功",
            "core_essence": "炼精化气，内气沿任督二脉循环运转，即河车搬运。",
            "key_points": ["炼精化气", "任督循环", "火候适当", "意气相随", "气沉丹田"],
            "characteristics": "内丹初关功法，内气从下丹田经会阴、尾闾、命门、百会、上丹田、中丹田回到下丹田",
            "route": "下丹田→会阴→尾闾→命门→夹脊→玉枕→百会→印堂→鹊桥→中丹田→下丹田",
        },
    },
]

# ===========================================================================
# RELATIONSHIPS
# (source, target, type, properties, weight)
# ===========================================================================

RELATIONSHIPS: list[tuple[str, str, str, dict, float]] = [
    # --- derived_from: variant -> origin practice ---
    ("hp-taiji-chen", "hp-taiji", "derived_from", {"关系": "流派源自"}, 1.0),
    ("hp-taiji-yang", "hp-taiji", "derived_from", {"关系": "流派源自"}, 1.0),
    ("hp-taiji-wu", "hp-taiji", "derived_from", {"关系": "流派源自"}, 1.0),
    ("hp-taiji-wu-style", "hp-taiji", "derived_from", {"关系": "流派源自"}, 1.0),
    ("hp-taiji-sun", "hp-taiji", "derived_from", {"关系": "流派源自"}, 1.0),
    ("hp-baduanjin-shaolin", "hp-baduanjin", "derived_from", {"门派": "少林"}, 1.0),
    ("hp-baduanjin-daoist", "hp-baduanjin", "derived_from", {"门派": "全真道"}, 1.0),
    ("hp-baduanjin-medical", "hp-baduanjin", "derived_from", {"门派": "医家"}, 1.0),
    ("hp-baduanjin-wen", "hp-baduanjin", "derived_from", {"形式": "坐式"}, 1.0),
    ("hp-baduanjin-wu", "hp-baduanjin", "derived_from", {"形式": "站式"}, 1.0),
    ("hp-zhanzhuang-hunyuan", "hp-zhanzhuang", "derived_from", {"桩法": "基础"}, 1.0),
    ("hp-zhanzhuang-santi", "hp-zhanzhuang", "derived_from", {"桩法": "形意拳"}, 1.0),
    ("hp-dazuo-shuxi", "hp-dazuo", "derived_from", {"阶次": "入门"}, 1.0),
    ("hp-dazuo-guanxi", "hp-dazuo", "derived_from", {"阶次": "进阶"}, 1.0),
    ("hp-neidan-xiao", "hp-qigong", "derived_from", {"阶次": "初关"}, 1.0),

    # --- belongs_to_school: practice -> school ---
    ("hp-taiji", "ps-wudang", "belongs_to_school", {"关系": "内家名拳"}, 1.0),
    ("hp-taiji", "ps-taiji-schools", "belongs_to_school", {"关系": "五大流派统称"}, 0.9),
    ("hp-jingang", "ps-quanzhen", "belongs_to_school", {"关系": "龙门秘传"}, 1.0),
    ("hp-changshou", "ps-quanzhen", "belongs_to_school", {"关系": "龙门秘传"}, 1.0),
    ("hp-yijinjing", "ps-shaolin", "belongs_to_school", {"关系": "少林名功"}, 1.0),
    ("hp-wuqinxi", "ps-yijia-daoyin", "belongs_to_school", {"关系": "华佗创编"}, 1.0),
    ("hp-liuzijue", "ps-yijia-daoyin", "belongs_to_school", {"关系": "医家吐纳"}, 1.0),
    ("hp-qigong", "ps-neidan", "belongs_to_school", {"关系": "内丹核心"}, 1.0),
    ("hp-dazuo", "ps-chanxiu", "belongs_to_school", {"关系": "禅修基础"}, 0.9),
    ("hp-tongbeiquan", "ps-wudang", "belongs_to_school", {"关系": "内家拳法"}, 0.8),
    # variants -> schools
    ("hp-taiji-chen", "ps-taiji-schools", "belongs_to_school", {"流派": "陈式"}, 1.0),
    ("hp-taiji-yang", "ps-taiji-schools", "belongs_to_school", {"流派": "杨式"}, 1.0),
    ("hp-taiji-wu", "ps-taiji-schools", "belongs_to_school", {"流派": "吴式"}, 1.0),
    ("hp-taiji-wu-style", "ps-taiji-schools", "belongs_to_school", {"流派": "武式"}, 1.0),
    ("hp-taiji-sun", "ps-taiji-schools", "belongs_to_school", {"流派": "孙式"}, 1.0),
    ("hp-baduanjin-shaolin", "ps-shaolin", "belongs_to_school", {"门派": "少林"}, 1.0),
    ("hp-baduanjin-daoist", "ps-quanzhen", "belongs_to_school", {"门派": "全真道"}, 1.0),
    ("hp-baduanjin-medical", "ps-yijia-daoyin", "belongs_to_school", {"门派": "医家"}, 1.0),
    ("hp-baduanjin-wen", "ps-minjian", "belongs_to_school", {"门派": "民间"}, 1.0),
    ("hp-baduanjin-wu", "ps-minjian", "belongs_to_school", {"门派": "民间"}, 1.0),
    ("hp-zhanzhuang-hunyuan", "ps-minjian", "belongs_to_school", {"门派": "民间"}, 1.0),
    ("hp-zhanzhuang-santi", "ps-minjian", "belongs_to_school", {"门派": "形意拳"}, 1.0),
    ("hp-dazuo-shuxi", "ps-chanxiu", "belongs_to_school", {"门派": "禅修"}, 1.0),
    ("hp-dazuo-guanxi", "ps-chanxiu", "belongs_to_school", {"门派": "禅修"}, 1.0),
    ("hp-neidan-xiao", "ps-neidan", "belongs_to_school", {"门派": "内丹派"}, 1.0),
    ("hp-baduanjin", "ps-minjian", "belongs_to_school", {"关系": "民间流传最广"}, 1.0),
    ("hp-shierduanjin", "ps-minjian", "belongs_to_school", {"关系": "民间流传"}, 0.9),
    ("hp-mawangdui", "ps-yijia-daoyin", "belongs_to_school", {"关系": "古代导引复原"}, 0.8),
    ("hp-dawu", "ps-yijia-daoyin", "belongs_to_school", {"关系": "上古导引"}, 0.8),
    ("hp-yigugong", "ps-wudang", "belongs_to_school", {"关系": "内家秘传"}, 0.7),
    ("hp-zhanzhuang", "ps-minjian", "belongs_to_school", {"关系": "各派共有"}, 0.9),

    # --- complementary_to: mutually beneficial practices ---
    ("hp-jingang", "hp-changshou", "complementary_to", {"关系": "一外一内，相辅相成"}, 1.0),
    ("hp-changshou", "hp-jingang", "complementary_to", {"关系": "一内一外，相辅相成"}, 1.0),
    ("hp-taiji", "hp-zhanzhuang", "complementary_to", {"关系": "动静结合，互为补充"}, 0.8),
    ("hp-zhanzhuang", "hp-taiji", "complementary_to", {"关系": "动静结合，互为补充"}, 0.8),
    ("hp-baduanjin", "hp-liuzijue", "complementary_to", {"关系": "动功与吐纳配合"}, 0.7),
    ("hp-dazuo", "hp-zhanzhuang", "complementary_to", {"关系": "一坐一站，相辅相成"}, 0.7),
]


# ===========================================================================
# Seed functions
# ===========================================================================


def _practice_keywords(p: dict) -> str:
    """Build keywords JSON from practice properties."""
    props = p["properties"]
    kw = [p["title"]]
    if props.get("founder"):
        kw.append(props["founder"])
    if props.get("practice_type"):
        kw.append(props["practice_type"])
    if props.get("pinyin"):
        kw.append(props["pinyin"])
    # dedupe preserving order
    seen: set[str] = set()
    out = []
    for k in kw:
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return json.dumps(out, ensure_ascii=False)


def _practice_tags(p: dict) -> str:
    tags = [p["category"]]
    if p["properties"].get("difficulty"):
        tags.append(p["properties"]["difficulty"])
    if p["properties"].get("practice_type"):
        tags.append(p["properties"]["practice_type"])
    return json.dumps(tags, ensure_ascii=False)


def _content_preview(p: dict) -> str:
    props = p["properties"]
    parts = []
    if props.get("core_essence"):
        parts.append(props["core_essence"])
    if props.get("indications"):
        parts.append("功效：" + "、".join(props["indications"][:4]))
    elif props.get("benefits"):
        parts.append(props["benefits"][:60])
    return "；".join(parts)[:200]


async def _ensure_tables(db: aiosqlite.Connection) -> None:
    """Create tables if not exist (standalone safety net)."""
    cur = await db.cursor()
    for stmt in _DDL:
        await cur.execute(stmt)
    await db.commit()


async def seed_core_practices(db: aiosqlite.Connection) -> int:
    now = _now()
    count = 0
    for p in CORE_PRACTICES:
        props = p["properties"]
        await db.execute(
            _INSERT_ENTITY,
            (
                p["id"],
                "health_practice",
                "health_practice",
                p["id"],
                p["title"],
                p["summary"],
                _practice_keywords(p),
                _practice_tags(p),
                p["category"],
                _content_preview(p),
                json.dumps(props, ensure_ascii=False),
                "system",
                "active",
                now,
                now,
            ),
        )
        count += 1
    return count


async def seed_schools(db: aiosqlite.Connection) -> int:
    now = _now()
    count = 0
    for s in SCHOOLS:
        props = s["properties"]
        tags = [s["category"]]
        kw = [s["title"], props.get("founder", ""), props.get("pinyin", "")]
        await db.execute(
            _INSERT_ENTITY,
            (
                s["id"],
                "practice_school",
                "practice_school",
                s["id"],
                s["title"],
                s["summary"],
                json.dumps([k for k in kw if k], ensure_ascii=False),
                json.dumps(tags, ensure_ascii=False),
                s["category"],
                props.get("characteristics", "")[:200],
                json.dumps(props, ensure_ascii=False),
                "system",
                "active",
                now,
                now,
            ),
        )
        count += 1
    return count


async def seed_variants(db: aiosqlite.Connection) -> int:
    now = _now()
    count = 0
    for v in VARIANTS:
        props = v["properties"]
        # variants reference their parent's category
        tags = [v["category"], props.get("difficulty", ""), props.get("practice_type", "")]
        kw = [v["title"], props.get("founder", ""), props.get("pinyin", "")]
        await db.execute(
            _INSERT_ENTITY,
            (
                v["id"],
                "health_practice",
                "health_practice",
                v["id"],
                v["title"],
                v["summary"],
                json.dumps([k for k in kw if k], ensure_ascii=False),
                json.dumps([t for t in tags if t], ensure_ascii=False),
                v["category"],
                props.get("core_essence", "")[:200],
                json.dumps(props, ensure_ascii=False),
                "system",
                "active",
                now,
                now,
            ),
        )
        count += 1
    return count


async def seed_relationships(db: aiosqlite.Connection) -> int:
    now = _now()
    count = 0
    for src, tgt, rel_type, props, weight in RELATIONSHIPS:
        rel_id = f"rel:{rel_type}:{src}->{tgt}"
        await db.execute(
            _INSERT_REL,
            (
                rel_id,
                src,
                tgt,
                rel_type,
                json.dumps(props, ensure_ascii=False),
                weight,
                now,
            ),
        )
        count += 1
    return count


async def _count(db: aiosqlite.Connection, sql: str) -> int:
    cur = await db.execute(sql)
    row = await cur.fetchone()
    return row[0] if row else 0


async def seed(db_path: str) -> None:
    """Run the full seed pipeline and print summary."""
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await _ensure_tables(db)

        before_practice = await _count(
            db,
            "SELECT COUNT(*) FROM knowledge_entities WHERE entity_type = 'health_practice'",
        )
        before_school = await _count(
            db,
            "SELECT COUNT(*) FROM knowledge_entities WHERE entity_type = 'practice_school'",
        )
        before_rel = await _count(
            db,
            "SELECT COUNT(*) FROM entity_relationships "
            "WHERE relationship_type IN ('derived_from','belongs_to_school','complementary_to')",
        )

        core_n = await seed_core_practices(db)
        school_n = await seed_schools(db)
        variant_n = await seed_variants(db)
        rel_n = await seed_relationships(db)
        await db.commit()

        total_practice = await _count(
            db,
            "SELECT COUNT(*) FROM knowledge_entities WHERE entity_type = 'health_practice'",
        )
        total_school = await _count(
            db,
            "SELECT COUNT(*) FROM knowledge_entities WHERE entity_type = 'practice_school'",
        )
        total_entities = await _count(
            db, "SELECT COUNT(*) FROM knowledge_entities"
        )
        total_rel = await _count(
            db,
            "SELECT COUNT(*) FROM entity_relationships "
            "WHERE relationship_type IN ('derived_from','belongs_to_school','complementary_to')",
        )

        derived_n = await _count(
            db, "SELECT COUNT(*) FROM entity_relationships WHERE relationship_type='derived_from'"
        )
        belongs_n = await _count(
            db, "SELECT COUNT(*) FROM entity_relationships WHERE relationship_type='belongs_to_school'"
        )
        comple_n = await _count(
            db, "SELECT COUNT(*) FROM entity_relationships WHERE relationship_type='complementary_to'"
        )

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print("=" * 60)
    print("  养生功法种子数据完成")
    print("=" * 60)
    print(f"  本次插入:")
    print(f"    核心功法 (health_practice): {core_n}")
    print(f"    门派流派 (practice_school): {school_n}")
    print(f"    功法变体 (health_practice): {variant_n}")
    print(f"    实体关系:                    {rel_n}")
    print(f"  ---------------------------")
    print(f"  数据库现有:")
    print(f"    功法实体 (health_practice): {total_practice} (原有 {before_practice})")
    print(f"    门派实体 (practice_school): {total_school} (原有 {before_school})")
    print(f"    知识实体总数:               {total_entities}")
    print(f"  ---------------------------")
    print(f"  关系统计:")
    print(f"    derived_from (源自):        {derived_n}")
    print(f"    belongs_to_school (属门派): {belongs_n}")
    print(f"    complementary_to (相辅):    {comple_n}")
    print(f"    合计:                        {total_rel} (原有 {before_rel})")
    print()

    assert total_practice >= 30, f"Expected >=30 health_practice, got {total_practice}"
    assert total_school >= 10, f"Expected >=10 practice_school, got {total_school}"
    print(
        f"  OK: {total_practice} 功法 + {total_school} 门派 + {total_rel} 关系 seeded successfully."
    )


if __name__ == "__main__":
    db_path = os.environ.get("HOMEDOCTOR_DATABASE_URL", "data/homedoctor.db")
    if len(sys.argv) > 1:
        if sys.argv[1] in ("--db", "-d"):
            db_path = sys.argv[2]
        else:
            db_path = sys.argv[1]
    asyncio.run(seed(db_path))
