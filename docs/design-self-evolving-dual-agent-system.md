# 设计规格：自进化双Agent系统（知识Agent + 巡检Agent）

> 版本：v1.0
> 日期：2025-06-22
> 参考：/fighting Hermes Agent + hermes-tools.ts（14只读+4写工具）+ opencode-runner
> 核心理念：两个Agent持续对话、自我进化、积累经验、最终无需人类指导

---

## 1. 用户需求总结

### 1.1 核心愿景
两个Agent（知识Agent + 巡检Agent）具备：
- **自主性**：参考/fighting，有足够的原子工具自由组合
- **记忆**：独立记忆 + 共享记忆，能记住经验教训
- **自我进化**：审视自己的提示词和记忆，优化改进
- **举一反三**：解决一个问题→总结→解决一类问题
- **对话机制**：两个Agent相互交流，查漏补缺
- **UI可见**：每次知识处理后，展示提取/归类/推送的完整链路
- **人机交互**：用户可对处理结果给出意见，Agent对话完善，总结经验入记忆

### 1.2 功能需求
1. **知识Agent**：吸收知识时展示"分析思路+处理结果"，用户可继续对话指导
2. **巡检Agent**：定期巡检，与知识Agent对话讨论缺口
3. **Agent记忆**：
   - 独立记忆（各自的经验）
   - 共享记忆（公共知识、协作经验）
   - 记忆可被检索、更新、优化
4. **Agent对话**：
   - 开放式/反思类/探讨类话术模板
   - 目的：让系统越来越完善
5. **工具能力**：
   - 知识库检索（BM25+语义+图谱遍历）
   - Web搜索
   - 知识CRUD
   - 记忆读写
   - Agent间通信
   - 配套工具开发能力（Agent可以创建自己的辅助脚本）
6. **持续改进**：
   - 每次处理后总结经验
   - 记录"什么方法有效/无效"
   - 逐步减少人类干预
   - 最终两个Agent自主协作

### 1.3 约束
- **不授予代码修改权限**（不能改app源码）
- **允许开发配套工具**（完善自身能力的辅助脚本）
- **仅限中医/中国传统文化**（西医手工输入）

---

## 2. /fighting 参考分析

### 2.1 架构模式
```
/fighting Hermes Agent 架构：
  hermes-agent.ts (630行) — 编排层
    ├── buildHermesPrompt() — 构造系统提示（数据字典+规则+引用约定）
    ├── AgentRunner — 可替换的agent执行器
    └── 解析答案 + a2引用校验（防幻觉）

  hermes-tools.ts (1302行) — 14只读工具
    ├── list_node_types / describe_node_type — 元数据查询
    ├── count_nodes / query_nodes / get_node — 节点CRUD读
    ├── search_text — 全文搜索
    ├── traverse_graph — 图谱遍历
    ├── get_progress / get_audit — 历史/审计
    ├── aggregate / dashboard_metric — 统计聚合
    ├── recommend_helpers — 推荐算法
    └── welink_* (5个) — 外部消息源集成

  hermes-tools-write.ts (184行) — 4写工具
    ├── create_node / update_node — 节点创建/更新
    ├── add_progress — 追加进展
    └── delete_node — 删除（仅admin）

  opencode-runner.ts (129行) — opencode执行器
    └── 连接外部opencode server或进程内spawn
```

### 2.2 工具设计模式（关键学习点）
```typescript
// 每个工具的定义模式：
interface ToolDefinition<I, O> {
  name: string;                    // 工具名（LLM调用用）
  description: string;             // 人类语言描述（LLM prompt用）
  inputSchema: Record<string, unknown>;  // JSON Schema（参数校验）
  execute: (input: I, ctx: HermesToolCtx) => Promise<O>;  // 实现
}

// 安全特性：
// - _confirm: 'yes' 必须显式确认才执行写操作
// - 输出 >32KB 自动截断
// - 私单过滤（数据隔离）
// - 所有SQL参数化
```

