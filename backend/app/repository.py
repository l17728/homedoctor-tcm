"""Repository layer with tenant_id filtering via contextvars."""

from __future__ import annotations

import contextvars
from typing import Any

from app.database import DbAdapter

# Current tenant_id — set by middleware from JWT
current_tenant_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "tenant_id", default="default"
)


class BaseRepository:
    """Base repository with mandatory tenant_id filtering."""

    def __init__(self, db: DbAdapter) -> None:
        self.db = db

    def _tenant_id(self) -> str:
        return current_tenant_id.get()

    def _tenant_filter(self, alias: str = "") -> str:
        prefix = f"{alias}." if alias else ""
        return f"{prefix}tenant_id = ?"

    async def _query_tenant(
        self, sql: str, params: tuple[Any, ...] = (), *, inject_tenant: bool = False
    ) -> list[dict[str, Any]]:
        """Run a query, optionally prepending tenant_id to params."""
        if inject_tenant:
            params = (self._tenant_id(),) + params
        return await self.db.query(sql, params)

    async def _query_one_tenant(
        self, sql: str, params: tuple[Any, ...] = (), *, inject_tenant: bool = False
    ) -> dict[str, Any] | None:
        if inject_tenant:
            params = (self._tenant_id(),) + params
        return await self.db.query_one(sql, params)


class HerbRepository(BaseRepository):
    """Repository for herbs (global data, no tenant filtering)."""

    async def list_herbs(
        self, page: int = 1, page_size: int = 20, category: str | None = None
    ) -> tuple[list[dict[str, Any]], int]:
        where = ""
        params: list[Any] = []
        if category:
            where = "WHERE category = ?"
            params.append(category)

        count_row = await self.db.query_one(
            f"SELECT COUNT(*) as cnt FROM herbs {where}", tuple(params)
        )
        total = count_row["cnt"] if count_row else 0

        offset = (page - 1) * page_size
        rows = await self.db.query(
            f"SELECT * FROM herbs {where} ORDER BY name LIMIT ? OFFSET ?",
            tuple(params + [page_size, offset]),
        )
        return rows, total

    async def get_herb(self, herb_id: str) -> dict[str, Any] | None:
        return await self.db.query_one("SELECT * FROM herbs WHERE id = ?", (herb_id,))

    async def search_herbs(self, query: str) -> list[dict[str, Any]]:
        """FTS5 full-text search across herbs."""
        rows = await self.db.query(
            """SELECT h.* FROM herbs h
               JOIN herbs_fts fts ON h.rowid = fts.rowid
               WHERE herbs_fts MATCH ?
               ORDER BY rank""",
            (query,),
        )
        return rows


class FormulaRepository(BaseRepository):
    """Repository for formulas (global data, no tenant filtering)."""

    async def list_formulas(
        self, page: int = 1, page_size: int = 20, category: str | None = None
    ) -> tuple[list[dict[str, Any]], int]:
        where = ""
        params: list[Any] = []
        if category:
            where = "WHERE category = ?"
            params.append(category)

        count_row = await self.db.query_one(
            f"SELECT COUNT(*) as cnt FROM formulas {where}", tuple(params)
        )
        total = count_row["cnt"] if count_row else 0

        offset = (page - 1) * page_size
        rows = await self.db.query(
            f"SELECT * FROM formulas {where} ORDER BY name LIMIT ? OFFSET ?",
            tuple(params + [page_size, offset]),
        )
        return rows, total

    async def get_formula(self, formula_id: str) -> dict[str, Any] | None:
        return await self.db.query_one(
            "SELECT * FROM formulas WHERE id = ?", (formula_id,)
        )


