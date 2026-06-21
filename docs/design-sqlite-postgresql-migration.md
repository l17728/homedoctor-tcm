# 设计文档：SQLite → PostgreSQL 迁移方案

> 状态：**设计完成，暂不实施**
> 日期：2025-06-21
> 作者：系统架构评审

## 1. 背景与动机

当前系统使用 SQLite + SQLCipher 作为数据存储。优点：零配置、本地优先、单文件部署。
随着数据增长（1594+ 实体、2888+ 关系、1595 RAG 分块）和多家庭并发使用，需要评估迁移到 PostgreSQL 的可行性和路径。

## 2. 当前 SQLite 方言依赖分析

| 方言特性 | 使用次数 | 迁移难度 | PostgreSQL 对应 |
|---------|---------|---------|----------------|
| `datetime('now')` | 70 处 | 低 | `NOW()` 或 `CURRENT_TIMESTAMP` |
| `json_extract()` | 少量 | 低 | `->` / `->>` 操作符 |
| `INSERT OR REPLACE` | 18 处 | 中 | `INSERT ... ON CONFLICT DO UPDATE` |
| FTS5 全文搜索 | 12 处 | **高** | `tsvector` + `tsquery` + GIN 索引 |
| `PRAGMA` | 5 处 | 低 | PostgreSQL 配置参数 |
| `sqlite3` 类型引用 | 14 处 | 中 | `asyncpg` 类型 |
| `row_factory = Row` | 1 处 | 低 | asyncpg 默认返回 dict |
| `sqlite_master` | 2 处 | 低 | `information_schema` |

## 3. 现有抽象层评估

```python
# database.py — 已有抽象
class DbAdapter(ABC):
    @property
    @abstractmethod
    def dialect(self) -> str: ...  # 'sqlite' or 'postgresql'

    @abstractmethod
    async def query(self, sql, params) -> list[dict]: ...

    @abstractmethod
    async def query_one(self, sql, params) -> dict | None: ...

    @abstractmethod
    async def execute(self, sql, params) -> Any: ...

    @abstractmethod
    async def transaction(self) -> AsyncContextManager: ...
```

**评估结论**：抽象层设计正确。`dialect` 属性已添加。需增加 SQL 方言翻译层。

## 4. 迁移架构设计

```
应用层（路由/引擎/Agent）
         ↓ 调用
    DbAdapter（ABC）
     ↙        ↘
SqliteAdapter  PostgresAdapter
     ↓              ↓
  aiosqlite      asyncpg
     ↓              ↓
  SQLite 文件   PostgreSQL
```

### 4.1 方言翻译层 (Dialect)

```python
class Dialect(ABC):
    @abstractmethod
    def now(self) -> str: ...
    @abstractmethod
    def upsert(self, table, columns, conflict_cols) -> str: ...
    @abstractmethod
    def json_extract(self, column, path) -> str: ...
    @abstractmethod
    def fts_match(self, query) -> str: ...

class SqliteDialect(Dialect):
    def now(self) -> str: return "datetime('now')"
    def upsert(self, table, columns, conflict_cols) -> str:
        return f"INSERT OR REPLACE INTO {table} ..."
    def json_extract(self, column, path) -> str:
        return f"json_extract({column}, '$.{path}')"
    def fts_match(self, query) -> str:
        return f"MATCH '{query}'"

class PostgresDialect(Dialect):
    def now(self) -> str: return "NOW()"
    def upsert(self, table, columns, conflict_cols) -> str:
        return f"INSERT INTO {table} ... ON CONFLICT ({conflict_cols}) DO UPDATE SET ..."
    def json_extract(self, column, path) -> str:
        return f"{column}->>'{path}'"
    def fts_match(self, query) -> str:
        return f"@@ to_tsquery('chinese', '{query}')"
```

### 4.2 全文搜索迁移（最大障碍）

SQLite FTS5 → PostgreSQL:

