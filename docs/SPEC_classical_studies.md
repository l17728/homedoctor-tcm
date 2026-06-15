# P1-1: 经典学习模块（Classical Studies）

> **状态**：需求记录，待实现
> **优先级**：P1（MVP 后增强功能）
> **提出日期**：2026-06-12

---

## 需求概述

新增「经典学习」模块，收录中国传统中医经典著作，按学习次第组织，支持原文阅读、笔记、白话对照翻译、以及基于选中文字的 AI 问答。

## 功能清单

### 1. 经典著作库
- **黄帝内经**（素问 + 灵枢，各 81 篇）
- **伤寒论**（113 方 + 397 条）
- **金匮要略**（25 篇）
- **温病条辨**
- **本草纲目**（选编）
- 后续可扩展：难经、神农本草经、千金方等

### 2. 学习次第组织
按由浅入深的学习顺序排列：
```
入门 → 黄帝内经·素问（选读篇目）→ 伤寒论（六经辨证主线）→ 金匮要略（杂病）→ 温病条辨
```
- 每部著作内按篇章顺序
- 标注「推荐入门」「进阶」「精读」等级
- 学习进度追踪（已读/在读/未读）

### 3. 原文阅读
- 竖排/横排切换
- 繁体/简体切换
- 篇章目录导航
- 阅读进度自动记忆
- 字号可调（适老化 18px+）

### 4. 白话对照翻译
- 类似双语阅读体验，左右或上下分栏
- 左侧：古文原文
- 右侧：现代白话翻译
- 逐段对齐，滚动联动
- 可切换「仅原文」「仅译文」「对照」三种模式

### 5. 笔记系统
- 选中文字 → 弹出工具栏（高亮/笔记/问答）
- 高亮：标记重要段落（多色）
- 笔记：对选中文字写批注（富文本）
- 笔记按篇章组织，可汇总查看
- 笔记数据存 SQLite（user_id + classic_id + chapter + selection_range + content）

### 6. AI 问答侧边栏（核心交互）
- **布局**：左侧阅读区（70%）+ 右侧问答面板（30%）
- **触发方式**：
  - 选中左侧文字 → 右侧自动弹出「解读选中内容」
  - 手动在右侧输入框提问
- **问答上下文**：自动将选中文字 + 所在篇章 + 前后文作为上下文传给 AI
- **问答类型**：
  - 「这句古文什么意思？」→ 白话翻译
  - 「这个方剂的适应症？」→ 结合方剂库解读
  - 「这个概念在现代怎么理解？」→ 古今对照
- 问答历史按篇章保存

### 7. 数据模型（预估）

```sql
-- 经典著作
CREATE TABLE classics (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,         -- "黄帝内经·素问"
    author TEXT,
    era TEXT,                     -- "春秋战国"
    difficulty TEXT,              -- "入门" | "进阶" | "精读"
    sort_order INTEGER,           -- 学习次第
    description TEXT
);

-- 篇章
CREATE TABLE classic_chapters (
    id TEXT PRIMARY KEY,
    classic_id TEXT NOT NULL,
    chapter_num INTEGER,
    title TEXT NOT NULL,          -- "上古天真论篇第一"
    original_text TEXT,           -- 古文原文（分段用 \n\n）
    translation TEXT,             -- 白话翻译（分段对应）
    notes TEXT,                   -- 编者注
    sort_order INTEGER,
    FOREIGN KEY (classic_id) REFERENCES classics(id)
);

-- 用户笔记
CREATE TABLE classic_notes (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    chapter_id TEXT NOT NULL,
    selection_start INTEGER,      -- 选中文字起始位置
    selection_end INTEGER,        -- 选中文字结束位置
    selection_text TEXT,          -- 选中文字内容
    note_type TEXT,               -- "highlight" | "note" | "question"
    content TEXT,                 -- 笔记内容 / 问答内容
    color TEXT,                   -- 高亮颜色
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY (chapter_id) REFERENCES classic_chapters(id)
);

-- 阅读进度
CREATE TABLE classic_progress (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    classic_id TEXT NOT NULL,
    current_chapter_id TEXT,
    read_chapters TEXT DEFAULT '[]',  -- JSON array of chapter_ids
    last_read_at TEXT,
    FOREIGN KEY (classic_id) REFERENCES classics(id)
);
```

### 8. 前端页面（预估）
- `ClassicsListPage`：经典列表，按学习次第排列，显示进度
- `ClassicReaderPage`：核心阅读页
  - 左 70%：原文/译文对照阅读区
  - 右 30%：AI 问答侧边栏
  - 顶部：篇章导航 + 模式切换（原文/译文/对照）
- `ClassicNotesPage`：笔记汇总

### 9. 技术要点
- 古文数据量大（黄帝内经素问 81 篇约 15 万字），需分批 seed
- 翻译数据需要人工编辑，初期可只收录部分经典篇章
- AI 问答复用现有 `/api/chat` 端点，增加 `context` 参数传入选中文字
- 选中文字交互用 `window.getSelection()` API
- 笔记高亮用 `<mark>` 标签 + contenteditable 或自定义渲染

## 与现有模块的关系
- **方剂库**：伤寒论篇章中提到的方剂可链接到 `/formulas/:id`
- **中药库**：本草纲目篇目中的药材可链接到 `/herbs/:id`
- **安全检查**：经典中的方剂应用建议触发安全检查
- **AI 问答**：复用 chat API + safety engine

## 实现建议
1. 先做最小版本：伤寒论 20 条核心条文 + 白话翻译 + 基础阅读
2. 再加笔记 + AI 问答侧边栏
3. 最后扩展到完整经典库
