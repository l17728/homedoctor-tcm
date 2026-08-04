"""Database schema — DDL statements, FTS indexes, and triggers."""

from __future__ import annotations


import logging

logger = logging.getLogger(__name__)
__all__ = ["DDL_STATEMENTS", "FTS_STATEMENTS", "FTS_TRIGGERS"]

DDL_STATEMENTS = [
    # -- 用户与家庭
    """CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        display_name TEXT,
        family_id TEXT,
        settings TEXT DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS families (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        owner_id TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS family_members (
        id TEXT PRIMARY KEY,
        family_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        name TEXT,
        relation TEXT,
        gender TEXT,
        constitution_type TEXT,
        constitution_sub TEXT,
        health_profile TEXT DEFAULT '{}',
        is_pregnant INTEGER DEFAULT 0,
        date_of_birth TEXT,
        weight_kg REAL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    # -- 中药方剂知识
    """CREATE TABLE IF NOT EXISTS herbs (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        aliases TEXT,
        nature TEXT,
        flavor TEXT,
        meridians TEXT,
        efficacy TEXT,
        indications TEXT,
        contraindications TEXT,
        dosage_min_g REAL,
        dosage_max_g REAL,
        toxicity TEXT,
        category TEXT,
        processing_method TEXT,
        origin TEXT,
        source_ref TEXT,
        properties TEXT DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS formulas (
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
    )""",
    # -- 家庭药箱
    """CREATE TABLE IF NOT EXISTS medicines (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        family_member_id TEXT,
        name TEXT NOT NULL,
        brand TEXT,
        type TEXT NOT NULL,
        specification TEXT,
        unit TEXT,
        quantity INTEGER DEFAULT 0,
        production_date TEXT,
        expiry_date TEXT,
        opened_date TEXT,
        shelf_life_after_open TEXT,
        dosage_instructions TEXT,
        contraindications TEXT,
        barcode TEXT,
        drug_class TEXT,
        active_ingredients TEXT DEFAULT '[]',
        herbal_fields TEXT DEFAULT '{}',
        batches TEXT DEFAULT '[]',
        photos TEXT DEFAULT '[]',
        properties TEXT DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    # -- AI对话
    """CREATE TABLE IF NOT EXISTS conversations (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        title TEXT,
        model_id TEXT,
        messages TEXT DEFAULT '[]',
        reasoning_trace TEXT DEFAULT '[]',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    # -- 知识收藏
    """CREATE TABLE IF NOT EXISTS knowledge_entries (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        entry_type TEXT NOT NULL,
        title TEXT,
        content TEXT,
        summary TEXT,
        tags TEXT DEFAULT '[]',
        category_path TEXT,
        source_type TEXT,
        source_url TEXT,
        is_starred INTEGER DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    # -- 安全规则
    """CREATE TABLE IF NOT EXISTS safety_rules (
        id TEXT PRIMARY KEY,
        rule_type TEXT NOT NULL,
        drug_a TEXT NOT NULL,
        drug_b TEXT,
        severity TEXT NOT NULL DEFAULT 'warning',
        mechanism TEXT,
        action TEXT,
        source TEXT,
        enabled INTEGER DEFAULT 1
    )""",
    # -- 用药打卡
    """CREATE TABLE IF NOT EXISTS medication_logs (
        id TEXT PRIMARY KEY,
        family_member_id TEXT NOT NULL,
        date TEXT NOT NULL,
        medicine_id TEXT NOT NULL,
        taken INTEGER DEFAULT 1,
        skipped_reason TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    # -- 体质自测评估记录 (spec §2.3 / §4.2)
    """CREATE TABLE IF NOT EXISTS constitution_assessments (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        assessed_at TEXT NOT NULL DEFAULT (datetime('now')),
        results TEXT NOT NULL DEFAULT '{}',
        primary_type TEXT NOT NULL,
        secondary_types TEXT DEFAULT '[]',
        raw_answers TEXT NOT NULL DEFAULT '{}',
        FOREIGN KEY (user_id) REFERENCES users(id)
    )""",
    # -- 用户体质档案 (spec §4.2)
    """CREATE TABLE IF NOT EXISTS user_profiles (
        user_id TEXT PRIMARY KEY,
        display_name TEXT,
        birth_year INTEGER,
        gender TEXT,
        height_cm REAL,
        weight_kg REAL,
        constitution_type TEXT,
        constitution_secondary TEXT DEFAULT '[]',
        allergies TEXT DEFAULT '[]',
        health_conditions TEXT DEFAULT '[]',
        is_pregnant INTEGER DEFAULT 0,
        liver_disease INTEGER DEFAULT 0,
        kidney_disease INTEGER DEFAULT 0,
        blood_type TEXT,
        notes TEXT,
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    )""",
    # -- 吃药提醒 (spec §20)
    """CREATE TABLE IF NOT EXISTS reminders (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        family_member_id TEXT,
        title TEXT NOT NULL,
        herb_name TEXT,
        formula_name TEXT,
        medicine_name TEXT,
        dosage TEXT,
        frequency TEXT NOT NULL DEFAULT 'daily',
        times TEXT NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT,
        notes TEXT,
        enabled INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    )""",
    """CREATE TABLE IF NOT EXISTS audit_log (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        user_id TEXT,
        action TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_id TEXT,
        changes TEXT,
        prev_hash TEXT,
        hash TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS favorites (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        entry_type TEXT NOT NULL,
        entry_id TEXT,
        title TEXT,
        content TEXT,
        tags TEXT DEFAULT '[]',
        source_type TEXT,
        is_starred INTEGER DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    # -- 外治理疗知识库 (spec §9.6 / §10.6.1)
    """CREATE TABLE IF NOT EXISTS therapies (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        risk_level TEXT NOT NULL DEFAULT 'medium',
        home_use_safe INTEGER NOT NULL DEFAULT 0,
        display_only INTEGER NOT NULL DEFAULT 0,
        description TEXT,
        indications TEXT,
        contraindications TEXT,
        operation_steps TEXT,
        duration TEXT,
        frequency TEXT,
        precautions TEXT,
        properties TEXT DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    # -- 疗法穴位关联 (spec §9.6.4)
    """CREATE TABLE IF NOT EXISTS therapy_acupoints (
        id TEXT PRIMARY KEY,
        therapy_id TEXT NOT NULL,
        acupoint_name TEXT NOT NULL,
        location TEXT,
        function TEXT,
        meridian TEXT,
        is_primary INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (therapy_id) REFERENCES therapies(id)
    )""",
    # -- 疗法专用安全规则 (spec §9.6.6)
    """CREATE TABLE IF NOT EXISTS therapy_safety_rules (
        id TEXT PRIMARY KEY,
        therapy_category TEXT,
        rule_type TEXT NOT NULL,
        condition_text TEXT NOT NULL,
        action TEXT NOT NULL,
        severity TEXT NOT NULL DEFAULT 'warning',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    # -- 用药套餐 (spec §20.5) — groups multiple medicines into a shared-schedule plan
    """CREATE TABLE IF NOT EXISTS medication_plans (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        family_member_id TEXT,
        name TEXT NOT NULL,
        description TEXT,
        status TEXT DEFAULT 'active',
        start_date TEXT,
        end_date TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    )""",
    """CREATE TABLE IF NOT EXISTS plan_items (
        id TEXT PRIMARY KEY,
        plan_id TEXT NOT NULL,
        medicine_name TEXT NOT NULL,
        dosage TEXT,
        frequency TEXT,
        times TEXT,
        notes TEXT,
        sort_order INTEGER DEFAULT 0,
        reminder_id TEXT,
        FOREIGN KEY (plan_id) REFERENCES medication_plans(id)
    )""",
    # -- 子女远程协助：家庭数据共享 (spec §22)
    """CREATE TABLE IF NOT EXISTS family_shares (
        id TEXT PRIMARY KEY,
        sharer_id TEXT NOT NULL,
        viewer_id TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT '家属查看',
        status TEXT NOT NULL DEFAULT 'active',
        alert_config TEXT DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(sharer_id, viewer_id)
    )""",
    # -- 知识图谱：节点与边 (spec §9/§13.3 V3)
    # 结构化数据是权威来源；图谱从 herbs/formulas/therapies/safety_rules 派生重建。
    """CREATE TABLE IF NOT EXISTS graph_nodes (
        id TEXT PRIMARY KEY,
        node_type TEXT NOT NULL,
        label TEXT NOT NULL,
        properties TEXT DEFAULT '{}',
        search_text TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS graph_edges (
        id TEXT PRIMARY KEY,
        edge_type TEXT NOT NULL,
        source_id TEXT NOT NULL,
        target_id TEXT NOT NULL,
        properties TEXT DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_graph_nodes_type ON graph_nodes(node_type)",
    "CREATE INDEX IF NOT EXISTS idx_graph_edges_source ON graph_edges(source_id)",
    "CREATE INDEX IF NOT EXISTS idx_graph_edges_target ON graph_edges(target_id)",
    "CREATE INDEX IF NOT EXISTS idx_graph_edges_type ON graph_edges(edge_type)",
    # -- 经典读诵：中医典籍书架 (spec §7.x 经典读诵)
    """CREATE TABLE IF NOT EXISTS classics (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        author TEXT,
        dynasty TEXT,
        category TEXT,
        description TEXT,
        cover_color TEXT DEFAULT '#1890ff',
        total_chapters INTEGER DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS classic_chapters (
        id TEXT PRIMARY KEY,
        classic_id TEXT NOT NULL,
        chapter_number INTEGER NOT NULL,
        title TEXT NOT NULL,
        original_text TEXT NOT NULL,
        translation TEXT,
        translator_notes TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (classic_id) REFERENCES classics(id)
    )""",
    """CREATE TABLE IF NOT EXISTS classic_annotations (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        classic_id TEXT NOT NULL,
        chapter_id TEXT NOT NULL,
        start_offset INTEGER NOT NULL,
        end_offset INTEGER NOT NULL,
        selected_text TEXT NOT NULL,
        note_type TEXT NOT NULL DEFAULT 'annotation',
        content TEXT NOT NULL,
        ai_model TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        FOREIGN KEY (chapter_id) REFERENCES classic_chapters(id)
    )""",
    """CREATE TABLE IF NOT EXISTS classic_study_notes (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        classic_id TEXT NOT NULL,
        chapter_id TEXT,
        content TEXT DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_classic_chapters_classic ON classic_chapters(classic_id)",
    "CREATE INDEX IF NOT EXISTS idx_classic_annotations_user_chapter ON classic_annotations(user_id, chapter_id)",
    "CREATE INDEX IF NOT EXISTS idx_classic_study_notes_user_classic ON classic_study_notes(user_id, classic_id)",
    # -- 健康分享卡 & 月度家庭健康报告 (spec §13.3 V3)
    # 结构化数据是权威来源；分享卡为派生视图，持久化以便列表/删除/回顾。
    """CREATE TABLE IF NOT EXISTS share_cards (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        family_id TEXT NOT NULL,
        member_id TEXT,
        card_type TEXT NOT NULL,
        card_data TEXT NOT NULL DEFAULT '{}',
        month TEXT,
        is_monthly_report INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_share_cards_user ON share_cards(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_share_cards_family ON share_cards(family_id)",
    "CREATE INDEX IF NOT EXISTS idx_share_cards_monthly ON share_cards(is_monthly_report, month)",
    # -- 每日健康打卡 (血压/血糖/体重/睡眠/心情)
    """CREATE TABLE IF NOT EXISTS health_logs (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        family_member_id TEXT,
        log_date TEXT NOT NULL,
        systolic INTEGER,
        diastolic INTEGER,
        blood_sugar REAL,
        weight REAL,
        sleep_hours REAL,
        mood TEXT,
        notes TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_health_logs_user_date ON health_logs(user_id, log_date)",
    # -- 诊疗时间线 (spec §13.2 V2 — 诊疗记录)
    """CREATE TABLE IF NOT EXISTS medical_visits (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        family_member_id TEXT,
        visit_date TEXT NOT NULL,
        hospital TEXT,
        department TEXT,
        doctor_name TEXT,
        diagnosis TEXT,
        tcm_diagnosis TEXT,
        prescription TEXT,
        lab_results TEXT,
        notes TEXT,
        attachments TEXT DEFAULT '[]',
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_visits_user_date ON medical_visits(user_id, visit_date)",
    # -- AI模型注册表 (可配置的多模型管理)
    """CREATE TABLE IF NOT EXISTS ai_models (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        provider TEXT NOT NULL,
        model_id TEXT NOT NULL,
        api_endpoint TEXT,
        api_key TEXT,
        access_type TEXT DEFAULT 'api',
        capabilities TEXT DEFAULT '["text"]',
        max_tokens INTEGER DEFAULT 4096,
        temperature REAL DEFAULT 0.3,
        enabled INTEGER DEFAULT 1,
        is_default INTEGER DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    # -- Agent处理日志 (自主知识抽取审计)
    """CREATE TABLE IF NOT EXISTS agent_logs (
        id TEXT PRIMARY KEY,
        action_type TEXT NOT NULL,
        source_type TEXT,
        source_ref TEXT,
        entity_id TEXT,
        details TEXT DEFAULT '{}',
        decision TEXT,
        user_reviewed INTEGER DEFAULT 0,
        user_action TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_agent_logs_entity ON agent_logs(entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_agent_logs_created ON agent_logs(created_at DESC)",
    # -- 统一知识实体注册表 (spec §9 — 统一知识实体系统)
    # 结构化数据是权威来源；本表为跨类型实体统一注册（中药/方剂/理疗/症状/文章/茶饮等）
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
    "CREATE INDEX IF NOT EXISTS idx_ke_status ON knowledge_entities(status)",
    # -- 实体关系引擎 — entity_relationships
    # 取代 graph_edges 成为权威关系存储；图谱可从此派生重建
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
    # -- RAG 知识分块 (spec §RAG — 语义检索)
    # 结构化实体(knowledge_entities)被切分为语义块后嵌入向量，用于混合检索。
    # source_type: 'internal'=知识库内容, 'external'=外部链接原文索引
    # source_url: 外部链接时指向原文URL（内部知识为NULL）
    """CREATE TABLE IF NOT EXISTS knowledge_chunks (
        id TEXT PRIMARY KEY,
        entity_id TEXT,
        chunk_index INTEGER DEFAULT 0,
        chunk_text TEXT NOT NULL,
        chunk_type TEXT DEFAULT 'content',
        hierarchy_path TEXT,
        hierarchy_level INTEGER DEFAULT 0,
        token_count INTEGER DEFAULT 0,
        metadata TEXT DEFAULT '{}',
        source_url TEXT,
        source_type TEXT DEFAULT 'internal',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_kc_entity ON knowledge_chunks(entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_kc_source_type ON knowledge_chunks(source_type)",
    # -- RAG 向量嵌入存储 (spec §RAG — BGE-M3 1024维)
    # 嵌入以 JSON 字符串存储；检索时加载到内存做 numpy 余弦相似度。
    """CREATE TABLE IF NOT EXISTS chunk_embeddings (
        chunk_id TEXT PRIMARY KEY,
        embedding TEXT NOT NULL,
        model_name TEXT DEFAULT 'bge-m3',
        dim INTEGER DEFAULT 1024,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    # -- 知识血缘表 (trust hierarchy + provenance)
    """CREATE TABLE IF NOT EXISTS knowledge_provenance (
        id TEXT PRIMARY KEY,
        entity_id TEXT NOT NULL,
        source_type TEXT NOT NULL,
        source_url TEXT,
        source_title TEXT,
        source_domain TEXT,
        trust_level TEXT DEFAULT 'C',
        trust_score REAL DEFAULT 0,
        review_details TEXT DEFAULT '{}',
        content_date TEXT,
        freshness_status TEXT DEFAULT 'current',
        imported_by TEXT,
        imported_at TEXT NOT NULL DEFAULT (datetime('now')),
        verified_by TEXT,
        verified_at TEXT,
        FOREIGN KEY (entity_id) REFERENCES knowledge_entities(id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_prov_entity ON knowledge_provenance(entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_prov_trust ON knowledge_provenance(trust_level)",
    # -- 知识冲突记录
    """CREATE TABLE IF NOT EXISTS knowledge_conflicts (
        id TEXT PRIMARY KEY,
        entity_id TEXT NOT NULL,
        field TEXT NOT NULL,
        conflict_type TEXT NOT NULL,
        existing_value TEXT,
        incoming_value TEXT,
        resolution TEXT,
        resolved INTEGER DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_conf_entity ON knowledge_conflicts(entity_id)",
    # -- 删除推荐豁免
    """CREATE TABLE IF NOT EXISTS deletion_exemptions (
        id TEXT PRIMARY KEY,
        target_type TEXT NOT NULL,
        target_id TEXT NOT NULL,
        exempted_by TEXT NOT NULL,
        exempt_reason TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(target_type, target_id)
    )""",
    # -- 知识质量反馈
    """CREATE TABLE IF NOT EXISTS knowledge_feedback (
        id TEXT PRIMARY KEY,
        entity_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        rating TEXT NOT NULL,
        comment TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(entity_id, user_id)
    )""",
    # -- 用户兴趣画像
    """CREATE TABLE IF NOT EXISTS user_interest_profiles (
        user_id TEXT NOT NULL,
        interest_domain TEXT NOT NULL,
        search_count INTEGER DEFAULT 0,
        last_searched TEXT,
        PRIMARY KEY (user_id, interest_domain)
    )""",
    """CREATE TABLE IF NOT EXISTS user_notes (
        id TEXT PRIMARY KEY,
        entity_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(entity_id, user_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_notes_entity ON user_notes(entity_id)",
    """CREATE TABLE IF NOT EXISTS agent_memories (
        id TEXT PRIMARY KEY,
        agent_name TEXT NOT NULL,
        memory_type TEXT NOT NULL,
        content TEXT NOT NULL,
        tags TEXT DEFAULT '[]',
        context TEXT DEFAULT '{}',
        confidence REAL DEFAULT 0.5,
        times_used INTEGER DEFAULT 0,
        success_count INTEGER DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        superseded_by TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_mem_agent ON agent_memories(agent_name)",
    "CREATE INDEX IF NOT EXISTS idx_mem_type ON agent_memories(memory_type)",
    """CREATE TABLE IF NOT EXISTS agent_conversations (
        id TEXT PRIMARY KEY,
        from_agent TEXT NOT NULL,
        to_agent TEXT NOT NULL,
        message_type TEXT NOT NULL,
        content TEXT NOT NULL,
        reply_to TEXT,
        metadata TEXT DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_conv_created ON agent_conversations(created_at DESC)",
    """CREATE TABLE IF NOT EXISTS agent_configs (
        agent_name TEXT NOT NULL,
        config_key TEXT NOT NULL,
        config_value TEXT NOT NULL,
        updated_at TEXT DEFAULT (datetime('now')),
        PRIMARY KEY (agent_name, config_key)
    )""",
]


FTS_STATEMENTS = [
    """CREATE VIRTUAL TABLE IF NOT EXISTS herbs_fts USING fts5(
        name, aliases, efficacy, indications, category,
        content=herbs, content_rowid=rowid
    )""",
    """CREATE VIRTUAL TABLE IF NOT EXISTS formulas_fts USING fts5(
        name, source, efficacy, indications, category,
        content=formulas, content_rowid=rowid
    )""",
    """CREATE VIRTUAL TABLE IF NOT EXISTS therapies_fts USING fts5(
        name, category, description, indications, contraindications,
        content=therapies, content_rowid=rowid
    )""",
]

# Module-level DB adapter reference — set by main.py during startup


FTS_TRIGGERS = [
    """CREATE TRIGGER IF NOT EXISTS herbs_ai AFTER INSERT ON herbs BEGIN
        INSERT INTO herbs_fts(rowid, name, aliases, efficacy, indications, category)
        VALUES (new.rowid, new.name, new.aliases, new.efficacy, new.indications, new.category);
    END""",
    """CREATE TRIGGER IF NOT EXISTS herbs_ad AFTER DELETE ON herbs BEGIN
        INSERT INTO herbs_fts(herbs_fts, rowid, name, aliases, efficacy, indications, category)
        VALUES ('delete', old.rowid, old.name, old.aliases, old.efficacy, old.indications, old.category);
    END""",
    """CREATE TRIGGER IF NOT EXISTS formulas_ai AFTER INSERT ON formulas BEGIN
        INSERT INTO formulas_fts(rowid, name, source, efficacy, indications, category)
        VALUES (new.rowid, new.name, new.source, new.efficacy, new.indications, new.category);
    END""",
    """CREATE TRIGGER IF NOT EXISTS formulas_ad AFTER DELETE ON formulas BEGIN
        INSERT INTO formulas_fts(formulas_fts, rowid, name, source, efficacy, indications, category)
        VALUES ('delete', old.rowid, old.name, old.source, old.efficacy, old.indications, old.category);
    END""",
    """CREATE TRIGGER IF NOT EXISTS therapies_ai AFTER INSERT ON therapies BEGIN
        INSERT INTO therapies_fts(rowid, name, category, description, indications, contraindications)
        VALUES (new.rowid, new.name, new.category, new.description, new.indications, new.contraindications);
    END""",
    """CREATE TRIGGER IF NOT EXISTS therapies_ad AFTER DELETE ON therapies BEGIN
        INSERT INTO therapies_fts(therapies_fts, rowid, name, category, description, indications, contraindications)
        VALUES ('delete', old.rowid, old.name, old.category, old.description, old.indications, old.contraindications);
    END""",
]