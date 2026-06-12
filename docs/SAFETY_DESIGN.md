# Safety Design — 五层用药安全引擎

> Spec §15 (用药安全体系) + §24 (中西药交互安全强化)
> 设计原则：硬编码规则优先于 AI，安全层在 AI 层之前运行。

## 架构总览

```
用户请求（herbs + medicines + user_profile）
         │
         ▼
┌──────────────────────────────────────────────┐
│ 第1a层：中药×中药配伍禁忌（硬编码 DB）          │
│ 十八反 + 十九畏                                │
│ → critical 级别拦截，不经过 AI                  │
└──────────────────┬───────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────┐
│ 第1b层：中西药交互检查（硬编码 DB）              │
│ R-01 ~ R-10，drugClass 匹配                    │
│ → critical / high 级别拦截                     │
└──────────────────┬───────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────┐
│ 第2层：剂量范围检查                              │
│ herbs 表 dosage_min_g / dosage_max_g           │
│ → medium 级别提示                              │
└──────────────────┬───────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────┐
│ 第3层：特殊人群检查                              │
│ 孕妇 / 儿童<3岁(BLOCK) / 儿童3-14 / 老年65+    │
│ → critical (BLOCK) / medium                   │
└──────────────────┬───────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────┐
│ 第4层：AI 辅助分析（MVP placeholder）           │
│ → 返回结构化提示词供未来 AI 使用                 │
└──────────────────┬───────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────┐
│ 第5层：免责声明（始终附加）                      │
│ → 所有结果都附带医疗免责声明                     │
└──────────────────────────────────────────────┘
```

## 数据模型

### SafetyCheckResult

```python
class SafetyCheckResult:
    safe: bool                    # True = 无 critical/high 警告
    warnings: list[SafetyWarning]  # 所有层级的警告列表
    disclaimer: str               # 第5层免责声明
    checked_herbs: list[str]
    checked_medicines: list[str]
```

### SafetyWarning

```python
class SafetyWarning:
    layer: int          # 1-5
    severity: str       # "critical" | "high" | "medium" | "low"
    title: str          # 警告标题
    detail: str         # 详细说明
    herbs: list[str]    # 涉及的中药
    action: str         # "禁止" | "谨慎" | "告知医生"
    source: str         # 规则来源（如 "十八反"、"R-01"）
```

## 第1a层：中药配伍禁忌

### 数据来源
- DB `safety_rules` 表，`rule_type = '配伍禁忌'`
- 初始化时由 `database.py` 的 `seed_safety_rules()` 硬编码写入
- 字段：`drug_a`, `drug_b`, `severity`, `description`, `source`

### 十八反（3 组 × 10 对）

| 来源 | 禁忌组合 |
|------|---------|
| 乌头反 | 附子/川乌/草乌 × 半夏/瓜蒌/贝母/白蔹/白及 |
| 藜芦反 | 藜芦 × 人参/沙参/丹参/玄参/苦参/细辛/芍药 |
| 甘草反 | 甘草 × 甘遂/大戟/芫花/海藻 |

### 十九畏（9 对）

| 组合 | 说明 |
|------|------|
| 硫磺 × 朴硝 | 禁止同用 |
| 水银 × 砒霜 | 禁止同用 |
| 狼毒 × 密陀僧 | 禁止同用 |
| 巴豆 × 牵牛 | 禁止同用 |
| 丁香 × 郁金 | 禁止同用 |
| 川乌/草乌 × 犀角 | 禁止同用 |
| 牙硝 × 三棱 | 禁止同用 |
| 官桂 × 石脂 | 禁止同用 |
| 人参 × 五灵脂 | 禁止同用 |

### 匹配算法

```python
# 对输入的 herb_names 做两两组合检查
for i, herb_a in enumerate(herb_names):
    for herb_b in herb_names[i+1:]:
        # 查询 safety_rules 中是否有匹配
        rule = await db.fetch_one(
            "SELECT * FROM safety_rules WHERE rule_type='配伍禁忌' "
            "AND ((drug_a=? AND drug_b=?) OR (drug_a=? AND drug_b=?))",
            (herb_a, herb_b, herb_b, herb_a)
        )
        if rule:
            warnings.append(SafetyWarning(
                layer=1, severity=rule['severity'],
                title=f"配伍禁忌：{rule['source']}",
                detail=rule['description'],
                herbs=[herb_a, herb_b],
                action="禁止", source=rule['source']
            ))
```

## 第1b层：中西药交互

### 规则（R-01 ~ R-10）

