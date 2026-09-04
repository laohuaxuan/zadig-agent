"""飞书审批卡片 message_id 持久化。"""

from __future__ import annotations

from typing import Any

from utils.db import _now, execute, query, query_one


def create_workflow_feishu_card(
    *,
    instance_id: int,
    task_id: int,
    user_id: int,
    open_message_id: str,
    open_id: str = "",
) -> None:
    now = _now()
    execute(
        """
        INSERT INTO workflow_feishu_cards
        (instance_id, task_id, user_id, open_message_id, open_id, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (instance_id, task_id, user_id, open_message_id, open_id, now, now),
    )


def list_workflow_feishu_cards_by_instance(instance_id: int) -> list[dict[str, Any]]:
    return query(
        """
        SELECT * FROM workflow_feishu_cards
        WHERE instance_id = %s
        ORDER BY id ASC
        """,
        (instance_id,),
    )


def latest_workflow_feishu_card(instance_id: int, user_id: int, task_id: int) -> dict[str, Any] | None:
    return query_one(
        """
        SELECT * FROM workflow_feishu_cards
        WHERE instance_id = %s AND user_id = %s AND task_id = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (instance_id, user_id, task_id),
    )
