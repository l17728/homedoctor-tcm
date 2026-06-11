#!/usr/bin/env python3
"""
Seed 80 traditional Chinese medicine formulas into SQLite database.

Usage:
    python backend/scripts/seed_formulas.py [--db PATH]

Default DB path: data/homedoctor.db (relative to project root /homedoctor)

Formulas table schema:
    id, name, source, category, composition, efficacy, indications,
    modifications, modifications_structured, derived_from_id, properties

IDs start from formula-003 (formula-001=四君子汤, formula-002=四物汤 already exist).
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys

# ---------------------------------------------------------------------------
# 80 formulas — all data from 《方剂学》 textbook (10th edition, 人民卫生出版社)
# ---------------------------------------------------------------------------

FORMULAS: list[dict] = [
    # ===================================================================
    # 解表剂 (8)
    # ===================================================================
    {
        "id": "formula-003",
        "name": "麻黄汤",
        "source": "《伤寒论》",
        "category": "解表剂",
        "composition": [
            {"name": "麻黄", "dose": "9g", "role": "君"},
            {"name": "桂枝", "dose": "6g", "role": "臣"},
            {"name": "杏仁", "dose": "6g", "role": "佐"},
            {"name": "甘草", "dose": "3g", "role": "使"},
        ],
        "efficacy": "发汗解表，宣肺平喘",
        "indications": "外感风寒表实证。恶寒发热，头身疼痛，无汗而喘，舌苔薄白，脉浮紧",
    },
    {
        "id": "formula-004",
        "name": "桂枝汤",
        "source": "《伤寒论》",
        "category": "解表剂",
        "composition": [
            {"name": "桂枝", "dose": "9g", "role": "君"},
            {"name": "芍药", "dose": "9g", "role": "臣"},
            {"name": "生姜", "dose": "9g", "role": "佐"},
            {"name": "大枣", "dose": "3枚", "role": "佐"},
            {"name": "甘草", "dose": "6g", "role": "使"},
        ],
        "efficacy": "解肌发表，调和营卫",
        "indications": "外感风寒表虚证。头痛发热，汗出恶风，鼻鸣干呕，苔白不渴，脉浮缓或浮弱",
    },
    {
        "id": "formula-005",
        "name": "九味羌活汤",
        "source": "《此事难知》引张元素方",
        "category": "解表剂",
        "composition": [
            {"name": "羌活", "dose": "9g", "role": "君"},
            {"name": "防风", "dose": "9g", "role": "臣"},
            {"name": "苍术", "dose": "9g", "role": "臣"},
            {"name": "细辛", "dose": "3g", "role": "佐"},
            {"name": "川芎", "dose": "6g", "role": "佐"},
            {"name": "白芷", "dose": "6g", "role": "佐"},
            {"name": "生地黄", "dose": "6g", "role": "佐"},
            {"name": "黄芩", "dose": "6g", "role": "佐"},
            {"name": "甘草", "dose": "6g", "role": "使"},
        ],
        "efficacy": "发汗祛湿，兼清里热",
        "indications": "外感风寒湿邪，内有蕴热证。恶寒发热，肌表无汗，头痛项强，肢体酸楚疼痛，口苦微渴",
    },
    {
        "id": "formula-006",
        "name": "小青龙汤",
        "source": "《伤寒论》",
        "category": "解表剂",
        "composition": [
            {"name": "麻黄", "dose": "9g", "role": "君"},
            {"name": "桂枝", "dose": "9g", "role": "君"},
            {"name": "干姜", "dose": "9g", "role": "臣"},
            {"name": "细辛", "dose": "3g", "role": "臣"},
            {"name": "半夏", "dose": "9g", "role": "佐"},
            {"name": "五味子", "dose": "6g", "role": "佐"},
            {"name": "芍药", "dose": "9g", "role": "佐"},
            {"name": "甘草", "dose": "6g", "role": "使"},
        ],
        "efficacy": "解表散寒，温肺化饮",
        "indications": "外寒内饮证。恶寒发热，无汗，胸痞喘咳，痰多而稀，或痰喘不得平卧，舌苔白滑，脉浮",
    },
    {
        "id": "formula-007",
        "name": "止嗽散",
        "source": "《医学心悟》",
        "category": "解表剂",
        "composition": [
            {"name": "桔梗", "dose": "9g", "role": "君"},
            {"name": "荆芥", "dose": "9g", "role": "臣"},
            {"name": "紫菀", "dose": "9g", "role": "臣"},
            {"name": "百部", "dose": "9g", "role": "臣"},
            {"name": "白前", "dose": "9g", "role": "佐"},
            {"name": "陈皮", "dose": "6g", "role": "佐"},
            {"name": "甘草", "dose": "3g", "role": "使"},
        ],
        "efficacy": "宣肺疏风，止咳化痰",
        "indications": "风邪犯肺证。咳嗽咽痒，咯痰不爽，或微有恶风发热，舌苔薄白",
    },
    {
        "id": "formula-008",
        "name": "银翘散",
        "source": "《温病条辨》",
        "category": "解表剂",
        "composition": [
            {"name": "金银花", "dose": "30g", "role": "君"},
            {"name": "连翘", "dose": "30g", "role": "君"},
            {"name": "薄荷", "dose": "18g", "role": "臣"},
            {"name": "牛蒡子", "dose": "18g", "role": "臣"},
            {"name": "荆芥穗", "dose": "12g", "role": "臣"},
            {"name": "淡豆豉", "dose": "15g", "role": "臣"},
            {"name": "桔梗", "dose": "18g", "role": "佐"},
            {"name": "芦根", "dose": "30g", "role": "佐"},
            {"name": "竹叶", "dose": "12g", "role": "佐"},
            {"name": "甘草", "dose": "15g", "role": "使"},
        ],
        "efficacy": "辛凉透表，清热解毒",
        "indications": "温病初起。发热，微恶风寒，无汗或有汗不畅，头痛口渴，咳嗽咽痛，舌尖红，苔薄白或薄黄，脉浮数",
    },
    {
        "id": "formula-009",
        "name": "桑菊饮",
        "source": "《温病条辨》",
        "category": "解表剂",
        "composition": [
            {"name": "桑叶", "dose": "9g", "role": "君"},
            {"name": "菊花", "dose": "9g", "role": "君"},
            {"name": "薄荷", "dose": "6g", "role": "臣"},
            {"name": "连翘", "dose": "9g", "role": "臣"},
            {"name": "桔梗", "dose": "9g", "role": "佐"},
            {"name": "杏仁", "dose": "9g", "role": "佐"},
            {"name": "芦根", "dose": "12g", "role": "佐"},
            {"name": "甘草", "dose": "3g", "role": "使"},
        ],
        "efficacy": "疏风清热，宣肺止咳",
        "indications": "风温初起，表热轻证。咳嗽，身热不甚，口微渴，舌尖红，苔薄白，脉浮数",
    },
    {
        "id": "formula-010",
        "name": "麻杏石甘汤",
        "source": "《伤寒论》",
        "category": "解表剂",
        "composition": [
            {"name": "麻黄", "dose": "6g", "role": "君"},
            {"name": "石膏", "dose": "24g", "role": "臣"},
            {"name": "杏仁", "dose": "9g", "role": "佐"},
            {"name": "甘草", "dose": "6g", "role": "使"},
        ],
        "efficacy": "辛凉宣泄，清肺平喘",
        "indications": "外感风邪，肺热咳喘证。身热不解，咳逆气急鼻扇，口渴，有汗或无汗，舌苔薄白或黄，脉滑而数",
    },

    # ===================================================================
    # 泻下剂 (4)
    # ===================================================================
    {
        "id": "formula-011",
        "name": "大承气汤",
        "source": "《伤寒论》",
        "category": "泻下剂",
        "composition": [
            {"name": "大黄", "dose": "12g", "role": "君"},
            {"name": "芒硝", "dose": "9g", "role": "臣"},
            {"name": "厚朴", "dose": "15g", "role": "佐"},
            {"name": "枳实", "dose": "12g", "role": "佐"},
        ],
        "efficacy": "峻下热结",
        "indications": "阳明腑实证。大便不通，频转矢气，脘腹痞满，腹痛拒按，按之硬，甚或潮热谵语，手足濈然汗出，舌苔黄燥起刺或焦黑燥裂，脉沉实",
    },
    {
        "id": "formula-012",
        "name": "小承气汤",
        "source": "《伤寒论》",
        "category": "泻下剂",
        "composition": [
            {"name": "大黄", "dose": "12g", "role": "君"},
            {"name": "厚朴", "dose": "6g", "role": "臣"},
            {"name": "枳实", "dose": "9g", "role": "佐"},
        ],
        "efficacy": "轻下热结",
        "indications": "阳明腑实轻证。谵语潮热，大便秘结，胸腹痞满，舌苔老黄，脉滑而疾",
    },
    {
        "id": "formula-013",
        "name": "调胃承气汤",
        "source": "《伤寒论》",
        "category": "泻下剂",
        "composition": [
            {"name": "大黄", "dose": "12g", "role": "君"},
            {"name": "芒硝", "dose": "9g", "role": "臣"},
            {"name": "甘草", "dose": "6g", "role": "使"},
        ],
        "efficacy": "缓下热结",
        "indications": "阳明病胃肠燥热证。大便不通，口渴心烦，蒸蒸发热，或腹中胀满，舌苔正黄，脉滑数",
    },
    {
        "id": "formula-014",
        "name": "温脾汤",
        "source": "《备急千金要方》",
        "category": "泻下剂",
        "composition": [
            {"name": "大黄", "dose": "15g", "role": "君"},
            {"name": "附子", "dose": "9g", "role": "臣"},
            {"name": "干姜", "dose": "9g", "role": "臣"},
            {"name": "人参", "dose": "6g", "role": "佐"},
            {"name": "当归", "dose": "9g", "role": "佐"},
            {"name": "芒硝", "dose": "6g", "role": "佐"},
            {"name": "甘草", "dose": "6g", "role": "使"},
        ],
        "efficacy": "攻下冷积，温补脾阳",
        "indications": "阳虚寒积证。腹痛便秘，脐下绞结，绕脐不止，手足不温，苔白不渴，脉沉弦而迟",
    },

    # ===================================================================
    # 和解剂 (5)
    # ===================================================================
    {
        "id": "formula-015",
        "name": "小柴胡汤",
        "source": "《伤寒论》",
        "category": "和解剂",
        "composition": [
            {"name": "柴胡", "dose": "24g", "role": "君"},
            {"name": "黄芩", "dose": "9g", "role": "臣"},
            {"name": "人参", "dose": "9g", "role": "佐"},
            {"name": "半夏", "dose": "9g", "role": "佐"},
            {"name": "甘草", "dose": "9g", "role": "佐"},
            {"name": "生姜", "dose": "9g", "role": "佐"},
            {"name": "大枣", "dose": "4枚", "role": "佐"},
        ],
        "efficacy": "和解少阳",
        "indications": "伤寒少阳证。往来寒热，胸胁苦满，默默不欲饮食，心烦喜呕，口苦，咽干，目眩，舌苔薄白，脉弦",
    },
    {
        "id": "formula-016",
        "name": "大柴胡汤",
        "source": "《伤寒论》",
        "category": "和解剂",
        "composition": [
            {"name": "柴胡", "dose": "15g", "role": "君"},
            {"name": "黄芩", "dose": "9g", "role": "臣"},
            {"name": "芍药", "dose": "9g", "role": "臣"},
            {"name": "半夏", "dose": "9g", "role": "佐"},
            {"name": "枳实", "dose": "9g", "role": "佐"},
            {"name": "大黄", "dose": "6g", "role": "佐"},
            {"name": "生姜", "dose": "15g", "role": "佐"},
            {"name": "大枣", "dose": "4枚", "role": "佐"},
        ],
        "efficacy": "和解少阳，内泻热结",
        "indications": "少阳阳明合病。往来寒热，胸胁苦满，呕不止，郁郁微烦，心下痞硬，或心下急痛，大便不解或协热下利",
    },
    {
        "id": "formula-017",
        "name": "逍遥散",
        "source": "《太平惠民和剂局方》",
        "category": "和解剂",
        "composition": [
            {"name": "柴胡", "dose": "9g", "role": "君"},
            {"name": "当归", "dose": "9g", "role": "臣"},
            {"name": "白芍", "dose": "9g", "role": "臣"},
            {"name": "白术", "dose": "9g", "role": "佐"},
            {"name": "茯苓", "dose": "9g", "role": "佐"},
            {"name": "薄荷", "dose": "3g", "role": "佐"},
            {"name": "生姜", "dose": "3g", "role": "佐"},
            {"name": "甘草", "dose": "6g", "role": "使"},
        ],
        "efficacy": "疏肝解郁，养血健脾",
        "indications": "肝郁血虚脾弱证。两胁作痛，头痛目眩，口燥咽干，神疲食少，或往来寒热，或月经不调，乳房胀痛，脉弦而虚",
    },
    {
        "id": "formula-018",
        "name": "痛泻要方",
        "source": "《丹溪心法》",
        "category": "和解剂",
        "composition": [
            {"name": "白术", "dose": "90g", "role": "君"},
            {"name": "白芍", "dose": "60g", "role": "臣"},
            {"name": "陈皮", "dose": "45g", "role": "佐"},
            {"name": "防风", "dose": "60g", "role": "佐"},
        ],
        "efficacy": "补脾柔肝，祛湿止泻",
        "indications": "脾虚肝旺之痛泻。肠鸣腹痛，大便泄泻，泻必腹痛，舌苔薄白，脉两关不调，弦而缓",
    },
    {
        "id": "formula-019",
        "name": "半夏泻心汤",
        "source": "《伤寒论》",
        "category": "和解剂",
        "composition": [
            {"name": "半夏", "dose": "12g", "role": "君"},
            {"name": "黄芩", "dose": "9g", "role": "臣"},
            {"name": "干姜", "dose": "9g", "role": "臣"},
            {"name": "人参", "dose": "9g", "role": "佐"},
            {"name": "黄连", "dose": "3g", "role": "佐"},
            {"name": "大枣", "dose": "4枚", "role": "佐"},
            {"name": "甘草", "dose": "9g", "role": "使"},
        ],
        "efficacy": "寒热平调，消痞散结",
        "indications": "寒热互结之痞证。心下痞，但满而不痛，或呕吐，肠鸣下利，舌苔腻而微黄",
    },

    # ===================================================================
    # 清热剂 (9)
    # ===================================================================
    {
        "id": "formula-020",
        "name": "白虎汤",
        "source": "《伤寒论》",
        "category": "清热剂",
        "composition": [
            {"name": "石膏", "dose": "50g", "role": "君"},
            {"name": "知母", "dose": "18g", "role": "臣"},
            {"name": "粳米", "dose": "9g", "role": "佐"},
            {"name": "甘草", "dose": "6g", "role": "使"},
        ],
        "efficacy": "清热生津",
        "indications": "气分热盛证。壮热面赤，烦渴引饮，汗出恶热，脉洪大有力",
    },
    {
        "id": "formula-021",
        "name": "竹叶石膏汤",
        "source": "《伤寒论》",
        "category": "清热剂",
        "composition": [
            {"name": "竹叶", "dose": "6g", "role": "君"},
            {"name": "石膏", "dose": "50g", "role": "臣"},
            {"name": "人参", "dose": "6g", "role": "佐"},
            {"name": "麦冬", "dose": "20g", "role": "佐"},
            {"name": "半夏", "dose": "9g", "role": "佐"},
            {"name": "甘草", "dose": "6g", "role": "佐"},
            {"name": "粳米", "dose": "9g", "role": "使"},
        ],
        "efficacy": "清热生津，益气和胃",
        "indications": "伤寒、温病、暑病余热未清，气津两伤证。身热多汗，心胸烦闷，气逆欲呕，口干喜饮，虚烦不寐，舌红苔少，脉虚数",
    },
    {
        "id": "formula-022",
        "name": "清营汤",
        "source": "《温病条辨》",
        "category": "清热剂",
        "composition": [
            {"name": "犀角（水牛角代）", "dose": "30g", "role": "君"},
            {"name": "生地黄", "dose": "15g", "role": "臣"},
            {"name": "玄参", "dose": "9g", "role": "臣"},
            {"name": "麦冬", "dose": "9g", "role": "佐"},
            {"name": "金银花", "dose": "9g", "role": "佐"},
            {"name": "连翘", "dose": "6g", "role": "佐"},
            {"name": "黄连", "dose": "5g", "role": "佐"},
            {"name": "竹叶心", "dose": "3g", "role": "佐"},
            {"name": "丹参", "dose": "6g", "role": "佐"},
        ],
        "efficacy": "清营解毒，透热养阴",
        "indications": "热入营分证。身热夜甚，神烦少寐，时有谵语，目常开或喜闭，口渴或不渴，斑疹隐隐，舌绛而干，脉细数",
    },
    {
        "id": "formula-023",
        "name": "犀角地黄汤",
        "source": "《小品方》录自《外台秘要》",
        "category": "清热剂",
        "composition": [
            {"name": "犀角（水牛角代）", "dose": "30g", "role": "君"},
            {"name": "生地黄", "dose": "24g", "role": "臣"},
            {"name": "芍药", "dose": "12g", "role": "佐"},
            {"name": "牡丹皮", "dose": "9g", "role": "佐"},
        ],
        "efficacy": "清热解毒，凉血散瘀",
        "indications": "热入血分证。身热谵语，斑色紫黑，吐血衄血，便血尿血，舌绛起刺，脉细数；或喜忘如狂，漱水不欲咽",
    },
    {
        "id": "formula-024",
        "name": "黄连解毒汤",
        "source": "《外台秘要》引崔氏方",
        "category": "清热剂",
        "composition": [
            {"name": "黄连", "dose": "9g", "role": "君"},
            {"name": "黄芩", "dose": "6g", "role": "臣"},
            {"name": "黄柏", "dose": "6g", "role": "臣"},
            {"name": "栀子", "dose": "9g", "role": "佐"},
        ],
        "efficacy": "泻火解毒",
        "indications": "三焦火毒证。大热烦躁，口燥咽干，错语不眠，热病吐血衄血，或热甚发斑，身热下利，湿热黄疸，外科痈疽疔毒，舌红苔黄，脉数有力",
    },
    {
        "id": "formula-025",
        "name": "普济消毒饮",
        "source": "《东垣试效方》",
        "category": "清热剂",
        "composition": [
            {"name": "黄芩", "dose": "15g", "role": "君"},
            {"name": "黄连", "dose": "15g", "role": "君"},
            {"name": "牛蒡子", "dose": "3g", "role": "臣"},
            {"name": "连翘", "dose": "3g", "role": "臣"},
            {"name": "薄荷", "dose": "3g", "role": "臣"},
            {"name": "僵蚕", "dose": "2g", "role": "佐"},
            {"name": "桔梗", "dose": "3g", "role": "佐"},
            {"name": "升麻", "dose": "2g", "role": "佐"},
            {"name": "柴胡", "dose": "2g", "role": "佐"},
            {"name": "马勃", "dose": "3g", "role": "佐"},
            {"name": "板蓝根", "dose": "3g", "role": "佐"},
            {"name": "玄参", "dose": "3g", "role": "佐"},
            {"name": "陈皮", "dose": "6g", "role": "佐"},
            {"name": "甘草", "dose": "6g", "role": "使"},
        ],
        "efficacy": "清热解毒，疏风散邪",
        "indications": "大头瘟。恶寒发热，头面红肿焮痛，目不能开，咽喉不利，舌燥口渴，舌红苔白兼黄，脉浮数有力",
    },
    {
        "id": "formula-026",
        "name": "仙方活命饮",
        "source": "《校注妇人良方》",
        "category": "清热剂",
        "composition": [
            {"name": "金银花", "dose": "9g", "role": "君"},
            {"name": "陈皮", "dose": "9g", "role": "臣"},
            {"name": "当归", "dose": "3g", "role": "佐"},
            {"name": "赤芍", "dose": "3g", "role": "佐"},
            {"name": "白芷", "dose": "3g", "role": "佐"},
            {"name": "贝母", "dose": "3g", "role": "佐"},
            {"name": "防风", "dose": "3g", "role": "佐"},
            {"name": "天花粉", "dose": "3g", "role": "佐"},
            {"name": "乳香", "dose": "3g", "role": "佐"},
            {"name": "没药", "dose": "3g", "role": "佐"},
            {"name": "穿山甲", "dose": "3g", "role": "佐"},
            {"name": "皂角刺", "dose": "3g", "role": "佐"},
            {"name": "甘草", "dose": "3g", "role": "使"},
        ],
        "efficacy": "清热解毒，消肿溃坚，活血止痛",
        "indications": "阳证痈疡肿毒初起。红肿焮痛，或身热凛寒，苔薄白或黄，脉数有力",
    },
    {
        "id": "formula-027",
        "name": "龙胆泻肝汤",
        "source": "《医方集解》",
        "category": "清热剂",
        "composition": [
            {"name": "龙胆草", "dose": "6g", "role": "君"},
            {"name": "黄芩", "dose": "9g", "role": "臣"},
            {"name": "栀子", "dose": "9g", "role": "臣"},
            {"name": "泽泻", "dose": "9g", "role": "佐"},
            {"name": "木通", "dose": "6g", "role": "佐"},
            {"name": "车前子", "dose": "9g", "role": "佐"},
            {"name": "当归", "dose": "3g", "role": "佐"},
            {"name": "生地黄", "dose": "9g", "role": "佐"},
            {"name": "柴胡", "dose": "6g", "role": "佐"},
            {"name": "甘草", "dose": "6g", "role": "使"},
        ],
        "efficacy": "清泻肝胆实火，清利肝胆湿热",
        "indications": "肝胆实火上炎证。头痛目赤，胁痛口苦，耳聋耳肿；肝胆湿热下注证。阴肿阴痒，筋痿阴汗，小便淋浊，妇女湿热带下，舌红苔黄，脉弦数有力",
    },
    {
        "id": "formula-028",
        "name": "左金丸",
        "source": "《丹溪心法》",
        "category": "清热剂",
        "composition": [
            {"name": "黄连", "dose": "18g", "role": "君"},
            {"name": "吴茱萸", "dose": "3g", "role": "佐使"},
        ],
        "efficacy": "清泻肝火，降逆止呕",
        "indications": "肝火犯胃证。胁肋疼痛，嘈杂吞酸，呕吐口苦，舌红苔黄，脉弦数",
    },

    # ===================================================================
    # 祛暑剂 (2)
    # ===================================================================
    {
        "id": "formula-029",
        "name": "清暑益气汤",
        "source": "《温热经纬》",
        "category": "祛暑剂",
        "composition": [
            {"name": "西洋参", "dose": "9g", "role": "君"},
            {"name": "石斛", "dose": "15g", "role": "臣"},
            {"name": "麦冬", "dose": "9g", "role": "臣"},
            {"name": "黄连", "dose": "3g", "role": "佐"},
            {"name": "竹叶", "dose": "6g", "role": "佐"},
            {"name": "荷梗", "dose": "15g", "role": "佐"},
            {"name": "知母", "dose": "9g", "role": "佐"},
            {"name": "甘草", "dose": "3g", "role": "佐"},
            {"name": "粳米", "dose": "15g", "role": "佐"},
            {"name": "西瓜翠衣", "dose": "30g", "role": "佐"},
        ],
        "efficacy": "清暑益气，养阴生津",
        "indications": "暑热气津两伤证。身热汗多，口渴心烦，小便短赤，体倦少气，精神不振，脉虚数",
    },
    {
        "id": "formula-030",
        "name": "香薷散",
        "source": "《太平惠民和剂局方》",
        "category": "祛暑剂",
        "composition": [
            {"name": "香薷", "dose": "15g", "role": "君"},
            {"name": "白扁豆", "dose": "12g", "role": "臣"},
            {"name": "厚朴", "dose": "12g", "role": "佐"},
        ],
        "efficacy": "祛暑解表，化湿和中",
        "indications": "阴暑。恶寒发热，头重身痛，无汗，腹痛吐泻，胸脘痞闷，舌苔白腻，脉浮",
    },

    # ===================================================================
    # 温里剂 (4)
    # ===================================================================
    {
        "id": "formula-031",
        "name": "理中丸",
        "source": "《伤寒论》",
        "category": "温里剂",
        "composition": [
            {"name": "干姜", "dose": "9g", "role": "君"},
            {"name": "人参", "dose": "9g", "role": "臣"},
            {"name": "白术", "dose": "9g", "role": "佐"},
            {"name": "甘草", "dose": "9g", "role": "使"},
        ],
        "efficacy": "温中祛寒，补气健脾",
        "indications": "脾胃虚寒证。脘腹疼痛，喜温喜按，呕吐便溏，脘痞食少，畏寒肢冷，口不渴，舌淡苔白润，脉沉细或沉迟无力",
    },
    {
        "id": "formula-032",
        "name": "小建中汤",
        "source": "《伤寒论》",
        "category": "温里剂",
        "composition": [
            {"name": "饴糖", "dose": "30g", "role": "君"},
            {"name": "桂枝", "dose": "9g", "role": "臣"},
            {"name": "芍药", "dose": "18g", "role": "臣"},
            {"name": "生姜", "dose": "9g", "role": "佐"},
            {"name": "大枣", "dose": "6枚", "role": "佐"},
            {"name": "甘草", "dose": "6g", "role": "使"},
        ],
        "efficacy": "温中补虚，和里缓急",
        "indications": "中焦虚寒，肝脾不和证。腹中拘急疼痛，喜温喜按，神疲乏力，虚怯少气；或心中悸动，虚烦不宁，面色无华；或伴四肢酸楚，手足烦热，咽干口燥，舌淡苔白，脉细弦",
    },
    {
        "id": "formula-033",
        "name": "四逆汤",
        "source": "《伤寒论》",
        "category": "温里剂",
        "composition": [
            {"name": "附子", "dose": "15g", "role": "君"},
            {"name": "干姜", "dose": "9g", "role": "臣"},
            {"name": "甘草", "dose": "6g", "role": "佐使"},
        ],
        "efficacy": "回阳救逆",
        "indications": "心肾阳衰寒厥证。四肢厥逆，恶寒蜷卧，神衰欲寐，呕吐不渴，腹痛下利，舌苔白滑，脉微细",
    },
    {
        "id": "formula-034",
        "name": "当归四逆汤",
        "source": "《伤寒论》",
        "category": "温里剂",
        "composition": [
            {"name": "当归", "dose": "9g", "role": "君"},
            {"name": "桂枝", "dose": "9g", "role": "臣"},
            {"name": "芍药", "dose": "9g", "role": "臣"},
            {"name": "细辛", "dose": "3g", "role": "佐"},
            {"name": "通草", "dose": "6g", "role": "佐"},
            {"name": "大枣", "dose": "8枚", "role": "佐"},
            {"name": "甘草", "dose": "6g", "role": "使"},
        ],
        "efficacy": "温经散寒，养血通脉",
        "indications": "血虚寒厥证。手足厥寒，舌淡苔白，脉细欲绝或沉细；或腰、股、腿、足、臂、手冷痛",
    },

    # ===================================================================
    # 表里双解剂 (2)
    # ===================================================================
    {
        "id": "formula-035",
        "name": "防风通圣散",
        "source": "《宣明论方》",
        "category": "表里双解剂",
        "composition": [
            {"name": "防风", "dose": "15g", "role": "君"},
            {"name": "荆芥", "dose": "15g", "role": "君"},
            {"name": "连翘", "dose": "15g", "role": "臣"},
            {"name": "麻黄", "dose": "15g", "role": "臣"},
            {"name": "薄荷", "dose": "15g", "role": "臣"},
            {"name": "川芎", "dose": "15g", "role": "佐"},
            {"name": "当归", "dose": "15g", "role": "佐"},
            {"name": "白芍", "dose": "15g", "role": "佐"},
            {"name": "白术", "dose": "15g", "role": "佐"},
            {"name": "栀子", "dose": "15g", "role": "佐"},
            {"name": "大黄", "dose": "15g", "role": "佐"},
            {"name": "芒硝", "dose": "15g", "role": "佐"},
            {"name": "石膏", "dose": "30g", "role": "佐"},
            {"name": "黄芩", "dose": "30g", "role": "佐"},
            {"name": "桔梗", "dose": "30g", "role": "佐"},
            {"name": "滑石", "dose": "90g", "role": "佐"},
            {"name": "甘草", "dose": "60g", "role": "使"},
        ],
        "efficacy": "疏风解表，泻热通里",
        "indications": "风热壅盛，表里俱实证。憎寒壮热，头目昏眩，目赤睛痛，口苦而干，咽喉不利，胸膈痞闷，咳呕喘满，涕唾稠粘，大便秘结，小便赤涩，舌苔黄腻，脉数有力",
    },
    {
        "id": "formula-036",
        "name": "葛根黄芩黄连汤",
        "source": "《伤寒论》",
        "category": "表里双解剂",
        "composition": [
            {"name": "葛根", "dose": "15g", "role": "君"},
            {"name": "黄芩", "dose": "9g", "role": "臣"},
            {"name": "黄连", "dose": "9g", "role": "臣"},
            {"name": "甘草", "dose": "6g", "role": "佐使"},
        ],
        "efficacy": "解表清里",
        "indications": "协热下利。身热下利，胸脘烦热，口干作渴，喘而汗出，舌红苔黄，脉数或促",
    },

    # ===================================================================
    # 补益剂 (12)
    # ===================================================================
    {
        "id": "formula-037",
        "name": "八珍汤",
        "source": "《瑞竹堂经验方》",
        "category": "补益剂",
        "composition": [
            {"name": "人参", "dose": "9g", "role": "君"},
            {"name": "白术", "dose": "9g", "role": "臣"},
            {"name": "茯苓", "dose": "9g", "role": "臣"},
            {"name": "当归", "dose": "9g", "role": "臣"},
            {"name": "川芎", "dose": "6g", "role": "佐"},
            {"name": "白芍", "dose": "9g", "role": "佐"},
            {"name": "熟地黄", "dose": "12g", "role": "佐"},
            {"name": "甘草", "dose": "5g", "role": "使"},
            {"name": "生姜", "dose": "6g", "role": "使"},
            {"name": "大枣", "dose": "3枚", "role": "使"},
        ],
        "efficacy": "益气补血",
        "indications": "气血两虚证。面色苍白或萎黄，头晕耳眩，四肢倦怠，气短懒言，心悸怔忡，饮食减少，舌淡苔薄白，脉细弱或虚大无力",
    },
    {
        "id": "formula-038",
        "name": "十全大补汤",
        "source": "《太平惠民和剂局方》",
        "category": "补益剂",
        "composition": [
            {"name": "人参", "dose": "9g", "role": "君"},
            {"name": "白术", "dose": "9g", "role": "臣"},
            {"name": "茯苓", "dose": "9g", "role": "臣"},
            {"name": "当归", "dose": "9g", "role": "臣"},
            {"name": "川芎", "dose": "6g", "role": "佐"},
            {"name": "白芍", "dose": "9g", "role": "佐"},
            {"name": "熟地黄", "dose": "12g", "role": "佐"},
            {"name": "黄芪", "dose": "12g", "role": "佐"},
            {"name": "肉桂", "dose": "3g", "role": "佐"},
            {"name": "甘草", "dose": "5g", "role": "使"},
        ],
        "efficacy": "温补气血",
        "indications": "气血两虚证。五劳七伤，面色萎黄，食少无味，精神倦怠，四肢乏力，气短心悸，虚劳咳嗽，遗精失血，妇人崩漏，疮疡不敛",
    },
    {
        "id": "formula-039",
        "name": "归脾汤",
        "source": "《正体类要》",
        "category": "补益剂",
        "composition": [
            {"name": "黄芪", "dose": "12g", "role": "君"},
            {"name": "人参", "dose": "9g", "role": "臣"},
            {"name": "白术", "dose": "9g", "role": "臣"},
            {"name": "当归", "dose": "9g", "role": "佐"},
            {"name": "龙眼肉", "dose": "9g", "role": "佐"},
            {"name": "茯神", "dose": "9g", "role": "佐"},
            {"name": "酸枣仁", "dose": "9g", "role": "佐"},
            {"name": "远志", "dose": "6g", "role": "佐"},
            {"name": "木香", "dose": "6g", "role": "佐"},
            {"name": "甘草", "dose": "3g", "role": "使"},
            {"name": "生姜", "dose": "3g", "role": "使"},
            {"name": "大枣", "dose": "3枚", "role": "使"},
        ],
        "efficacy": "益气补血，健脾养心",
        "indications": "心脾气血两虚证。心悸怔忡，健忘失眠，盗汗虚热，食少体倦，面色萎黄，舌淡苔薄白，脉细弱；脾不统血证。便血，皮下紫癜，妇人崩漏，月经超前，量多色淡，或淋漓不止",
    },
    {
        "id": "formula-040",
        "name": "六味地黄丸",
        "source": "《小儿药证直诀》",
        "category": "补益剂",
        "composition": [
            {"name": "熟地黄", "dose": "24g", "role": "君"},
            {"name": "山茱萸", "dose": "12g", "role": "臣"},
            {"name": "山药", "dose": "12g", "role": "臣"},
            {"name": "泽泻", "dose": "9g", "role": "佐"},
            {"name": "牡丹皮", "dose": "9g", "role": "佐"},
            {"name": "茯苓", "dose": "9g", "role": "佐"},
        ],
        "efficacy": "滋补肝肾",
        "indications": "肝肾阴虚证。头晕耳鸣，腰膝酸软，骨蒸潮热，盗汗遗精，消渴，手足心热，口燥咽干，牙齿动摇，足跟作痛，舌红少苔，脉沉细数",
    },
    {
        "id": "formula-041",
        "name": "左归丸",
        "source": "《景岳全书》",
        "category": "补益剂",
        "composition": [
            {"name": "熟地黄", "dose": "24g", "role": "君"},
            {"name": "山药", "dose": "12g", "role": "臣"},
            {"name": "枸杞子", "dose": "12g", "role": "臣"},
            {"name": "山茱萸", "dose": "12g", "role": "佐"},
            {"name": "菟丝子", "dose": "12g", "role": "佐"},
            {"name": "鹿角胶", "dose": "12g", "role": "佐"},
            {"name": "龟板胶", "dose": "12g", "role": "佐"},
            {"name": "川牛膝", "dose": "9g", "role": "佐"},
        ],
        "efficacy": "滋阴补肾，填精益髓",
        "indications": "真阴不足证。头晕目眩，腰酸腿软，遗精滑泄，自汗盗汗，口燥舌干，舌红少苔，脉细",
    },
    {
        "id": "formula-042",
        "name": "右归丸",
        "source": "《景岳全书》",
        "category": "补益剂",
        "composition": [
            {"name": "熟地黄", "dose": "24g", "role": "君"},
            {"name": "附子", "dose": "12g", "role": "臣"},
            {"name": "肉桂", "dose": "6g", "role": "臣"},
            {"name": "鹿角胶", "dose": "12g", "role": "佐"},
            {"name": "山药", "dose": "12g", "role": "佐"},
            {"name": "山茱萸", "dose": "9g", "role": "佐"},
            {"name": "枸杞子", "dose": "9g", "role": "佐"},
            {"name": "菟丝子", "dose": "12g", "role": "佐"},
            {"name": "杜仲", "dose": "12g", "role": "佐"},
            {"name": "当归", "dose": "9g", "role": "佐"},
        ],
        "efficacy": "温补肾阳，填精止遗",
        "indications": "肾阳不足，命门火衰证。年老或久病气衰神疲，畏寒肢冷，腰膝软弱，阳痿遗精，或阳衰无子，或食少便溏，或小便自遗，舌淡苔白，脉沉迟",
    },
    {
        "id": "formula-043",
        "name": "肾气丸",
        "source": "《金匮要略》",
        "category": "补益剂",
        "composition": [
            {"name": "干地黄", "dose": "24g", "role": "君"},
            {"name": "山茱萸", "dose": "12g", "role": "臣"},
            {"name": "山药", "dose": "12g", "role": "臣"},
            {"name": "附子", "dose": "3g", "role": "佐"},
            {"name": "桂枝", "dose": "3g", "role": "佐"},
            {"name": "泽泻", "dose": "9g", "role": "佐"},
            {"name": "茯苓", "dose": "9g", "role": "佐"},
            {"name": "牡丹皮", "dose": "9g", "role": "佐"},
        ],
        "efficacy": "补肾助阳",
        "indications": "肾阳不足证。腰痛脚软，身半以下常有冷感，少腹拘急，小便不利或小便反多，入夜尤甚，阳痿早泄，舌淡而胖，脉虚弱尺部沉细",
    },
    {
        "id": "formula-044",
        "name": "一贯煎",
        "source": "《续名医类案》",
        "category": "补益剂",
        "composition": [
            {"name": "生地黄", "dose": "18g", "role": "君"},
            {"name": "枸杞子", "dose": "12g", "role": "臣"},
            {"name": "当归", "dose": "9g", "role": "臣"},
            {"name": "麦冬", "dose": "9g", "role": "佐"},
            {"name": "沙参", "dose": "9g", "role": "佐"},
            {"name": "川楝子", "dose": "5g", "role": "佐"},
        ],
        "efficacy": "滋阴疏肝",
        "indications": "肝肾阴虚，肝气不舒证。胸脘胁痛，吞酸吐苦，咽干口燥，舌红少津，脉细弱或虚弦；及疝气瘕聚",
    },
    {
        "id": "formula-045",
        "name": "百合固金汤",
        "source": "《医方集解》引周慎斋方",
        "category": "补益剂",
        "composition": [
            {"name": "百合", "dose": "12g", "role": "君"},
            {"name": "麦冬", "dose": "9g", "role": "臣"},
            {"name": "玄参", "dose": "9g", "role": "臣"},
            {"name": "生地黄", "dose": "9g", "role": "佐"},
            {"name": "熟地黄", "dose": "9g", "role": "佐"},
            {"name": "当归", "dose": "9g", "role": "佐"},
            {"name": "白芍", "dose": "6g", "role": "佐"},
            {"name": "贝母", "dose": "6g", "role": "佐"},
            {"name": "桔梗", "dose": "6g", "role": "佐"},
            {"name": "甘草", "dose": "3g", "role": "使"},
        ],
        "efficacy": "滋阴润肺，化痰止咳",
        "indications": "肺肾阴虚，虚火上炎证。咳嗽气喘，痰中带血，咽喉燥痛，头晕目眩，午后潮热，舌红少苔，脉细数",
    },
    {
        "id": "formula-046",
        "name": "补中益气汤",
        "source": "《脾胃论》",
        "category": "补益剂",
        "composition": [
            {"name": "黄芪", "dose": "18g", "role": "君"},
            {"name": "人参", "dose": "6g", "role": "臣"},
            {"name": "白术", "dose": "9g", "role": "臣"},
            {"name": "当归", "dose": "3g", "role": "佐"},
            {"name": "陈皮", "dose": "6g", "role": "佐"},
            {"name": "升麻", "dose": "6g", "role": "佐"},
            {"name": "柴胡", "dose": "6g", "role": "佐"},
            {"name": "甘草", "dose": "9g", "role": "使"},
        ],
        "efficacy": "补中益气，升阳举陷",
        "indications": "脾胃气虚证。饮食减少，体倦肢软，少气懒言，面色萎白，大便稀溏，脉大而虚软；气虚下陷证。脱肛，子宫脱垂，久泻久痢，崩漏等；气虚发热证。身热自汗，渴喜热饮，气短乏力，舌淡，脉虚大无力",
    },
    {
        "id": "formula-047",
        "name": "生脉散",
        "source": "《医学启源》",
        "category": "补益剂",
        "composition": [
            {"name": "人参", "dose": "9g", "role": "君"},
            {"name": "麦冬", "dose": "9g", "role": "臣"},
            {"name": "五味子", "dose": "6g", "role": "佐"},
        ],
        "efficacy": "益气生津，敛阴止汗",
        "indications": "温热、暑热，耗气伤阴证。汗多神疲，体倦乏力，气短懒言，咽干口渴，舌干红少苔，脉虚数；久咳伤肺，气阴两虚证。干咳少痰，短气自汗，口干舌燥，脉虚细",
    },
    {
        "id": "formula-048",
        "name": "人参养荣汤",
        "source": "《三因极一病证方论》",
        "category": "补益剂",
        "composition": [
            {"name": "人参", "dose": "9g", "role": "君"},
            {"name": "当归", "dose": "9g", "role": "臣"},
            {"name": "黄芪", "dose": "12g", "role": "臣"},
            {"name": "白术", "dose": "9g", "role": "佐"},
            {"name": "茯苓", "dose": "9g", "role": "佐"},
            {"name": "白芍", "dose": "9g", "role": "佐"},
            {"name": "熟地黄", "dose": "12g", "role": "佐"},
            {"name": "陈皮", "dose": "6g", "role": "佐"},
            {"name": "五味子", "dose": "6g", "role": "佐"},
            {"name": "远志", "dose": "6g", "role": "佐"},
            {"name": "肉桂", "dose": "3g", "role": "佐"},
            {"name": "甘草", "dose": "6g", "role": "使"},
            {"name": "生姜", "dose": "3g", "role": "使"},
            {"name": "大枣", "dose": "3枚", "role": "使"},
        ],
        "efficacy": "益气补血，养心安神",
        "indications": "积劳虚损，气血两虚证。呼吸少气，行动喘息，心虚惊悸，咽干唇燥，面色萎黄，四肢倦怠，毛发脱落，饮食无味，舌淡苔薄白，脉虚弱",
    },

    # ===================================================================
    # 固涩剂 (4)
    # ===================================================================
    {
        "id": "formula-049",
        "name": "牡蛎散",
        "source": "《太平惠民和剂局方》",
        "category": "固涩剂",
        "composition": [
            {"name": "黄芪", "dose": "30g", "role": "君"},
            {"name": "麻黄根", "dose": "9g", "role": "臣"},
            {"name": "牡蛎", "dose": "30g", "role": "佐"},
            {"name": "小麦", "dose": "30g", "role": "佐"},
        ],
        "efficacy": "敛阴止汗，益气固表",
        "indications": "体虚自汗、盗汗证。常自汗出，夜卧更甚，心悸惊惕，短气烦倦，舌淡红，脉细弱",
    },
    {
        "id": "formula-050",
        "name": "真人养脏汤",
        "source": "《太平惠民和剂局方》",
        "category": "固涩剂",
        "composition": [
            {"name": "罂粟壳", "dose": "18g", "role": "君"},
            {"name": "肉豆蔻", "dose": "12g", "role": "臣"},
            {"name": "诃子", "dose": "12g", "role": "臣"},
            {"name": "人参", "dose": "6g", "role": "佐"},
            {"name": "白术", "dose": "6g", "role": "佐"},
            {"name": "当归", "dose": "6g", "role": "佐"},
            {"name": "白芍", "dose": "15g", "role": "佐"},
            {"name": "肉桂", "dose": "3g", "role": "佐"},
            {"name": "木香", "dose": "9g", "role": "佐"},
            {"name": "甘草", "dose": "6g", "role": "使"},
        ],
        "efficacy": "涩肠固脱，温补脾肾",
        "indications": "久泻久痢，脾肾虚寒证。大便滑脱不禁，腹痛喜温喜按，食少神疲，舌淡苔白，脉迟细",
    },
    {
        "id": "formula-051",
        "name": "四神丸",
        "source": "《证治准绳》",
        "category": "固涩剂",
        "composition": [
            {"name": "补骨脂", "dose": "12g", "role": "君"},
            {"name": "肉豆蔻", "dose": "6g", "role": "臣"},
            {"name": "五味子", "dose": "6g", "role": "佐"},
            {"name": "吴茱萸", "dose": "3g", "role": "佐"},
        ],
        "efficacy": "温肾暖脾，固肠止泻",
        "indications": "脾肾虚寒之五更泄泻。五更泄泻，不思饮食，食不消化，或久泻不愈，腹痛喜温，腰酸肢冷，神疲乏力，舌淡苔白，脉沉迟无力",
    },
    {
        "id": "formula-052",
        "name": "金锁固精丸",
        "source": "《医方集解》",
        "category": "固涩剂",
        "composition": [
            {"name": "沙苑子", "dose": "12g", "role": "君"},
            {"name": "芡实", "dose": "12g", "role": "臣"},
            {"name": "莲须", "dose": "12g", "role": "佐"},
            {"name": "龙骨", "dose": "3g", "role": "佐"},
            {"name": "牡蛎", "dose": "3g", "role": "佐"},
            {"name": "莲子", "dose": "适量", "role": "使"},
        ],
        "efficacy": "固肾涩精",
        "indications": "肾虚不固之遗精。遗精滑泄，神疲乏力，腰痛耳鸣，四肢酸软，舌淡苔白，脉细弱",
    },

    # ===================================================================
    # 安神剂 (3)
    # ===================================================================
    {
        "id": "formula-053",
        "name": "朱砂安神丸",
        "source": "《内外伤辨惑论》",
        "category": "安神剂",
        "composition": [
            {"name": "朱砂", "dose": "1g", "role": "君"},
            {"name": "黄连", "dose": "6g", "role": "臣"},
            {"name": "当归", "dose": "6g", "role": "佐"},
            {"name": "生地黄", "dose": "6g", "role": "佐"},
            {"name": "甘草", "dose": "3g", "role": "使"},
        ],
        "efficacy": "镇心安神，清热养血",
        "indications": "心火亢盛，阴血不足证。失眠多梦，惊悸怔忡，心烦神乱，胸中烦热，舌红，脉细数",
    },
    {
        "id": "formula-054",
        "name": "天王补心丹",
        "source": "《校注妇人良方》",
        "category": "安神剂",
        "composition": [
            {"name": "生地黄", "dose": "12g", "role": "君"},
            {"name": "麦冬", "dose": "9g", "role": "臣"},
            {"name": "天冬", "dose": "9g", "role": "臣"},
            {"name": "玄参", "dose": "9g", "role": "佐"},
            {"name": "丹参", "dose": "9g", "role": "佐"},
            {"name": "当归", "dose": "9g", "role": "佐"},
            {"name": "人参", "dose": "5g", "role": "佐"},
            {"name": "茯苓", "dose": "5g", "role": "佐"},
            {"name": "酸枣仁", "dose": "9g", "role": "佐"},
            {"name": "远志", "dose": "5g", "role": "佐"},
            {"name": "柏子仁", "dose": "9g", "role": "佐"},
            {"name": "五味子", "dose": "5g", "role": "佐"},
            {"name": "桔梗", "dose": "5g", "role": "佐"},
            {"name": "朱砂", "dose": "1g", "role": "使"},
        ],
        "efficacy": "滋阴养血，补心安神",
        "indications": "阴虚血少，神志不安证。心悸怔忡，虚烦失眠，神疲健忘，或梦遗，手足心热，口舌生疮，大便干结，舌红少苔，脉细数",
    },
    {
        "id": "formula-055",
        "name": "酸枣仁汤",
        "source": "《金匮要略》",
        "category": "安神剂",
        "composition": [
            {"name": "酸枣仁", "dose": "15g", "role": "君"},
            {"name": "茯苓", "dose": "9g", "role": "臣"},
            {"name": "知母", "dose": "9g", "role": "佐"},
            {"name": "川芎", "dose": "6g", "role": "佐"},
            {"name": "甘草", "dose": "3g", "role": "使"},
        ],
        "efficacy": "养血安神，清热除烦",
        "indications": "肝血不足，虚热内扰证。虚烦失眠，心悸不安，头目眩晕，咽干口燥，舌红，脉弦细",
    },

    # ===================================================================
    # 开窍剂 (2)
    # ===================================================================
    {
        "id": "formula-056",
        "name": "安宫牛黄丸",
        "source": "《温病条辨》",
        "category": "开窍剂",
        "composition": [
            {"name": "牛黄", "dose": "30g", "role": "君"},
            {"name": "麝香", "dose": "7.5g", "role": "君"},
            {"name": "犀角（水牛角代）", "dose": "30g", "role": "臣"},
            {"name": "黄连", "dose": "30g", "role": "臣"},
            {"name": "黄芩", "dose": "30g", "role": "臣"},
            {"name": "栀子", "dose": "30g", "role": "臣"},
            {"name": "冰片", "dose": "7.5g", "role": "佐"},
            {"name": "郁金", "dose": "30g", "role": "佐"},
            {"name": "雄黄", "dose": "30g", "role": "佐"},
            {"name": "朱砂", "dose": "30g", "role": "佐"},
            {"name": "珍珠", "dose": "15g", "role": "佐"},
            {"name": "金箔", "dose": "适量", "role": "使"},
        ],
        "efficacy": "清热解毒，豁痰开窍",
        "indications": "邪热内陷心包证。高热烦躁，神昏谵语，口干舌燥，痰涎壅盛，舌红或绛，脉数有力；亦治中风昏迷，惊厥属痰热内闭者",
    },
    {
        "id": "formula-057",
        "name": "苏合香丸",
        "source": "《太平惠民和剂局方》",
        "category": "开窍剂",
        "composition": [
            {"name": "苏合香", "dose": "30g", "role": "君"},
            {"name": "麝香", "dose": "30g", "role": "君"},
            {"name": "冰片", "dose": "30g", "role": "臣"},
            {"name": "安息香", "dose": "30g", "role": "臣"},
            {"name": "香附", "dose": "30g", "role": "佐"},
            {"name": "檀香", "dose": "30g", "role": "佐"},
            {"name": "木香", "dose": "30g", "role": "佐"},
            {"name": "沉香", "dose": "30g", "role": "佐"},
            {"name": "乳香", "dose": "30g", "role": "佐"},
            {"name": "丁香", "dose": "30g", "role": "佐"},
            {"name": "白术", "dose": "30g", "role": "佐"},
            {"name": "诃子", "dose": "30g", "role": "佐"},
            {"name": "荜茇", "dose": "30g", "role": "佐"},
            {"name": "犀角（水牛角代）", "dose": "30g", "role": "佐"},
            {"name": "朱砂", "dose": "30g", "role": "使"},
        ],
        "efficacy": "芳香开窍，行气温中",
        "indications": "寒闭证。突然昏倒，牙关紧闭，不省人事，苔白，脉迟；心腹猝痛，甚则昏厥；亦治中风、中气及感受时行瘴疠之气",
    },

    # ===================================================================
    # 理气剂 (4)
    # ===================================================================
    {
        "id": "formula-058",
        "name": "越鞠丸",
        "source": "《丹溪心法》",
        "category": "理气剂",
        "composition": [
            {"name": "香附", "dose": "6g", "role": "君"},
            {"name": "川芎", "dose": "6g", "role": "臣"},
            {"name": "苍术", "dose": "6g", "role": "臣"},
            {"name": "栀子", "dose": "6g", "role": "佐"},
            {"name": "神曲", "dose": "6g", "role": "佐"},
        ],
        "efficacy": "行气解郁",
        "indications": "六郁证。胸膈痞闷，脘腹胀痛，嗳腐吞酸，恶心呕吐，饮食不消",
    },
    {
        "id": "formula-059",
        "name": "柴胡疏肝散",
        "source": "《证治准绳》引《医学统旨》",
        "category": "理气剂",
        "composition": [
            {"name": "柴胡", "dose": "6g", "role": "君"},
            {"name": "陈皮", "dose": "6g", "role": "臣"},
            {"name": "川芎", "dose": "5g", "role": "臣"},
            {"name": "香附", "dose": "5g", "role": "佐"},
            {"name": "枳壳", "dose": "5g", "role": "佐"},
            {"name": "芍药", "dose": "5g", "role": "佐"},
            {"name": "甘草", "dose": "3g", "role": "使"},
        ],
        "efficacy": "疏肝理气，活血止痛",
        "indications": "肝气郁滞证。胁肋疼痛，胸闷善太息，情志抑郁易怒，或嗳气，脘腹胀满，脉弦",
    },
    {
        "id": "formula-060",
        "name": "瓜蒌薤白白酒汤",
        "source": "《金匮要略》",
        "category": "理气剂",
        "composition": [
            {"name": "瓜蒌", "dose": "12g", "role": "君"},
            {"name": "薤白", "dose": "12g", "role": "臣"},
            {"name": "白酒", "dose": "适量", "role": "佐使"},
        ],
        "efficacy": "通阳散结，行气祛痰",
        "indications": "胸阳不振，痰气互结之胸痹轻证。胸中闷痛，甚则胸痛彻背，喘息咳唾，短气，舌苔白腻，脉沉弦或紧",
    },
    {
        "id": "formula-061",
        "name": "半夏厚朴汤",
        "source": "《金匮要略》",
        "category": "理气剂",
        "composition": [
            {"name": "半夏", "dose": "12g", "role": "君"},
            {"name": "厚朴", "dose": "9g", "role": "臣"},
            {"name": "茯苓", "dose": "12g", "role": "佐"},
            {"name": "生姜", "dose": "9g", "role": "佐"},
            {"name": "苏叶", "dose": "6g", "role": "佐"},
        ],
        "efficacy": "行气散结，降逆化痰",
        "indications": "梅核气。咽中如有物阻，咯吐不出，吞咽不下，胸膈满闷，或咳或呕，舌苔白润或白滑，脉弦缓或弦滑",
    },

    # ===================================================================
    # 理血剂 (6)
    # ===================================================================
    {
        "id": "formula-062",
        "name": "血府逐瘀汤",
        "source": "《医林改错》",
        "category": "理血剂",
        "composition": [
            {"name": "桃仁", "dose": "12g", "role": "君"},
            {"name": "红花", "dose": "9g", "role": "君"},
            {"name": "当归", "dose": "9g", "role": "臣"},
            {"name": "生地黄", "dose": "9g", "role": "臣"},
            {"name": "川芎", "dose": "5g", "role": "佐"},
            {"name": "赤芍", "dose": "6g", "role": "佐"},
            {"name": "牛膝", "dose": "9g", "role": "佐"},
            {"name": "桔梗", "dose": "5g", "role": "佐"},
            {"name": "柴胡", "dose": "3g", "role": "佐"},
            {"name": "枳壳", "dose": "6g", "role": "佐"},
            {"name": "甘草", "dose": "3g", "role": "使"},
        ],
        "efficacy": "活血化瘀，行气止痛",
        "indications": "胸中血瘀证。胸痛，头痛，日久不愈，痛如针刺而有定处，或呃逆日久不止，或饮水即呛，干呕，或心悸怔忡，或夜不能睡，或夜寐不安，或急躁善怒，或入暮潮热，或舌质暗红有瘀斑、瘀点，唇暗或两目暗黑，脉涩或弦紧",
    },
    {
        "id": "formula-063",
        "name": "补阳还五汤",
        "source": "《医林改错》",
        "category": "理血剂",
        "composition": [
            {"name": "黄芪", "dose": "120g", "role": "君"},
            {"name": "当归", "dose": "6g", "role": "臣"},
            {"name": "川芎", "dose": "3g", "role": "佐"},
            {"name": "赤芍", "dose": "5g", "role": "佐"},
            {"name": "桃仁", "dose": "3g", "role": "佐"},
            {"name": "红花", "dose": "3g", "role": "佐"},
            {"name": "地龙", "dose": "3g", "role": "佐"},
        ],
        "efficacy": "补气，活血，通络",
        "indications": "中风之气虚血瘀证。半身不遂，口眼歪斜，语言謇涩，口角流涎，下肢痿废，小便频数或遗尿不禁，舌苔白，脉缓",
    },
    {
        "id": "formula-064",
        "name": "温经汤",
        "source": "《金匮要略》",
        "category": "理血剂",
        "composition": [
            {"name": "吴茱萸", "dose": "9g", "role": "君"},
            {"name": "桂枝", "dose": "6g", "role": "臣"},
            {"name": "当归", "dose": "6g", "role": "臣"},
            {"name": "川芎", "dose": "6g", "role": "佐"},
            {"name": "芍药", "dose": "6g", "role": "佐"},
            {"name": "牡丹皮", "dose": "6g", "role": "佐"},
            {"name": "阿胶", "dose": "6g", "role": "佐"},
            {"name": "麦冬", "dose": "9g", "role": "佐"},
            {"name": "人参", "dose": "6g", "role": "佐"},
            {"name": "甘草", "dose": "6g", "role": "佐"},
            {"name": "半夏", "dose": "6g", "role": "佐"},
            {"name": "生姜", "dose": "6g", "role": "使"},
        ],
        "efficacy": "温经散寒，养血祛瘀",
        "indications": "冲任虚寒，瘀血阻滞证。漏下不止，月经不调，或前或后，或逾期不止，或一月再行，或经停不至，傍晚发热，手心烦热，唇口干燥，少腹里急，腹满；亦治妇人久不受孕",
    },
    {
        "id": "formula-065",
        "name": "生化汤",
        "source": "《傅青主女科》",
        "category": "理血剂",
        "composition": [
            {"name": "当归", "dose": "24g", "role": "君"},
            {"name": "川芎", "dose": "9g", "role": "臣"},
            {"name": "桃仁", "dose": "6g", "role": "佐"},
            {"name": "干姜", "dose": "2g", "role": "佐"},
            {"name": "甘草", "dose": "2g", "role": "使"},
        ],
        "efficacy": "养血祛瘀，温经止痛",
        "indications": "血虚寒凝，瘀血阻滞证。产后恶露不行，小腹冷痛",
    },
    {
        "id": "formula-066",
        "name": "小蓟饮子",
        "source": "《济生方》录自《玉机微义》",
        "category": "理血剂",
        "composition": [
            {"name": "小蓟", "dose": "15g", "role": "君"},
            {"name": "生地黄", "dose": "12g", "role": "臣"},
            {"name": "藕节", "dose": "9g", "role": "佐"},
            {"name": "蒲黄", "dose": "9g", "role": "佐"},
            {"name": "滑石", "dose": "9g", "role": "佐"},
            {"name": "木通", "dose": "6g", "role": "佐"},
            {"name": "淡竹叶", "dose": "6g", "role": "佐"},
            {"name": "栀子", "dose": "9g", "role": "佐"},
            {"name": "当归", "dose": "6g", "role": "佐"},
            {"name": "甘草", "dose": "6g", "role": "使"},
        ],
        "efficacy": "凉血止血，利水通淋",
        "indications": "热结下焦之血淋、尿血。尿中带血，小便频数，赤涩热痛，舌红，脉数",
    },
    {
        "id": "formula-067",
        "name": "咳血方",
        "source": "《丹溪心法》",
        "category": "理血剂",
        "composition": [
            {"name": "青黛", "dose": "6g", "role": "君"},
            {"name": "瓜蒌仁", "dose": "9g", "role": "臣"},
            {"name": "海浮石", "dose": "9g", "role": "佐"},
            {"name": "栀子", "dose": "9g", "role": "佐"},
            {"name": "诃子", "dose": "6g", "role": "佐"},
        ],
        "efficacy": "清肝宁肺，凉血止血",
        "indications": "肝火犯肺之咳血证。咳嗽痰稠带血，咯吐不爽，心烦易怒，胸胁作痛，咽干口苦，颊赤便秘，舌红苔黄，脉弦数",
    },

    # ===================================================================
    # 治风剂 (4)
    # ===================================================================
    {
        "id": "formula-068",
        "name": "川芎茶调散",
        "source": "《太平惠民和剂局方》",
        "category": "治风剂",
        "composition": [
            {"name": "川芎", "dose": "12g", "role": "君"},
            {"name": "薄荷", "dose": "12g", "role": "臣"},
            {"name": "荆芥", "dose": "12g", "role": "臣"},
            {"name": "防风", "dose": "5g", "role": "佐"},
            {"name": "白芷", "dose": "6g", "role": "佐"},
            {"name": "羌活", "dose": "6g", "role": "佐"},
            {"name": "细辛", "dose": "3g", "role": "佐"},
            {"name": "甘草", "dose": "6g", "role": "使"},
            {"name": "茶叶", "dose": "适量", "role": "使"},
        ],
        "efficacy": "疏风止痛",
        "indications": "外感风邪头痛。偏正头痛或颠顶作痛，恶寒发热，目眩鼻塞，舌苔薄白，脉浮",
    },
    {
        "id": "formula-069",
        "name": "消风散",
        "source": "《外科正宗》",
        "category": "治风剂",
        "composition": [
            {"name": "荆芥", "dose": "6g", "role": "君"},
            {"name": "防风", "dose": "6g", "role": "君"},
            {"name": "蝉蜕", "dose": "6g", "role": "臣"},
            {"name": "牛蒡子", "dose": "6g", "role": "臣"},
            {"name": "苍术", "dose": "6g", "role": "佐"},
            {"name": "苦参", "dose": "6g", "role": "佐"},
            {"name": "木通", "dose": "3g", "role": "佐"},
            {"name": "石膏", "dose": "6g", "role": "佐"},
            {"name": "知母", "dose": "6g", "role": "佐"},
            {"name": "当归", "dose": "6g", "role": "佐"},
            {"name": "生地黄", "dose": "6g", "role": "佐"},
            {"name": "胡麻仁", "dose": "6g", "role": "佐"},
            {"name": "甘草", "dose": "3g", "role": "使"},
        ],
        "efficacy": "疏风除湿，清热养血",
        "indications": "风疹、湿疹。皮肤瘙痒，疹出色红，或遍身云片斑点，抓破后渗出津水，苔白或黄，脉浮数",
    },
    {
        "id": "formula-070",
        "name": "天麻钩藤饮",
        "source": "《杂病证治新义》",
        "category": "治风剂",
        "composition": [
            {"name": "天麻", "dose": "9g", "role": "君"},
            {"name": "钩藤", "dose": "12g", "role": "君"},
            {"name": "石决明", "dose": "18g", "role": "臣"},
            {"name": "栀子", "dose": "9g", "role": "佐"},
            {"name": "黄芩", "dose": "9g", "role": "佐"},
            {"name": "川牛膝", "dose": "12g", "role": "佐"},
            {"name": "杜仲", "dose": "9g", "role": "佐"},
            {"name": "益母草", "dose": "9g", "role": "佐"},
            {"name": "桑寄生", "dose": "9g", "role": "佐"},
            {"name": "夜交藤", "dose": "9g", "role": "佐"},
            {"name": "茯神", "dose": "9g", "role": "佐"},
        ],
        "efficacy": "平肝熄风，清热活血，补益肝肾",
        "indications": "肝阳偏亢，肝风上扰证。头痛眩晕，失眠多梦，或口苦面红，舌红苔黄，脉弦或数",
    },
    {
        "id": "formula-071",
        "name": "镇肝熄风汤",
        "source": "《医学衷中参西录》",
        "category": "治风剂",
        "composition": [
            {"name": "怀牛膝", "dose": "30g", "role": "君"},
            {"name": "代赭石", "dose": "30g", "role": "臣"},
            {"name": "龙骨", "dose": "15g", "role": "臣"},
            {"name": "牡蛎", "dose": "15g", "role": "臣"},
            {"name": "龟板", "dose": "15g", "role": "佐"},
            {"name": "玄参", "dose": "15g", "role": "佐"},
            {"name": "天冬", "dose": "15g", "role": "佐"},
            {"name": "白芍", "dose": "15g", "role": "佐"},
            {"name": "茵陈", "dose": "6g", "role": "佐"},
            {"name": "川楝子", "dose": "6g", "role": "佐"},
            {"name": "麦芽", "dose": "6g", "role": "佐"},
            {"name": "甘草", "dose": "5g", "role": "使"},
        ],
        "efficacy": "镇肝熄风，滋阴潜阳",
        "indications": "类中风。头目眩晕，目胀耳鸣，脑部热痛，心中烦热，面色如醉，或时常噫气，或肢体渐觉不利，口角渐形歪斜，甚或眩晕颠仆，昏不知人，移时始醒，或醒后不能复原，精神短少，脉长有力",
    },

    # ===================================================================
    # 治燥剂 (3)
    # ===================================================================
    {
        "id": "formula-072",
        "name": "杏苏散",
        "source": "《温病条辨》",
        "category": "治燥剂",
        "composition": [
            {"name": "杏仁", "dose": "9g", "role": "君"},
            {"name": "苏叶", "dose": "9g", "role": "君"},
            {"name": "半夏", "dose": "9g", "role": "臣"},
            {"name": "陈皮", "dose": "6g", "role": "佐"},
            {"name": "前胡", "dose": "9g", "role": "佐"},
            {"name": "桔梗", "dose": "6g", "role": "佐"},
            {"name": "枳壳", "dose": "6g", "role": "佐"},
            {"name": "茯苓", "dose": "9g", "role": "佐"},
            {"name": "甘草", "dose": "3g", "role": "佐"},
            {"name": "生姜", "dose": "3g", "role": "佐"},
            {"name": "大枣", "dose": "3枚", "role": "使"},
        ],
        "efficacy": "轻宣凉燥，理肺化痰",
        "indications": "外感凉燥证。恶寒无汗，头微痛，咳嗽痰稀，鼻塞咽干，苔白，脉弦",
    },
    {
        "id": "formula-073",
        "name": "桑杏汤",
        "source": "《温病条辨》",
        "category": "治燥剂",
        "composition": [
            {"name": "桑叶", "dose": "3g", "role": "君"},
            {"name": "杏仁", "dose": "5g", "role": "臣"},
            {"name": "沙参", "dose": "6g", "role": "佐"},
            {"name": "浙贝母", "dose": "3g", "role": "佐"},
            {"name": "豆豉", "dose": "3g", "role": "佐"},
            {"name": "栀子皮", "dose": "3g", "role": "佐"},
            {"name": "梨皮", "dose": "3g", "role": "佐"},
        ],
        "efficacy": "清宣温燥，润肺止咳",
        "indications": "外感温燥证。身热不甚，口渴，咽干鼻燥，干咳无痰或痰少而粘，舌红苔薄白而干，脉浮数而右脉大",
    },
    {
        "id": "formula-074",
        "name": "麦门冬汤",
        "source": "《金匮要略》",
        "category": "治燥剂",
        "composition": [
            {"name": "麦冬", "dose": "42g", "role": "君"},
            {"name": "人参", "dose": "9g", "role": "臣"},
            {"name": "甘草", "dose": "6g", "role": "佐"},
            {"name": "粳米", "dose": "9g", "role": "佐"},
            {"name": "大枣", "dose": "4枚", "role": "佐"},
            {"name": "半夏", "dose": "9g", "role": "佐"},
        ],
        "efficacy": "润肺益胃，降逆下气",
        "indications": "肺痿。咳嗽气喘，咽喉不利，咯痰不爽，或咳唾涎沫，口干咽燥，舌红少苔，脉虚数；胃阴不足证。呕吐，呃逆，口渴咽干，舌红少苔，脉虚数",
    },

    # ===================================================================
    # 祛湿剂 (5)
    # ===================================================================
    {
        "id": "formula-075",
        "name": "平胃散",
        "source": "《太平惠民和剂局方》",
        "category": "祛湿剂",
        "composition": [
            {"name": "苍术", "dose": "15g", "role": "君"},
            {"name": "厚朴", "dose": "9g", "role": "臣"},
            {"name": "陈皮", "dose": "9g", "role": "佐"},
            {"name": "甘草", "dose": "6g", "role": "使"},
            {"name": "生姜", "dose": "3g", "role": "使"},
            {"name": "大枣", "dose": "3枚", "role": "使"},
        ],
        "efficacy": "燥湿运脾，行气和胃",
        "indications": "湿滞脾胃证。脘腹胀满，不思饮食，口淡无味，恶心呕吐，嗳气吞酸，肢体沉重，怠惰嗜卧，常多自利，舌苔白腻而厚，脉缓",
    },
    {
        "id": "formula-076",
        "name": "藿香正气散",
        "source": "《太平惠民和剂局方》",
        "category": "祛湿剂",
        "composition": [
            {"name": "藿香", "dose": "15g", "role": "君"},
            {"name": "紫苏", "dose": "6g", "role": "臣"},
            {"name": "白芷", "dose": "6g", "role": "臣"},
            {"name": "半夏曲", "dose": "9g", "role": "佐"},
            {"name": "陈皮", "dose": "9g", "role": "佐"},
            {"name": "白术", "dose": "9g", "role": "佐"},
            {"name": "茯苓", "dose": "9g", "role": "佐"},
            {"name": "厚朴", "dose": "9g", "role": "佐"},
            {"name": "大腹皮", "dose": "9g", "role": "佐"},
            {"name": "桔梗", "dose": "9g", "role": "佐"},
            {"name": "甘草", "dose": "6g", "role": "使"},
            {"name": "生姜", "dose": "3g", "role": "使"},
            {"name": "大枣", "dose": "2枚", "role": "使"},
        ],
        "efficacy": "解表化湿，理气和中",
        "indications": "外感风寒，内伤湿滞证。恶寒发热，头痛，胸膈满闷，脘腹疼痛，恶心呕吐，肠鸣泄泻，舌苔白腻，脉浮或濡缓；及山岚瘴疟等",
    },
    {
        "id": "formula-077",
        "name": "茵陈蒿汤",
        "source": "《伤寒论》",
        "category": "祛湿剂",
        "composition": [
            {"name": "茵陈", "dose": "18g", "role": "君"},
            {"name": "栀子", "dose": "9g", "role": "臣"},
            {"name": "大黄", "dose": "6g", "role": "佐"},
        ],
        "efficacy": "清热，利湿，退黄",
        "indications": "湿热黄疸。一身面目俱黄，黄色鲜明，发热，无汗或但头汗出，口渴欲饮，恶心呕吐，腹微满，小便短赤，大便不爽或秘结，舌红苔黄腻，脉沉数或滑数有力",
    },
    {
        "id": "formula-078",
        "name": "五苓散",
        "source": "《伤寒论》",
        "category": "祛湿剂",
        "composition": [
            {"name": "泽泻", "dose": "15g", "role": "君"},
            {"name": "茯苓", "dose": "9g", "role": "臣"},
            {"name": "猪苓", "dose": "9g", "role": "臣"},
            {"name": "白术", "dose": "9g", "role": "佐"},
            {"name": "桂枝", "dose": "6g", "role": "佐"},
        ],
        "efficacy": "利水渗湿，温阳化气",
        "indications": "膀胱蓄水证。小便不利，头痛微热，烦渴欲饮，甚则水入即吐，舌苔白，脉浮；及水湿内停证。水肿，泄泻，小便不利，以及霍乱吐泻；痰饮。脐下动悸，吐涎沫而头眩，或短气而咳",
    },
    {
        "id": "formula-079",
        "name": "真武汤",
        "source": "《伤寒论》",
        "category": "祛湿剂",
        "composition": [
            {"name": "附子", "dose": "9g", "role": "君"},
            {"name": "茯苓", "dose": "9g", "role": "臣"},
            {"name": "白术", "dose": "6g", "role": "佐"},
            {"name": "芍药", "dose": "9g", "role": "佐"},
            {"name": "生姜", "dose": "9g", "role": "佐"},
        ],
        "efficacy": "温阳利水",
        "indications": "阳虚水泛证。畏寒肢冷，小便不利，四肢沉重疼痛，下肢水肿，腰以下为甚，腹痛下利，或肢体浮肿，舌淡胖，苔白滑，脉沉细",
    },

    # ===================================================================
    # 消食剂 (3)
    # ===================================================================
    {
        "id": "formula-080",
        "name": "保和丸",
        "source": "《丹溪心法》",
        "category": "消食剂",
        "composition": [
            {"name": "山楂", "dose": "18g", "role": "君"},
            {"name": "神曲", "dose": "6g", "role": "臣"},
            {"name": "莱菔子", "dose": "6g", "role": "佐"},
            {"name": "半夏", "dose": "9g", "role": "佐"},
            {"name": "陈皮", "dose": "6g", "role": "佐"},
            {"name": "茯苓", "dose": "9g", "role": "佐"},
            {"name": "连翘", "dose": "6g", "role": "佐"},
        ],
        "efficacy": "消食和胃",
        "indications": "食滞胃脘证。脘腹痞满胀痛，嗳腐吞酸，恶食呕逆，或大便泄泻，舌苔厚腻，脉滑",
    },
    {
        "id": "formula-081",
        "name": "健脾丸",
        "source": "《证治准绳》",
        "category": "消食剂",
        "composition": [
            {"name": "白术", "dose": "15g", "role": "君"},
            {"name": "人参", "dose": "9g", "role": "臣"},
            {"name": "茯苓", "dose": "9g", "role": "臣"},
            {"name": "山药", "dose": "9g", "role": "佐"},
            {"name": "莲子肉", "dose": "9g", "role": "佐"},
            {"name": "山楂", "dose": "6g", "role": "佐"},
            {"name": "神曲", "dose": "6g", "role": "佐"},
            {"name": "麦芽", "dose": "6g", "role": "佐"},
            {"name": "陈皮", "dose": "6g", "role": "佐"},
            {"name": "木香", "dose": "6g", "role": "佐"},
            {"name": "砂仁", "dose": "6g", "role": "佐"},
            {"name": "肉豆蔻", "dose": "6g", "role": "佐"},
            {"name": "甘草", "dose": "6g", "role": "使"},
            {"name": "黄连", "dose": "3g", "role": "佐"},
        ],
        "efficacy": "健脾和胃，消食止泻",
        "indications": "脾虚食积证。食少难消，脘腹痞闷，大便溏薄，倦怠乏力，苔腻微黄，脉虚弱",
    },
    {
        "id": "formula-082",
        "name": "枳实导滞丸",
        "source": "《内外伤辨惑论》",
        "category": "消食剂",
        "composition": [
            {"name": "枳实", "dose": "9g", "role": "君"},
            {"name": "大黄", "dose": "9g", "role": "臣"},
            {"name": "黄芩", "dose": "6g", "role": "佐"},
            {"name": "黄连", "dose": "6g", "role": "佐"},
            {"name": "茯苓", "dose": "6g", "role": "佐"},
            {"name": "白术", "dose": "6g", "role": "佐"},
            {"name": "泽泻", "dose": "6g", "role": "佐"},
            {"name": "神曲", "dose": "9g", "role": "佐"},
        ],
        "efficacy": "消导化积，清热利湿",
        "indications": "湿热食积证。脘腹胀痛，下痢泄泻，或大便秘结，小便短赤，舌苔黄腻，脉沉有力",
    },
]


def seed(db_path: str) -> None:
    """Insert 80 formulas into the database using sync sqlite3."""
    # Resolve path relative to project root
    if not os.path.isabs(db_path):
        db_path = os.path.join("/homedoctor", db_path)

    # Ensure data directory exists
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # Ensure formulas table exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS formulas (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            source TEXT,
            category TEXT,
            composition TEXT DEFAULT '[]',
            efficacy TEXT,
            indications TEXT,
            modifications TEXT DEFAULT '[]',
            modifications_structured TEXT DEFAULT '[]',
            derived_from_id TEXT,
            properties TEXT DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # Create FTS table if not exists
    try:
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS formulas_fts USING fts5(
                name, source, efficacy, indications, category,
                content=formulas, content_rowid=rowid
            )
        """)
    except sqlite3.OperationalError:
        pass  # FTS5 might not be available

    inserted = 0
    for f in FORMULAS:
        composition_json = json.dumps(f["composition"], ensure_ascii=False)
        cursor = conn.execute(
            """INSERT OR IGNORE INTO formulas
               (id, name, source, category, composition, efficacy, indications,
                modifications, modifications_structured, derived_from_id, properties)
               VALUES (?, ?, ?, ?, ?, ?, ?, '[]', '[]', NULL, '{}')""",
            (
                f["id"],
                f["name"],
                f["source"],
                f["category"],
                composition_json,
                f["efficacy"],
                f["indications"],
            ),
        )
        if cursor.rowcount > 0:
            inserted += 1

    conn.commit()

    # Verify total count
    total = conn.execute("SELECT COUNT(*) FROM formulas").fetchone()[0]

    # Category breakdown
    rows = conn.execute(
        "SELECT category, COUNT(*) as cnt FROM formulas GROUP BY category ORDER BY category"
    ).fetchall()

    conn.close()

    print(f"Seeded {inserted} formulas (skipped {len(FORMULAS) - inserted} existing)")
    print(f"Total formulas in database: {total}")
    print(f"\nCategory breakdown:")
    for cat, cnt in rows:
        print(f"  {cat}: {cnt}")

    assert total >= 80, f"Expected at least 80 formulas, got {total}"
    print(f"\n✓ Seeded {inserted} formulas successfully (total: {total})")


if __name__ == "__main__":
    db_path = "data/homedoctor.db"
    if len(sys.argv) > 1:
        if sys.argv[1] in ("--db", "-d"):
            db_path = sys.argv[2]
        else:
            db_path = sys.argv[1]
    seed(db_path)