| 编号 | 西药 | 中药/类别 | 机制 | 严重性 |
|------|------|----------|------|--------|
| R-01 | 华法林 | 当归/丹参/红花 | 增加出血风险 | critical |
| R-02 | 阿司匹林 | 银杏叶/当归 | 增加出血风险 | high |
| R-03 | 地高辛 | 麻黄/甘草 | 影响血药浓度 | critical |
| R-04 | MAOI类抗抑郁药 | 麻黄 | 高血压危象 | critical |
| R-05 | 他汀类降脂药 | 五味子/山楂 | 横纹肌溶解风险 | critical |
| R-06 | 降糖药 | 葛根/山药/玉竹 | 低血糖 | warning |
| R-07 | 降压药 | 甘草 | 升高血压/减弱降压效果 | warning |
| R-08 | 抗血小板药 | 银杏叶/丹参 | 出血风险 | critical |
| R-09 | 四环素类 | 石膏/龙骨/牡蛎 | 影响吸收 | warning |
| R-10 | 铁剂 | 大黄/虎杖 | 影响吸收 | warning |

### 匹配方式
- 精确匹配：药品名 × 中药名
- 模糊匹配：drugClass 匹配（如 "降压药" 匹配 "硝苯地平"）

## 第2层：剂量检查

### 逻辑
1. 对每个输入 herb，查询 DB 的 `dosage_min_g` 和 `dosage_max_g`
2. 如果用户指定了剂量：
   - > max → "剂量超出安全范围"
   - < min → "剂量低于推荐范围"
   - = max → 正好上限（不警告）
3. 如果未指定剂量：仅提示安全范围

### 示例
```python
if herb['dosage_max_g'] and user_dosage > herb['dosage_max_g']:
    warnings.append(SafetyWarning(
        layer=2, severity="medium",
        title="剂量超出安全范围",
        detail=f"{herb_name}的安全用量为 {min}-{max}g，您输入了 {user_dosage}g",
        herbs=[herb_name], action="谨慎", source="药典"
    ))
```

## 第3层：特殊人群

### 规则

| 人群 | 条件 | 动作 |
|------|------|------|
| 孕妇 | `is_pregnant = true` | 检查禁忌药材（活血化瘀/峻下逐水/毒性）→ warning |
| 婴幼儿 | `age < 3` | **BLOCK** → critical "3岁以下婴幼儿，请直接就医" |
| 儿童 | `3 ≤ age < 14` | 儿童用药安全提示 → medium |
| 老年 | `age ≥ 65` | 剂量调整提示 → medium |

### 孕妇禁忌药材列表
桃仁、红花、牛膝、川芎、三棱、莪术、水蛭、虻虫、斑蝥、麝香、附子、乌头、巴豆、甘遂、大戟、芫花、芒硝

## 第5层：免责声明

始终附加，不可关闭：

> ⚠️ 以上分析基于中药配伍禁忌和中西药交互规则，仅供参考，不能替代专业中医师的诊断和处方。如有不适，请及时就医。

## 急症关键词（独立于五层）

### 29 个关键词
急救、急诊、心梗、脑梗、休克、昏迷、抽搐、呼吸困难、大出血、中毒、服毒、上吊、跳楼、割腕、不省人事、心脏骤停、窒息、溺水、烧伤、烫伤、骨折、车祸、中风、晕厥、吐血、便血、高烧不退、剧烈疼痛

### 拦截逻辑
```python
# 在 AI 对话之前检查
matched = check_emergency_keywords(user_message)
if matched:
    return {
        "reply": "您提到的症状可能需要紧急就医。请立即拨打120急救电话或前往最近的医院急诊。",
        "warnings": [f"检测到急症关键词：{', '.join(matched)}"],
        "blocked": True  # 不发送到 AI
    }
```

## 测试覆盖

| 测试文件 | 数量 | 覆盖 |
|---------|------|------|
| test_safety_comprehensive.py | 41 | 全部五层 |
| test_chat.py | 2 | 急症关键词 |
| test_formula_safety.py | 15 | 方剂联动 |

### Layer 1a 测试（10 个）
- 十八反：乌头+半夏、甘草+甘遂、藜芦+人参
- 十九畏：硫磺+朴硝、丁香+郁金、人参+五灵脂
- 安全组合、三味组合冲突、自冲突

### Layer 1b 测试（10 个）
- R-01 ~ R-10 各一个测试 + 安全组合

### Layer 2 测试（5 个）
- 超量、低量、范围内、未指定、恰好上限

### Layer 3 测试（8 个）
- 孕妇+有毒/安全、2岁BLOCK、5岁/13岁/40岁/70岁、缺失 profile

### Layer 5 测试（3 个）
- 声明存在、内容正确、不重复

### 集成测试（5 个）
- 多层触发、全安全、空列表、未知药材、结构验证

## 代码位置

| 文件 | 职责 |
|------|------|
| `app/safety_engine.py` | 五层引擎核心逻辑 |
| `app/safety_keywords.py` | 29 个急症关键词 |
| `app/routers/safety.py` | API 端点 V1/V2 |
| `app/routers/chat.py` | AI 对话中的急症拦截 |
| `app/database.py` | `seed_safety_rules()` 60+ 规则 |
| `tests/test_safety_comprehensive.py` | 41 个安全测试 |