| SQLite FTS5 | PostgreSQL |
|-------------|-----------|
| `CREATE VIRTUAL TABLE herbs_fts USING fts5(...)` | `CREATE INDEX herbs_fts_idx ON herbs USING GIN(to_tsvector('chinese', ...))` |
| `SELECT * FROM herbs_fts WHERE herbs_fts MATCH '黄芪'` | `SELECT * FROM herbs WHERE to_tsvector('chinese', name) @@ to_tsquery('黄芪')` |
| 自动触发器同步 | 需要手动触发器或 generated column |
| 中文分词：内置 | 需 `pg_jieba` 或 `zhparser` 扩展 |

**注意**：PostgreSQL 中文全文搜索需要安装 `zhparser` 或 `pg_jieba` 扩展。

### 4.3 RAG 向量搜索迁移

当前：numpy 余弦相似度（内存加载全部向量）

PostgreSQL 方案：
- `pgvector` 扩展：原生向量存储 + 余弦/内积搜索
- `CREATE TABLE embeddings (id text, embedding vector(1024))`
- `SELECT id FROM embeddings ORDER BY embedding <=> $1 LIMIT 10`
- 优势：无需全量加载到内存，支持 HNSW/IVFFlat 索引

### 4.4 SQLCipher → PostgreSQL 原生加密

SQLite 使用 SQLCipher (AES-256) 透明加密。
PostgreSQL 替代方案：
- 传输加密：TLS/SSL 连接
- 存储加密：`pgcrypto` 扩展（列级加密）或磁盘级加密（LUKS）
- 不需要 PRAGMA key

## 5. 迁移步骤（按优先级）

| 阶段 | 工作 | 工作量 |
|------|------|--------|
| Phase 1 | 创建 `Dialect` ABC + `SqliteDialect` 实现 | 1 天 |
| Phase 2 | 全部 SQL 语句通过 Dialect 生成（替换硬编码 SQL 方言） | 2-3 天 |
| Phase 3 | 创建 `PostgresAdapter` + `PostgresDialect` | 1-2 天 |
| Phase 4 | FTS5 → tsvector 迁移（含中文分词扩展） | 1-2 天 |
| Phase 5 | numpy 向量 → pgvector 迁移 | 1 天 |
| Phase 6 | 双数据库测试 + 数据迁移脚本 | 1-2 天 |
| **总计** | | **7-11 天** |

## 6. 决策建议

| 条件 | 建议 |
|------|------|
| 用户量 < 50 家庭 | 保持 SQLite（足够用） |
| 用户量 50-500 | SQLite + 定期 VACUUM 优化 |
| 用户量 > 500 或多服务器 | 迁移到 PostgreSQL |
| 需要全文搜索中文分词质量 | 考虑 PostgreSQL + zhparser |
| 需要向量搜索性能（>10万向量） | 考虑 PostgreSQL + pgvector |

**当前建议**：保持 SQLite，已完成抽象层准备（`dialect` 属性）。当用户量或数据量触发阈值时，按上述 6 阶段迁移。

## 7. 已完成的准备工作

- ✅ `DbAdapter` ABC 定义了 `dialect` 属性
- ✅ `execute()` 返回类型从 `sqlite3.Cursor` 改为 `Any`
- ✅ 方言特性已编目（102 处）
- ✅ 本设计文档

## 8. 待实施时的检查清单

- [ ] Dialect ABC + SqliteDialect + PostgresDialect
- [ ] 所有 SQL 语句参数化（无硬编码方言）
- [ ] FTS5 → tsvector 迁移 + zhparser 安装
- [ ] numpy → pgvector 迁移
- [ ] PRAGMA → PG 配置映射
- [ ] INSERT OR REPLACE → ON CONFLICT
- [ ] 双模式测试（SQLite + PG 并行验证）
- [ ] 数据迁移脚本（SQLite → PG）
- [ ] docker-compose 增加 postgres 服务（可选）
