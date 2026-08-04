"""Agent tools — 10 atomic functions for the autonomous knowledge pipeline.

Each tool is self-contained: takes inputs, returns structured output, logs
to agent_logs. Tools can be freely composed by the knowledge_agent pipeline.

Design: all tools are async, fail gracefully (never raise), and write
audit entries for every action.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from app.database import DbAdapter

logger = logging.getLogger(__name__)


async def log_action(
    db: DbAdapter,
    action_type: str,
    source_type: str = "",
    source_ref: str = "",
    entity_id: str = "",
    details: dict[str, Any] | None = None,
    decision: str = "",
) -> str:
    """Write an audit entry to agent_logs."""
    log_id = f"log-{uuid.uuid4()}"
    try:
        await db.execute(
            """INSERT INTO agent_logs (id, action_type, source_type, source_ref,
               entity_id, details, decision)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                log_id, action_type, source_type, source_ref,
                entity_id,
                json.dumps(details or {}, ensure_ascii=False),
                decision,
            ),
        )
    except Exception as exc:
        logger.warning("agent_tools: log_action failed: %s", exc)
    return log_id



from app.tools.pipeline import (  # noqa: E402,F401
    tool_extract,
    tool_analyze,
    tool_scan_entities,
    tool_check_duplicates,
    tool_assess_quality,
    tool_create_or_update_entity,
    tool_build_index,
    tool_index_external_content,
    tool_push_to_modules,
)
from app.tools.review import (  # noqa: E402,F401
    tool_multi_model_review,
    tool_detect_conflicts,
)
from app.tools.entities import (  # noqa: E402,F401
    tool_record_provenance,
    tool_generate_summary,
    tool_auto_relate,
    tool_delete_entity,
    tool_create_relationship,
    tool_delete_relationship,
    tool_list_entity_types,
    tool_list_categories,
)
from app.tools.config import (  # noqa: E402,F401
    tool_query_logs,
    tool_optimize_prompt,
    tool_apply_prompt_optimization,
    tool_optimize_and_apply,
    tool_generalize_experience,
    memory_save_tool,
    _AGENT_CONFIGS,
    _load_configs_from_db,
    tool_get_config,
    tool_set_config,
)