class MedicineRepository(BaseRepository):
    """Repository for medicines (tenant-scoped, family drug cabinet)."""

    async def list_medicines(
        self, page: int = 1, page_size: int = 20
    ) -> tuple[list[dict[str, Any]], int]:
        tid = self._tenant_id()
        count_row = await self.db.query_one(
            "SELECT COUNT(*) as cnt FROM medicines WHERE tenant_id = ?", (tid,)
        )
        total = count_row["cnt"] if count_row else 0

        offset = (page - 1) * page_size
        rows = await self.db.query(
            "SELECT * FROM medicines WHERE tenant_id = ? ORDER BY name LIMIT ? OFFSET ?",
            (tid, page_size, offset),
        )
        return rows, total

    async def get_medicine(self, medicine_id: str) -> dict[str, Any] | None:
        tid = self._tenant_id()
        return await self.db.query_one(
            "SELECT * FROM medicines WHERE id = ? AND tenant_id = ?",
            (medicine_id, tid),
        )

    async def create_medicine(self, data: dict[str, Any]) -> str:
        import uuid
        import json

        medicine_id = str(uuid.uuid4())
        tid = self._tenant_id()
        await self.db.execute(
            """INSERT INTO medicines
               (id, tenant_id, name, brand, type, specification, unit, quantity,
                production_date, expiry_date, opened_date, shelf_life_after_open,
                dosage_instructions, contraindications, barcode, drug_class,
                active_ingredients, herbal_fields, properties)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                medicine_id, tid, data["name"], data.get("brand"), data["type"],
                data.get("specification"), data.get("unit"), data.get("quantity", 0),
                data.get("production_date"), data.get("expiry_date"),
                data.get("opened_date"), data.get("shelf_life_after_open"),
                data.get("dosage_instructions"), data.get("contraindications"),
                data.get("barcode"), data.get("drug_class"),
                json.dumps(data.get("active_ingredients", []), ensure_ascii=False),
                json.dumps(data.get("herbal_fields", {}), ensure_ascii=False),
                json.dumps(data.get("properties", {}), ensure_ascii=False),
            ),
        )
        return medicine_id

    async def update_medicine(self, medicine_id: str, data: dict[str, Any]) -> bool:
        import json

        tid = self._tenant_id()
        existing = await self.get_medicine(medicine_id)
        if not existing:
            return False

        # Build dynamic UPDATE
        set_parts: list[str] = []
        values: list[Any] = []
        json_fields = {"active_ingredients", "herbal_fields", "properties"}

        for key, value in data.items():
            if value is None:
                continue
            if key in json_fields:
                set_parts.append(f"{key} = ?")
                values.append(json.dumps(value, ensure_ascii=False))
            else:
                set_parts.append(f"{key} = ?")
                values.append(value)

        if not set_parts:
            return True  # nothing to update

        set_parts.append("updated_at = datetime('now')")
        values.append(medicine_id)
        values.append(tid)

        await self.db.execute(
            f"UPDATE medicines SET {', '.join(set_parts)} WHERE id = ? AND tenant_id = ?",
            tuple(values),
        )
        return True

    async def delete_medicine(self, medicine_id: str) -> bool:
        tid = self._tenant_id()
        existing = await self.get_medicine(medicine_id)
        if not existing:
            return False
        await self.db.execute(
            "DELETE FROM medicines WHERE id = ? AND tenant_id = ?",
            (medicine_id, tid),
        )
        return True


class SafetyRepository(BaseRepository):
    """Repository for safety rules."""

    async def find_conflicts(
        self, herb_names: list[str], drug_names: list[str]
    ) -> list[dict[str, Any]]:
        """Find all safety rule conflicts between given herbs and drugs."""
        all_items = herb_names + drug_names
        if not all_items:
            return []

        results: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        # Check herb-herb pairs against 18反/19畏
        for i, a in enumerate(all_items):
            for b in all_items[i + 1:]:
                rows = await self.db.query(
                    """SELECT * FROM safety_rules WHERE enabled = 1
                       AND ((drug_a = ? AND drug_b = ?) OR (drug_a = ? AND drug_b = ?))
                       AND rule_type IN ('十八反', '十九畏')""",
                    (a, b, b, a),
                )
                for r in rows:
                    if r["id"] not in seen_ids:
                        seen_ids.add(r["id"])
                        results.append(r)

        # Check herb-drug interactions (drug_a is western drug, drug_b is herb)
        for drug in drug_names:
            for herb in herb_names:
                rows = await self.db.query(
                    """SELECT * FROM safety_rules WHERE enabled = 1
                       AND drug_a = ? AND drug_b = ?
                       AND rule_type = '中西药交互'""",
                    (drug, herb),
                )
                for r in rows:
                    if r["id"] not in seen_ids:
                        seen_ids.add(r["id"])
                        results.append(r)

        # Also check drug class matching for western drugs
        for drug in drug_names:
            rows = await self.db.query(
                """SELECT * FROM safety_rules WHERE enabled = 1
                   AND drug_a LIKE ? AND rule_type = '中西药交互'""",
                (f"%{drug}%",),
            )
            for r in rows:
                if r["id"] not in seen_ids and r["drug_b"] in herb_names:
                    seen_ids.add(r["id"])
                    results.append(r)

        return results
