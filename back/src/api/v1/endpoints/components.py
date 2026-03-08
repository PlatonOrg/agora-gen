"""
Components metadata endpoint.

Exposes the pre-built components/metadata.json via the REST API so that the
frontend can reliably consume it through the standard /api/ proxy, regardless
of deployment topology (dev, prod, Docker).  Serving the file directly from
nginx or as a static mount is fragile — the backend already owns this resource.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from src.core.path_constants import COMPONENT_METADATA_PATH

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/metadata",
    response_model=List[Dict[str, Any]],
    summary="List all component metadata entries",
)
async def get_components_metadata() -> List[Dict[str, Any]]:
    """
    Return the full component metadata list from the pre-built metadata.json.

    The file is generated at startup by the asset setup pipeline.  A 503 is
    returned when the file is not yet available (e.g. the background init is
    still running) so that the frontend can distinguish "not ready yet" from
    a permanent error and retry if appropriate.
    """
    if not COMPONENT_METADATA_PATH.exists():
        logger.warning(
            "Component metadata file not found at %s — asset setup may still be running.",
            COMPONENT_METADATA_PATH,
        )
        raise HTTPException(
            status_code=503,
            detail="Component metadata is not yet available. Please retry in a few moments.",
        )

    try:
        raw = COMPONENT_METADATA_PATH.read_text(encoding="utf-8")
        data: List[Dict[str, Any]] = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Failed to read component metadata: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Failed to load component metadata.",
        )

    if not isinstance(data, list) or not data:
        raise HTTPException(
            status_code=503,
            detail="Component metadata is empty. Asset setup may still be running.",
        )

    return data
