"""Generate the OpenAPI route index in ``docs/API_REFERENCE.md``.

The prose and examples before the generated markers remain hand-maintained.
Running this script repeatedly produces byte-for-byte identical output until
the application's OpenAPI schema changes.
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app  # noqa: E402


START_MARKER = "<!-- BEGIN AUTO-GENERATED API ROUTES -->"
END_MARKER = "<!-- END AUTO-GENERATED API ROUTES -->"
HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}


def _summary(operation: dict[str, Any]) -> str:
    value = operation.get("summary")
    if not value:
        value = (operation.get("description") or "").splitlines()[0:1]
        value = value[0] if value else ""
    return " ".join(str(value).split()).replace("|", "\\|")


def _parameter_summary(operation: dict[str, Any]) -> str:
    items: list[str] = []
    for parameter in operation.get("parameters", []):
        name = parameter.get("name", "?")
        location = parameter.get("in", "?")
        required = "，必填" if parameter.get("required") else "，可选"
        items.append(f"`{name}`（{location}{required}）")

    body = operation.get("requestBody")
    if body:
        required = "必填" if body.get("required") else "可选"
        content_types = ", ".join((body.get("content") or {}).keys())
        label = f"请求体，{required}"
        if content_types:
            label += f"：{content_types}"
        items.append(label)
    return "；参数：" + "、".join(items) if items else ""


def render_routes(spec: dict[str, Any]) -> tuple[str, int]:
    by_tag: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}
    count = 0
    for path, operations in spec.get("paths", {}).items():
        for method, operation in operations.items():
            method = method.upper()
            if method not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            count += 1
            tags = operation.get("tags") or ["未分类"]
            for tag in tags:
                by_tag.setdefault(str(tag), []).append((method, path, operation))

    lines = [
        "## 自动生成的 API 路由索引",
        "",
        "> 来源：FastAPI OpenAPI。运行 `python backend/scripts/gen_api_reference.py` 更新。",
        "",
        f"> 路由数：{count}",
        "",
    ]
    for tag in sorted(by_tag, key=str.casefold):
        lines.extend([f"### {tag}", ""])
        for method, path, operation in sorted(
            by_tag[tag], key=lambda row: (row[1], row[0])
        ):
            summary = _summary(operation)
            suffix = _parameter_summary(operation)
            lines.append(f"- `{method} {path}` — {summary}{suffix}")
        lines.append("")
    return "\n".join(lines).rstrip(), count


def update_document(document: str, generated: str) -> str:
    start = document.find(START_MARKER)
    end = document.find(END_MARKER)
    if (start == -1) != (end == -1):
        raise ValueError("API reference contains only one generated-region marker")
    if start != -1:
        if end < start:
            raise ValueError("API reference generated-region markers are reversed")
        end += len(END_MARKER)
        prefix = document[:start].rstrip()
        suffix = document[end:].lstrip("\r\n")
    else:
        # Migrate the existing unmarked generated appendix while preserving
        # every hand-written section above it.
        legacy_heading = "## 自动生成的 API 路由索引"
        legacy_start = document.find(legacy_heading)
        prefix = document[:legacy_start].rstrip() if legacy_start >= 0 else document.rstrip()
        suffix = ""

    region = f"{START_MARKER}\n{generated}\n{END_MARKER}"
    result = f"{prefix}\n\n{region}"
    if suffix:
        result += f"\n\n{suffix}"
    return result.rstrip() + "\n"


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    output = root / "docs" / "API_REFERENCE.md"
    generated, route_count = render_routes(app.openapi())
    previous = output.read_text(encoding="utf-8")
    updated = update_document(previous, generated)
    if updated != previous:
        output.write_text(updated, encoding="utf-8", newline="\n")
    print(f"API reference generated: {route_count} routes -> {output.relative_to(root)}")


if __name__ == "__main__":
    main()