### 2.3 性能模式
```
/fighting 性能策略：
  1. 只读工具直接调用后端API（HTTP，不走opencode）
  2. Agent只负责推理决策（通过opencode或直接API）
  3. 批量查询合并（避免N+1）
  4. 工具输出截断（32KB限制）
  5. 缓存（schema、节点列表等热数据）
```

---

## 3. 我们的Agent系统设计

### 3.1 双Agent架构

```
┌──────────────────────────────────────────────────────────┐
│                    Agent系统架构                           │
│                                                          │
│  ┌─────────────┐         对话          ┌──────────────┐  │
│  │  知识Agent   │ ←──────────────────→ │  巡检Agent    │  │
│  │ (Knowledge)  │                      │  (Patrol)    │  │
│  │              │                      │              │  │
│  │ 职责：        │                      │ 职责：        │  │
│  │ • 吸收知识    │                      │ • 定期巡检    │  │
│  │ • 提取归类    │                      │ • 发现缺口    │  │
│  │ • 评审入库    │                      │ • 搜索内容    │  │
│  │ • 展示结果    │                      │ • 喂链接      │  │
│  │ • 人机对话    │                      │ • 质量评估    │  │
│  └──────┬───────┘                      └──────┬───────┘  │
│         │                                     │          │
│         ▼                                     ▼          │
│  ┌────────────────────────────────────────────────────┐ │
│  │              工具层（原子工具）                       │ │
│  │                                                    │ │
│  │  知识工具 │ 检索工具 │ 记忆工具 │ 通信工具 │ 开发工具 │ │
│  └────────────────────────────────────────────────────┘ │
│         │                                               │
│         ▼                                               │
│  ┌────────────────────────────────────────────────────┐ │
│  │              记忆层                                 │ │
│  │                                                    │ │
│  │  知识Agent记忆 │ 巡检Agent记忆 │ 共享记忆            │ │
│  │  (经验/教训)   │ (巡检策略)   │ (协作经验/规则)     │ │
│  └────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

### 3.2 工具层设计（参考/fighting模式）

#### 3.2.1 知识工具（现有，复用）
| 工具 | 说明 | 来源 |
|------|------|------|
| `knowledge_create` | 创建知识实体 | tool_create_or_update_entity |
| `knowledge_merge` | 合并到已有实体 | tool_create_or_update_entity(duplicates) |
| `knowledge_search` | BM25+语义搜索 | search_pipeline.search() |
| `knowledge_graph` | 图谱遍历 | knowledge_reader.multi_hop_traverse |
| `knowledge_classify` | 动态分类 | category_classifier.classify_category |
| `knowledge_relate` | 自动关联 | tool_auto_relate |
| `knowledge_index` | 增量索引 | tool_build_index |
| `knowledge_review` | 多AI评审 | tool_multi_model_review |
| `knowledge_conflict` | 冲突检测 | tool_detect_conflicts |
| `knowledge_provenance` | 血缘记录 | tool_record_provenance |

#### 3.2.2 检索工具（参考/fighting hermes-tools.ts）
| 工具 | 说明 | /fighting对应 |
|------|------|---------------|
| `search_bm25` | 关键词搜索 | search_text |
| `search_semantic` | 语义向量搜索 | (新增) |
| `search_graph` | 图谱BFS遍历 | traverse_graph |
| `search_external` | 外部索引搜索 | (新增) |
| `search_web` | Web搜索 | (新增) |
| `query_entities` | 按类型/分类查询 | query_nodes |
| `get_entity` | 获取实体详情 | get_node |
| `get_relations` | 获取关系列表 | (新增) |
| `aggregate_stats` | 统计聚合 | aggregate |
| `get_provenance` | 查看血缘 | (新增) |

#### 3.2.3 记忆工具（全新，核心创新）
| 工具 | 说明 |
|------|------|
| `memory_save` | 保存经验/教训到记忆 |
| `memory_search` | 检索相关记忆（按场景/关键词） |
| `memory_update` | 更新已有记忆（自我修正） |
| `memory_reflect` | 反思总结（LLM审视记忆，发现改进点） |
| `memory_share` | 分享到共享记忆池 |
| `memory_consolidate` | 合并/精简相似记忆（防止膨胀） |

#### 3.2.4 通信工具（全新）
| 工具 | 说明 |
|------|------|
| `agent_message` | 向另一个Agent发送消息 |
| `agent_ask` | 向另一个Agent提问并等待回复 |
| `agent_propose` | 提出建议（如"建议巡检以下领域"） |
| `agent_debate` | 发起讨论（开放式/反思类话术模板） |
| `agent_review` | 审视另一个Agent的工作结果 |

#### 3.2.5 开发工具（受限，参考/fighting写工具模式）
| 工具 | 说明 | 安全 |
|------|------|------|
| `tool_create_script` | 创建辅助脚本（Python，沙箱执行） | _confirm + 限制路径 |
| `tool_run_script` | 运行已创建的辅助脚本 | 超时10s + 内存限制 |
| `tool_list_scripts` | 列出已创建的辅助脚本 | 只读 |
| `tool_optimize_prompt` | 优化自己的系统提示词 | 记录变更历史 |

### 3.3 记忆层设计

#### 3.3.1 数据模型
```sql
CREATE TABLE IF NOT EXISTS agent_memories (
    id TEXT PRIMARY KEY,
    agent_name TEXT NOT NULL,          -- 'knowledge_agent' / 'patrol_agent' / 'shared'
    memory_type TEXT NOT NULL,          -- 'experience'/'lesson'/'strategy'/'pattern'/'rule'
    content TEXT NOT NULL,              -- 记忆内容（自然语言）
    tags TEXT DEFAULT '[]',            -- 标签（JSON数组，用于检索）
    context TEXT DEFAULT '{}',          -- 场景上下文（JSON）
    confidence REAL DEFAULT 0.5,        -- 置信度（0-1，可被更新）
    times_used INTEGER DEFAULT 0,       -- 被引用次数
    success_count INTEGER DEFAULT 0,    -- 成功应用次数
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    superseded_by TEXT                  -- 被新记忆替代时的引用
);
CREATE INDEX IF NOT EXISTS idx_mem_agent ON agent_memories(agent_name);
CREATE INDEX IF NOT EXISTS idx_mem_type ON agent_memories(memory_type);
```

#### 3.3.2 记忆类型
| 类型 | 说明 | 示例 |
|------|------|------|
| `experience` | 成功经验 | "对'气功功法'类内容，先提取呼吸方法再提取步骤效果更好" |
| `lesson` | 失败教训 | "BM25模糊匹配会导致不同功法被错误合并，改用精确标题匹配" |
| `strategy` | 处理策略 | "用户导入的方剂类内容，优先检查组成药物的配伍禁忌" |
| `pattern` | 识别模式 | "文章中如果出现'第X步'，很可能是功法教程，按步骤提取" |
| `rule` | 规则 | "信任等级B的内容不进入安全引擎" |

#### 3.3.3 记忆生命周期
```
产生：Agent处理任务 → 发现值得记住的经验
    ↓
