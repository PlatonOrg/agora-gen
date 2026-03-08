from __future__ import annotations

from typing import Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def list_exercises_using_template(
        session: AsyncSession,
        template_platon_id: str,
        limit: int = 200
) -> list[dict[str, Any]]:
    """
    Given a template Platon ID, return all exercises referencing it.
    """

    sql = text("""
               SELECT
                   e.id::text AS exercise_id,
                   e.platon_id::text AS exercise_platon_id,
                   e.created_at
               FROM exercise e
                        JOIN template t ON t.id = e.template_id
               WHERE t.platon_id = :tpl
               ORDER BY e.created_at DESC
                   LIMIT :limit
               """)

    res = await session.execute(sql, {"tpl": template_platon_id, "limit": limit})
    rows = res.fetchall()

    return [
        {
            "exercise_id": r.exercise_id,
            "exercise_platon_id": r.exercise_platon_id,
        }
        for r in rows
    ]