"""Regenerate the route appendix in docs/API_REFERENCE.md from FastAPI OpenAPI."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    output = root / "docs" / "API_REFERENCE.md"
    existing = output.read_text(encoding="utf-8").splitlines()
    header = "\n".join(existing[:50]).rstrip()

    spec = app.openapi()
    by_tag: dict[str, list[tuple[str, str, dict]]] = {}
    for path, operations in spec.get("paths", {}).items():
        for method, operation in operations.items():
            if method.upper() not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                continue
            tags = operation.get("tags") or ["未分类"]
            for tag in tags:
                by_tag.setdefault(tag, []).append((method.upper(), path, operation))

    lines = ["## 自动生成的 API 路由索引", "", f"> 生成日期：{date.today().isoformat()}。重新运行 `python scripts/gen_api_reference.py` 更新。", ""]
    for tag in sorted(by_tag, key=str.casefold):
        lines.extend([f"### {tag}", ""])
        for method, path, operation in sorted(by_tag[tag], key=lambda row: (row[1], row[0])):
            summary = operation.get("summary") or operation.get("description", "").splitlines()[0:1]
            if isinstance(summary, list):
                summary = summary[0] if summary else ""
            parameters = operation.get("parameters") or []
            params = ", ".join(
                f"`{item.get('name')}` ({item.get('in')})" for item in parameters
            )
            request_body = "；请求体" if operation.get("requestBody") else ""
            suffix = f"；参数：{params}" if params else ""
            lines.append(f"- `{method} {path}` — {summary}{suffix}{request_body}")
        lines.append("")

    output.write_text(header + "\n\n" + "\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