存储：memory_save(content, type, tags, context)
    ↓
使用：下次类似任务 → memory_search(场景) → 检索相关记忆 → 应用
    ↓
验证：应用后记录成功/失败 → 更新 success_count / confidence
    ↓
反思：memory_reflect() → LLM审视全部记忆 → 发现矛盾/过时/改进点
    ↓
合并：memory_consolidate() → 合并相似记忆，淘汰低置信度记忆
    ↓
共享：memory_share() → 高价值记忆推到共享池
```

### 3.4 对话机制设计

#### 3.4.1 对话模板
```python
DIALOGUE_TEMPLATES = {
    "open_ended": [
        "最近我在处理{domain}的知识时发现了{finding}，你觉得这个方向值得深入吗？",
        "我对{entity}的处理方式是{approach}，你有什么改进建议？",
        "我注意到{pattern}，这可能是系统的一个改进点。",
    ],
    "reflective": [
        "上次我们用{method}处理{problem}，结果{outcome}。反思一下，哪里做得好？哪里可以改进？",
        "我对{decision}不太确定，你能从你的角度分析一下利弊吗？",
        "过去一周的经验中，哪条记忆你觉得最有价值？为什么？",
    ],
    "exploratory": [
        "知识库的{area}似乎还有缺口，你觉得我们应该主动搜索补充吗？",
        "如果用户导入的内容质量参差不齐，我们该如何优化筛选策略？",
        "我们的信任评审机制有没有可能被绕过？一起分析一下安全边界。",
    ],
    "gap_filling": [
        "我巡检发现{entity_type}中缺少{field}的实体有{count}个，需要补全。",
        "用户最近频繁搜索'{keyword}'但找不到结果，我来搜索一下相关内容。",
        "知识图谱中{entity_a}和{entity_b}之间缺少关联，需要建立关系。",
    ],
}
```

#### 3.4.2 对话流程
```
巡检Agent发现缺口
    ↓ agent_message → 知识Agent
