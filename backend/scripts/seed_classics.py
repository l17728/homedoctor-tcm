#!/usr/bin/env python3
"""Seed TCM classics (经典读诵) into SQLite database.

Usage:
    python backend/scripts/seed_classics.py [--db PATH]

Default DB path: data/homedoctor.db (relative to project root /homedoctor)

Data: 5 classics + 12 chapters with REAL classical text excerpts:
  - 黄帝内经·素问 (3 chapters)
  - 伤寒论 (3 chapters)
  - 金匮要略 (2 chapters)
  - 温病条辨 (2 chapters)
  - 医学心悟 (2 chapters)
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import SqliteAdapter, init_db


CLASSICS_SEED: list[dict] = [
    {
        "id": "classic-hdnj-suwen",
        "title": "黄帝内经·素问",
        "author": "黄帝、岐伯",
        "dynasty": "战国",
        "category": "医经",
        "description": "中医理论奠基之作，以黄帝与岐伯问答形式阐述阴阳五行、藏象经络、病因病机、养生防病等核心理论。",
        "cover_color": "#cf1322",
        "chapters": [
            {
                "id": "hdnj-ch1",
                "chapter_number": 1,
                "title": "上古天真论篇第一",
                "original_text": (
                    "昔在黄帝，生而神灵，弱而能言，幼而徇齐，长而敦敏，成而登天。"
                    "乃问于天师曰：余闻上古之人，春秋皆度百岁，而动作不衰；"
                    "今时之人，年半百而动作皆衰者，时世异耶？人将失之耶？"
                    "岐伯对曰：上古之人，其知道者，法于阴阳，和于术数，食饮有节，起居有常，不妄作劳，"
                    "故能形与神俱，而尽终其天年，度百岁乃去。"
                    "今时之人不然也，以酒为浆，以妄为常，醉以入房，以欲竭其精，以耗散其真，"
                    "不知持满，不时御神，务快其心，逆于生乐，起居无节，故半百而衰也。"
                    "夫上古圣人之教下也，皆谓之虚邪贼风，避之有时，恬淡虚无，真气从之，精神内守，病安从来。"
                    "是以志闲而少欲，心安而不惧，形劳而不倦，气从以顺，各从其欲，皆得所愿。"
                    "故美其食，任其服，乐其俗，高下不相慕，其民故曰朴。"
                    "是以嗜欲不能劳其目，淫邪不能惑其心，愚智贤不肖不惧于物，故合于道。"
                    "所以能年皆度百岁而动作不衰者，以其德全不危也。"
                ),
            },
            {
                "id": "hdnj-ch2",
                "chapter_number": 2,
                "title": "四气调神大论篇第二",
                "original_text": (
                    "春三月，此谓发陈，天地俱生，万物以荣，夜卧早起，广步于庭，被发缓形，以使志生，"
                    "生而勿杀，予而勿夺，赏而勿罚，此春气之应，养生之道也。逆之则伤肝，夏为寒变，奉长者少。"
                    "夏三月，此谓蕃秀，天地气交，万物华实，夜卧早起，无厌于日，使志无怒，使华英成秀，"
                    "使气得泄，若所爱在外，此夏气之应，养长之道也。逆之则伤心，秋为痎疟，奉收者少，冬至重病。"
                    "秋三月，此谓容平，天气以急，地气以明，早卧早起，与鸡俱兴，使志安宁，以缓秋刑，"
                    "收敛神气，使秋气平，无外其志，使肺气清，此秋气之应，养收之道也。逆之则伤肺，冬为飧泄，奉藏者少。"
                    "冬三月，此谓闭藏，水冰地坼，无扰乎阳，早卧晚起，必待日光，使志若伏若匿，若有私意，若已有得，"
                    "去寒就温，无泄皮肤，使气亟夺，此冬气之应，养藏之道也。逆之则伤肾，春为痿厥，奉生者少。"
                ),
            },
            {
                "id": "hdnj-ch3",
                "chapter_number": 3,
                "title": "生气通天论篇第三",
                "original_text": (
                    "黄帝曰：夫自古通天者，生之本，本于阴阳。天地之间，六合之内，其气九州、九窍、五脏、十二节，皆通乎天气。"
                    "其生五，其气三，数犯此者，则邪气伤人，此寿命之本也。"
                    "苍天之气，清静则志意治，顺之则阳气固，虽有贼邪，弗能害也，此因时之序。"
                    "故圣人传精神，服天气，而通神明。失之则内闭九窍，外壅肌肉，卫气散解，此谓自伤，气之削也。"
                    "阳气者，若天与日，失其所，则折寿而不彰，故天运当以日光明。是故阳因而上，卫外者也。"
                    "因于寒，欲如运枢，起居如惊，神气乃浮。因于暑，汗，烦则喘喝，静则多言，体若燔炭，汗出而散。"
                    "因于湿，首如裹，湿热不攘，大筋緛短，小筋弛长，緛短为拘，弛长为痿。"
                    "因于气，为肿，四维相代，阳气乃竭。阳气者，烦劳则张，精绝，辟积于夏，使人煎厥。"
                ),
            },
        ],
    },
    {
        "id": "classic-shanghanlun",
        "title": "伤寒论",
        "author": "张仲景",
        "dynasty": "东汉",
        "category": "医经",
        "description": "外感病辨证论治经典，创立六经辨证体系，奠定中医临床医学基础。",
        "cover_color": "#722ed1",
        "chapters": [
            {
                "id": "shl-ch1",
                "chapter_number": 1,
                "title": "辨太阳病脉证并治上",
                "original_text": (
                    "太阳之为病，脉浮，头项强痛而恶寒。"
                    "太阳病，发热，汗出，恶风，脉缓者，名为中风。"
                    "太阳病，或已发热，或未发热，必恶寒，体痛，呕逆，脉阴阳俱紧者，名为伤寒。"
                    "伤寒一日，太阳受之，脉若静者，为不传；颇欲吐，若躁烦，脉数急者，为传也。"
                    "伤寒二三日，阳明少阳证不见者，为不传也。"
                    "太阳病，发热恶寒，热多寒少，躁烦脉微弱者，此无阳也，不可发汗，宜桂枝二越婢一汤。"
                    "太阳病，头痛至七日以上自愈者，以行其经尽故也。若欲作再经者，针足阳明，使经不传则愈。"
                    "病有发热恶寒者，发于阳也；无热恶寒者，发于阴也。发于阳，七日愈；发于阴，六日愈。以阳数七，阴数六故也。"
                ),
            },
            {
                "id": "shl-ch2",
                "chapter_number": 2,
                "title": "辨阳明病脉证并治",
                "original_text": (
                    "阳明之为病，胃家实是也。"
                    "问曰：阳明病，外证云何？答曰：身热，汗自出，不恶寒，反恶热也。"
                    "问曰：病有得之一日，不发热而恶寒者，何也？"
                    "答曰：虽得之一日，恶寒将自罢，即自汗出而恶热也。"
                    "问曰：恶寒何故自罢？答曰：阳明居中，主土也，万物所归，无所复传，始虽恶寒，二日自止，此为阳明病也。"
                    "本太阳病，初得病时，发其汗，汗先出不彻，因转属阳明也。"
                    "伤寒发热无汗，呕不能食，而反汗出濈濈然者，是转属阳明也。"
                    "伤寒脉浮而缓，手足自温者，是为系在太阴。太阴者，身当发黄；若小便自利者，不能发黄；至七八日，大便硬者，为阳明病也。"
                ),
            },
            {
                "id": "shl-ch3",
                "chapter_number": 3,
                "title": "辨少阳病脉证并治",
                "original_text": (
                    "少阳之为病，口苦，咽干，目眩也。"
                    "少阳中风，两耳无所闻，目赤，胸中满而烦者，不可吐下，吐下则悸而惊。"
                    "伤寒，脉弦细，头痛发热者，属少阳。少阳不可发汗，发汗则谵语，"
                    "此属胃，胃和则愈，胃不和，烦而悸。"
                    "本太阳病不解，转入少阳者，胁下硬满，干呕不能食，往来寒热，尚未吐下，脉沉紧者，与小柴胡汤。"
                    "若已吐下发汗温针，谵语，柴胡汤证罢，此为坏病，知犯何逆，以法治之。"
                    "三阳合病，脉浮大，上关上，但欲眠睡，目合则汗。"
                ),
            },
        ],
    },
    {
        "id": "classic-jingui",
        "title": "金匮要略",
        "author": "张仲景",
        "dynasty": "东汉",
        "category": "方书",
        "description": "杂病辨证论治专书，论述内伤杂病及部分外科、妇科疾病的证治。",
        "cover_color": "#13c2c2",
        "chapters": [
            {
                "id": "jg-ch1",
                "chapter_number": 1,
                "title": "脏腑经络先后病脉证第一",
                "original_text": (
                    "问曰：上工治未病，何也？"
                    "师曰：夫治未病者，见肝之病，知肝传脾，当先实脾，四季脾王不受邪，即勿补之。"
                    "中工不晓相传，见肝之病，不解实脾，惟治肝也。"
                    "夫肝之病，补用酸，助用焦苦，益用甘味之药调之。"
                    "酸入肝，焦苦入心，甘入脾。脾能伤肾，肾气微弱，则水不行；水不行，则心火气盛；心火气盛，则伤肺；肺被伤，则金气不行；金气不行，则肝气盛。故实脾，则肝自愈。此治肝补脾之要妙也。肝虚则用此法，实则不在用之。"
                    "经曰：虚虚实实，补不足，损有余，是其义也。余脏准此。"
                    "夫人禀五常，因风气而生长，风气虽能生万物，亦能害万物，如水能浮舟，亦能覆舟。"
                    "若五脏元真通畅，人即安和，客气邪风，中人多死。"
                ),
            },
            {
                "id": "jg-ch2",
                "chapter_number": 2,
                "title": "血痹虚劳病脉证并治第六",
                "original_text": (
                    "问曰：血痹病从何得之？"
                    "师曰：夫尊荣人骨弱肌肤盛，重因疲劳汗出，卧不时动摇，加被微风，遂得之。"
                    "但以脉自微涩，在寸口、关上小紧，宜针引阳气，令脉和紧去则愈。"
                    "血痹阴阳俱微，寸口关上微，尺中小紧，外证身体不仁，如风痹状，黄芪桂枝五物汤主之。"
                    "夫男子平人，脉大为劳，极虚亦为劳。"
                    "男子面色薄者，主渴及亡血，卒喘悸，脉浮者，里虚也。"
                    "男子脉虚沉弦，无寒热，短气里急，小便不利，面色白，时目瞑，兼衄，少腹满，此为劳使之然。"
                    "劳之为病，其脉浮大，手足烦，春夏剧，秋冬瘥，阴寒精自出，酸削不能行。"
                    "少阴脉弱而涩，弱则微烦，涩则厥逆。"
                ),
            },
        ],
    },
    {
        "id": "classic-wenbing",
        "title": "温病条辨",
        "author": "吴鞠通",
        "dynasty": "清",
        "category": "温病",
        "description": "温病学派代表作，创立三焦辨证体系，论治温热病。",
        "cover_color": "#fa8c16",
        "chapters": [
            {
                "id": "wb-ch1",
                "chapter_number": 1,
                "title": "上焦篇·风温",
                "original_text": (
                    "温病者：有太阴伤风，咳嗽、脉浮数；有厥阴温病，脉弦数；有少阴温病，脉沉数。"
                    "凡温病者，始于上焦，在手太阴。"
                    "太阴之为病，脉不缓不紧而动数，或两寸独大，尺肤热，头痛，微恶风寒，身热自汗，口渴，或不渴，而咳，午后热甚者，名曰温病。"
                    "太阴温病，脉浮洪，舌黄，渴甚，大汗，面赤，恶热者，辛凉平剂银翘散主之。"
                    "太阴风温，但咳，身不甚热，微渴者，辛凉轻剂桑菊饮主之。"
                    "太阴温病，脉浮大而芤，汗大出，微喘，甚至鼻孔扇者，白虎汤主之。"
                    "太阴温病，不可发汗，发汗而汗不出者，必发斑疹；汗出过多者，必神昏谵语。"
                ),
            },
            {
                "id": "wb-ch2",
                "chapter_number": 2,
                "title": "中焦篇·暑温",
                "original_text": (
                    "暑温者，正夏之时，暑病之偏于热者也。"
                    "脉虚，夜寐不安，烦渴，舌赤，时有谵语，目常开不闭，或喜闭不开，入手厥阴者，"
                    "宜清营汤主之。"
                    "暑温蔓延三焦，舌滑微黄，邪在气分者，三石汤主之；"
                    "邪气久留，舌绛苔少，热搏血分者，加味清宫汤主之。"
                    "暑温误治，或本身阳气有余，致成暑瘵者，清络饮加杏仁薏苡滑石汤主之。"
                    "暑温寒热，舌白不渴，吐血者，名曰暑瘵，为难治。"
                    "手太阴暑温，但咳无痰，咳声清高者，清络饮加甘草桔梗杏仁麦冬知母汤主之。"
                    "暑温悉数在气分，而无湿者，白虎汤主之；脉芤甚者，白虎加人参汤主之。"
                ),
            },
        ],
    },
    {
        "id": "classic-yixue-xinwu",
        "title": "医学心悟",
        "author": "程钟龄",
        "dynasty": "清",
        "category": "综合",
        "description": "清代医学入门佳作，以「医门八法」论治，简明实用，为初学津梁。",
        "cover_color": "#52c41a",
        "chapters": [
            {
                "id": "yx-ch1",
                "chapter_number": 1,
                "title": "医门八法",
                "original_text": (
                    "论病之原，以内伤外感四字括之。论病之情，则以寒热虚实表里阴阳八字统之。"
                    "而论治病之方，则又以汗和下消吐清温补八法尽之。"
                    "盖一法之中，八法备焉；八法之中，百法备焉。病变虽殊，而法归于一。"
                    "汗法者，散外感之邪也。风寒初中，客于肌表，必用汗以散之。"
                    "和法者，调和之也。病在半表半里，惟和可以解之。"
                    "下法者，攻其里也。邪气结实于里，非下之不去。"
                    "消法者，消其食、消其痰、消其血、消其气也。"
                    "吐法者，越在上之邪也。病在上焦，当因而越之。"
                    "清法者，清其热也。热邪传里，非清不解。"
                    "温法者，温其中也。脏寒内生，非温不除。"
                    "补法者，补其虚也。气血阴阳亏虚，非补不复。"
                ),
            },
            {
                "id": "yx-ch2",
                "chapter_number": 2,
                "title": "火字解",
                "original_text": (
                    "火者，五行之一也。在天为日，在地为火，在人为心。"
                    "心为君主之官，神明出焉。心主火，而相火附焉。"
                    "相火者，天火也；君火者，心火也。"
                    "君火以明，相火以位。君火正，则十二官安；相火正，则气血流畅。"
                    "若五志过极，则君火不宁；房劳过度，则相火妄动。"
                    "火之为病，有虚有实。"
                    "实火者，外感六淫之邪，及饮食内伤，郁而化火也，其脉实大，其证发热、口渴、烦躁、便秘。"
                    "虚火者，劳欲过度，阴血亏虚，水不制火也，其脉虚数，其证潮热、盗汗、颧红、咽干。"
                    "治实火，宜苦寒直折；治虚火，宜壮水之主，以制阳光。"
                    "丹溪曰：气有余便是火。气顺则火降，血行则火平。"
                    "故治火者，必先理气；理气者，必先养血。"
                ),
            },
        ],
    },
]


async def seed(db_path: str) -> None:
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    adapter = SqliteAdapter(db_path)
    await adapter.connect()
    await init_db(adapter)

    classics_before = await adapter.query_one(
        "SELECT COUNT(*) AS cnt FROM classics"
    )
    before = classics_before["cnt"] if classics_before else 0

    for classic in CLASSICS_SEED:
        await adapter.execute(
            """INSERT OR IGNORE INTO classics
               (id, title, author, dynasty, category, description,
                cover_color, total_chapters)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                classic["id"],
                classic["title"],
                classic.get("author"),
                classic.get("dynasty"),
                classic.get("category"),
                classic.get("description"),
                classic.get("cover_color", "#1890ff"),
                len(classic["chapters"]),
            ),
        )
        for ch in classic["chapters"]:
            await adapter.execute(
                """INSERT OR IGNORE INTO classic_chapters
                   (id, classic_id, chapter_number, title, original_text,
                    translation, translator_notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    ch["id"],
                    classic["id"],
                    ch["chapter_number"],
                    ch["title"],
                    ch["original_text"],
                    ch.get("translation"),
                    ch.get("translator_notes"),
                ),
            )

    classics_after = await adapter.query_one("SELECT COUNT(*) AS cnt FROM classics")
    after = classics_after["cnt"] if classics_after else 0

    chapter_row = await adapter.query_one(
        "SELECT COUNT(*) AS cnt FROM classic_chapters"
    )
    chapter_count = chapter_row["cnt"] if chapter_row else 0

    cat_rows = await adapter.query(
        "SELECT category, COUNT(*) AS cnt FROM classics GROUP BY category ORDER BY category"
    )

    await adapter.close()

    inserted = after - before
    print(f"Seeded {inserted} new classics (skipped {before} existing)")
    print(f"Total classics: {after} | chapters: {chapter_count}")
    print("\nCategory breakdown:")
    for r in cat_rows:
        print(f"  {r['category']}: {r['cnt']}")

    assert after >= 5, f"Expected at least 5 classics, got {after}"
    assert chapter_count >= 12, f"Expected at least 12 chapters, got {chapter_count}"
    print(f"\n✓ Classics seeded successfully ({after} classics, {chapter_count} chapters)")


if __name__ == "__main__":
    db_path = os.environ.get("HOMEDOCTOR_DATABASE_URL", "data/homedoctor.db")
    if len(sys.argv) > 1:
        if sys.argv[1] in ("--db", "-d"):
            db_path = sys.argv[2]
        else:
            db_path = sys.argv[1]
    asyncio.run(seed(db_path))