"我发现3个穴位缺少'needling'字段，是否需要搜索补全？"
    ↓ agent_ask ← 知识Agent
"是的，优先补全足三里、合谷、内关（搜索量最高的3个）"
    ↓ 巡检Agent
    ├── search_web("穴位 足三里 刺法")
    ├── agent_message → 知识Agent: "找到3篇文章，URL如下"
    ↓ 知识Agent
    ├── process_input(url1) → 提取 → 评审 → 入库
    ├── process_input(url2) → 提取 → 评审 → 入库
    ├── process_input(url3) → 提取 → 评审 → 入库
    ↓ agent_message → 巡检Agent
"3个穴位的刺法已补全。其中足三里的刺法有2个来源不一致，已记录冲突。"
    ↓ 巡检Agent
    └── memory_save(type='experience', content="穴位刺法补全策略：优先搜索量最高的")
```

### 3.5 UI交互设计

#### 3.5.1 知识处理结果展示
```
┌─────────────────────────────────────────────────────────┐
│  📋 知识处理报告                                          │
│  ─────────────────────────────────────────────────────  │
│  输入：「李少波真气运行法」文章                            │
│                                                         │
│  🔍 分析思路：                                            │
│  1. 识别类型 → health_practice（养生功法）                 │
│  2. 动态分类 → 新建分类「气功功法」（与打坐/站桩并列）       │
│  3. 结构化提取 → 5步功法 + 呼吸方法 + 适应症 + 禁忌       │
│  4. 去重检查 → 无重复（精确标题匹配）                      │
│  5. 多AI评审 → 3模型通过，评分82.3，A级                   │
│  6. 自动关联 → 关联到「打坐」「站桩」「气功」               │
│                                                         │
│  📦 提取内容：                                            │
│  • 归类到：养生功法 > 气功功法                              │
│  • 摘要：李少波创编的五步真气运行法...                      │
│  • 新增字段：breathing/mental_focus/steps/indications     │
│  • 入库位置：knowledge_entities (id: ke-xxx)              │
│  • 外部索引：原文已分块索引（5 chunks）                     │
│                                                         │
│  📤 推送到的模块：                                        │
│  • 功法页面（practice_page）— 原因：同类功法               │
│  • 体质推荐（constitution_engine）— 原因：适合气虚质       │
│                                                         │
│  🔗 建立的关联：                                          │
│  • 真气运行法 →[related_to]→ 打坐（相似度0.72）           │
│  • 真气运行法 →[related_to]→ 站桩（相似度0.65）           │
│                                                         │
│  💬 你有什么意见？                                        │
│  [输入反馈...]                              [发送给Agent] │
│                                                         │
│  📝 Agent记忆更新：                                       │
│  • 新经验：「气功功法类内容，步骤提取效果好」               │
│  • 已记忆，下次处理类似内容会优先用这个策略                 │
└─────────────────────────────────────────────────────────┘
```

#### 3.5.2 Agent对话面板
```
┌─────────────── Agent对话 ──────────────────┐
│                                            │
│  🔵 巡检Agent: 我发现3个功法缺少呼吸方法     │
│  🔴 知识Agent: 优先补全搜索量最高的八段锦     │
│  🔵 巡检Agent: 搜索到2篇文章，URL如下...     │
│  🔴 知识Agent: 已处理，2个补全，1个有冲突     │
│  🔵 巡检Agent: 记住这个策略，下次复用         │
│                                            │
│  [查看完整对话] [加入讨论] [查看记忆]        │
└────────────────────────────────────────────┘
```

---

## 4. 数据库变更

```sql
-- Agent记忆表
CREATE TABLE IF NOT EXISTS agent_memories (
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
);

-- Agent对话表
CREATE TABLE IF NOT EXISTS agent_conversations (
    id TEXT PRIMARY KEY,
    from_agent TEXT NOT NULL,
    to_agent TEXT NOT NULL,
    message_type TEXT NOT NULL,  -- 'message'/'ask'/'propose'/'debate'/'review'
    content TEXT NOT NULL,
    reply_to TEXT,               -- 引用的上一条消息ID
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Agent创建的辅助工具
CREATE TABLE IF NOT EXISTS agent_tools (
    id TEXT PRIMARY KEY,
    agent_name TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    description TEXT,
    script_path TEXT NOT NULL,
    parameters TEXT DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_used TEXT,
    usage_count INTEGER DEFAULT 0
);

-- Agent提示词优化历史
CREATE TABLE IF NOT EXISTS agent_prompt_history (
    id TEXT PRIMARY KEY,
    agent_name TEXT NOT NULL,
    version INTEGER NOT NULL,
    prompt TEXT NOT NULL,
    change_reason TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

---

## 5. 原子工具完整清单（参考/fighting模式）

### 5.1 知识工具组（10个）
1. `knowledge_create` — 创建实体
2. `knowledge_merge` — 合并实体
3. `knowledge_search` — BM25+语义搜索
4. `knowledge_graph` — 图谱遍历
5. `knowledge_classify` — 动态分类
6. `knowledge_relate` — 自动关联
7. `knowledge_index` — 增量索引
8. `knowledge_review` — 多AI评审
9. `knowledge_conflict` — 冲突检测
10. `knowledge_provenance` — 血缘记录

### 5.2 检索工具组（10个）
11. `search_bm25` — 关键词搜索
12. `search_semantic` — 语义搜索
13. `search_graph` — 图谱BFS
14. `search_external` — 外部索引
15. `search_web` — Web搜索
16. `query_entities` — 按类型查询
17. `get_entity` — 实体详情
18. `get_relations` — 关系列表
19. `aggregate_stats` — 统计聚合
20. `get_provenance` — 血缘查询

### 5.3 记忆工具组（6个）
21. `memory_save` — 保存记忆
22. `memory_search` — 检索记忆
23. `memory_update` — 更新记忆
24. `memory_reflect` — 反思总结
25. `memory_share` — 分享记忆
26. `memory_consolidate` — 合并精简

### 5.4 通信工具组（5个）
27. `agent_message` — 发送消息
28. `agent_ask` — 提问等待回复
29. `agent_propose` — 提出建议
30. `agent_debate` — 发起讨论
31. `agent_review` — 审视结果

### 5.5 开发工具组（4个）
32. `tool_create_script` — 创建辅助脚本
33. `tool_run_script` — 运行脚本
34. `tool_list_scripts` — 列出脚本
35. `tool_optimize_prompt` — 优化提示词

**总计：35个原子工具**，参考/fighting的14只读+4写=18个工具，我们的系统更复杂需要更多。

---

## 6. 自我进化机制

### 6.1 进化循环
```
处理任务 → 记录结果 → 反思总结 → 发现改进 → 更新记忆 → 优化提示词 → 下次更好
    ↑                                                              │
    └──────────────────────────────────────────────────────────────┘
```

### 6.2 提示词自我优化
```python
async def self_optimize_prompt(agent_name: str):
    """Agent审视自己的提示词+记忆，提出优化建议。"""
    memories = await memory_search(agent_name, type='lesson', min_confidence=0.7)
    current_prompt = await get_current_prompt(agent_name)

    prompt = f"""你是{agent_name}。请审视你的系统提示词和最近的教训记忆，提出优化建议。

当前提示词：
{current_prompt}

最近的教训（高置信度）：
{format_memories(memories)}

请分析：
1. 哪些教训应该融入提示词？
2. 提示词中哪些规则可以被简化或删除？
3. 是否有新的规则应该添加？

返回JSON：{{"additions": [...], "deletions": [...], "modifications": [...]}}
"""
    suggestions = await llm_chat(prompt)
    # 记录变更历史，不自动应用，需要确认
    await save_prompt_history(agent_name, suggestions)
```

### 6.3 举一反三
```python
async def generalize_experience(agent_name: str, specific_case: dict):
    """从一个具体案例中提取通用模式。"""
    prompt = f"""从以下具体处理案例中，提取通用规则：

案例：{json.dumps(specific_case, ensure_ascii=False)}

请提取：
1. 这属于哪类问题？（分类）
2. 适用的通用解决方案是什么？（模式）
3. 下次遇到类似问题应该怎么做？（策略）

返回JSON：{{"problem_type": "...", "pattern": "...", "strategy": "..."}}
"""
    result = await llm_chat(prompt)
    await memory_save(agent_name, type='pattern', content=result)
```

---

## 7. 实施计划

| 阶段 | 内容 | 工作量 |
|------|------|--------|
| **Phase 1** | 记忆系统（agent_memories + 6工具） | 2天 |
| **Phase 2** | 工具层统一（35工具注册+Schema定义） | 3天 |
| **Phase 3** | Agent对话机制（5通信工具+模板） | 2天 |
| **Phase 4** | UI交互（处理结果展示+对话面板+人机交互） | 3天 |
| **Phase 5** | 自我进化（反思+举一反三+提示词优化） | 2天 |
| **Phase 6** | 开发工具（受限脚本创建+沙箱执行） | 1天 |
| **总计** | | **13天** |

---

## 8. 检查清单

### 记忆系统
- [ ] agent_memories 表
- [ ] 6个记忆工具（save/search/update/reflect/share/consolidate）
- [ ] 独立记忆 + 共享记忆
- [ ] 记忆生命周期（产生→使用→验证→反思→合并→共享）

### 工具层
- [ ] 35个原子工具统一注册
- [ ] JSON Schema 定义（参考/fighting inputSchema模式）
- [ ] _confirm 安全机制（写操作需确认）
- [ ] 输出截断（32KB限制）

### 对话机制
- [ ] agent_conversations 表
- [ ] 5个通信工具
- [ ] 4类对话模板（开放式/反思/探讨/查漏补缺）
- [ ] 巡检Agent↔知识Agent 对话流程

### UI交互
- [ ] 知识处理结果展示（分析思路+提取内容+推送+关联+记忆更新）
- [ ] Agent对话面板
- [ ] 人机交互（用户反馈→Agent对话→完善→记忆）
- [ ] 继续对话能力

### 自我进化
- [ ] memory_reflect（反思总结）
- [ ] 提示词自我优化（记录历史，需确认）
- [ ] 举一反三（具体案例→通用模式）
- [ ] 经验积累（success_count/confidence 追踪）

### 安全
- [ ] 不授予代码修改权限
- [ ] 辅助脚本沙箱执行（超时+内存限制+路径限制）
- [ ] 记忆可信度验证（防止错误记忆传播）
- [ ] 仅限中医/中国传统文化
