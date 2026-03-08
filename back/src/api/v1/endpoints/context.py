import json
import traceback
import logging
from fastapi import APIRouter, Request, Depends, HTTPException
from redis.asyncio import Redis
from src.services.platon_service import platon_service
from src.services.auth_service import auth_service
from src.api.v1.dependencies import get_session_id, get_user_token, require_session_id
from src.services.workspace_service import workspace_service
from src.services.template_service import filter_templates
from src.infra.db.redis import get_redis
from src.core.sqlalchemy import AsyncSessionLocal
from src.infra.db.components_repo import list_component_for_form
from typing import List, Optional
from src.services.models.api import (
    FilterTemplatesRequest,
    TemplateResponse,
    TemplatePreviewRequest,
    ExerciseData,
    CircleNode,
    TreeNode,
    Topic,
    Level,
    PreviewUrlResponse,
    PleContentResponse,
)
from src.services.models.platon import PlatonUser, SandboxError
from sqlalchemy import text

logger = logging.getLogger(__name__)

router = APIRouter()


def _transform_platon_tree_to_frontend_format(platon_resource: dict) -> TreeNode:
    if not platon_resource:
        return TreeNode(name="PLaTon")

    def transform_node(node: dict) -> TreeNode:
        children = [transform_node(child) for child in node.get("children", []) if child]
        return TreeNode(name=node.get("name", ""), children=children)

    return transform_node(platon_resource)


def _extract_circles_from_tree(tree: dict) -> List[CircleNode]:
    circles: List[CircleNode] = []

    def extract_node(node: dict, parent_id: Optional[str] = None) -> None:
        circle_id = node.get("id", "")
        circle_name = node.get("name", "")

        if circle_id and circle_name:
            permissions = node.get("permissions", {})
            circles.append(CircleNode(
                id=circle_id,
                name=circle_name,
                fullPath=circle_name,
                parentId=parent_id,
                hasChildren=bool(node.get("children")),
                writePermission=bool(permissions.get("write", False)),
            ))

        for child in node.get("children", []):
            extract_node(child, circle_id)

    if tree:
        extract_node(tree)

    return circles


def _transform_platon_topics_to_frontend_format(platon_topics) -> List[Topic]:
    if not isinstance(platon_topics, list):
        logger.warning(f"Expected list for topics, got {type(platon_topics)}")
        return []

    result: List[Topic] = []
    for topic in platon_topics:
        if not isinstance(topic, dict):
            continue
        topic_id = str(topic.get("id", ""))
        topic_name = str(topic.get("name", ""))
        if topic_id:
            result.append(Topic(
                id=topic_id,
                name=topic_name,
                description=f"Sujet: {topic_name}" if topic_name else "",
            ))
    return result


def _transform_platon_levels_to_frontend_format(platon_levels) -> List[Level]:
    if not isinstance(platon_levels, list):
        logger.warning(f"Expected list for levels, got {type(platon_levels)}")
        return []

    result: List[Level] = []
    for level in platon_levels:
        if not isinstance(level, dict):
            continue
        level_id = str(level.get("id", ""))
        level_name = str(level.get("name", ""))
        if level_id:
            result.append(Level(
                id=level_id,
                name=level_name,
                description=f"Niveau: {level_name}" if level_name else "",
            ))
    return result


@router.get("/all")
async def get_all_context(
    user_token: Optional[str] = Depends(get_user_token),
    redis: Redis = Depends(get_redis),
):
    circles_data: List[CircleNode] = []
    transformed_tree: TreeNode
    try:
        circles_tree = await platon_service.get_cercle_tree(token=user_token)
        circles_tree_data = circles_tree.get("resource", {})
        transformed_tree = _transform_platon_tree_to_frontend_format(circles_tree_data)
        circles_data = _extract_circles_from_tree(circles_tree_data)
    except Exception as e:
        logger.warning(f"Platon API call failed: {e}. Using fallback data.")
        transformed_tree = TreeNode(name="PLaTon")
        circles_data = []

    transformed_topics: List[Topic] = []
    try:
        topics_data = await platon_service.get_topics(token=user_token)
        transformed_topics = _transform_platon_topics_to_frontend_format(topics_data)
    except Exception as e:
        logger.warning(f"Platon topics API call failed: {e}. Using fallback data.")

    transformed_levels: List[Level] = []
    try:
        levels_data = await platon_service.get_levels(token=user_token)
        transformed_levels = _transform_platon_levels_to_frontend_format(levels_data)
    except Exception as e:
        logger.warning(f"Platon levels API call failed: {e}. Using fallback data.")

    components, formulaire, widgets = [], [], []
    try:
        async with AsyncSessionLocal() as session:
            components = await list_component_for_form(session)
        formulaire = [c for c in components if c["type"] == "Formulaire"]
        widgets = [c for c in components if c["type"] == "Widget"]
    except Exception as e:
        logger.error(f"[Context] components load failed: {e}")

    return {
        "circles": [c.model_dump() for c in circles_data],
        "circlesTree": transformed_tree.model_dump(),
        "topics": [t.model_dump() for t in transformed_topics],
        "levels": [lv.model_dump() for lv in transformed_levels],
        "components": components,
        "formulaireComponents": formulaire,
        "widgetComponents": widgets
    }


@router.get("/circles/tree")
async def get_circles_tree(user_token: Optional[str] = Depends(get_user_token)):

    try:
        response = await platon_service.get_cercle_tree(token=user_token)
        platon_tree = response.get("resource", {})
        return _transform_platon_tree_to_frontend_format(platon_tree).model_dump()
    except Exception as e:
        logger.warning(f"Platon API call failed: {e}. Using fallback data.")
        return TreeNode(name="PLaTon").model_dump()


@router.get("/topics")
async def get_topics(user_token: Optional[str] = Depends(get_user_token)):

    try:
        topics_data = await platon_service.get_topics(token=user_token)
        return [t.model_dump() for t in _transform_platon_topics_to_frontend_format(topics_data)]
    except Exception as e:
        logger.warning(f"Platon topics API call failed: {e}. Using fallback data.")
        return []


@router.get("/levels")
async def get_levels(user_token: Optional[str] = Depends(get_user_token)):

    try:
        levels_data = await platon_service.get_levels(token=user_token)
        return [lv.model_dump() for lv in _transform_platon_levels_to_frontend_format(levels_data)]
    except Exception as e:
        logger.warning(f"Platon levels API call failed: {e}. Using fallback data.")
        return []


@router.get("/template_config/{template_id}")
async def get_template_config(
    template_id: str,
    user_token: Optional[str] = Depends(get_user_token),
):

    try:
        config = await workspace_service.get_template_config(template_id, user_token)
        return config
    except Exception as e:
        logger.error(f"Error getting template config for {template_id}: {e}")
        raise HTTPException(status_code=500, detail="Erreur lors de la récupération de la configuration du template")


@router.post("/selected_templates", response_model=List[TemplateResponse])
async def get_selected_templates(
    request: FilterTemplatesRequest,
    user_token: Optional[str] = Depends(get_user_token),
):
    logger.info("Filtering templates with request: %s", request)

    try:
        async with AsyncSessionLocal() as session:
            template_responses = await filter_templates(
                request=request,
                session=session,
                user_token=user_token
            )

        logger.info(f"Successfully processed {len(template_responses)} templates")
        return template_responses

    except Exception as e:
        logger.exception(f"Error filtering templates: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/template_preview", response_model=PreviewUrlResponse)
async def preview_template(
    request: TemplatePreviewRequest,
    user_token: Optional[str] = Depends(get_user_token),
) -> PreviewUrlResponse:

    try:
        plo_content = json.dumps(request.variables)
        ple_content = f"@extends /{request.template_id}:latest/main.ple"

        preview_result = await platon_service.create_exercise_preview(
            ple=ple_content,
            plo=plo_content,
            plc=None
        )

        return PreviewUrlResponse(preview_url=preview_result.state.preview_url)

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la prévisualisation du template: {str(e)}"
        )


@router.post("/preview_exercise", response_model=PreviewUrlResponse)
async def preview_exercise(
    exercise_data: ExerciseData,
    req: Request,
    redis: Redis = Depends(get_redis)
) -> PreviewUrlResponse:
    logger.info(f"Previewing exercise with data: {exercise_data}")
    try:
        workspace_service.sanitise_exercise_data(exercise_data)

        has_content = any([
            exercise_data.titre,
            exercise_data.enonce,
            exercise_data.forme,
            exercise_data.construction,
            exercise_data.evaluation,
        ])
        if not has_content:
            raise HTTPException(
                status_code=422,
                detail="L'exercice ne contient aucun contenu exploitable pour la prévisualisation. "
                       "Veuillez remplir au moins le titre, l'énoncé ou le formulaire."
            )

        ple_content = workspace_service.from_json_to_ple(exercise_data)
        logger.info(f"Generated PLE content:\n{ple_content}")

        preview_result = await platon_service.create_exercise_preview(
            ple=ple_content,
            plo=None,
            plc=None
        )

        return PreviewUrlResponse(preview_url=preview_result.state.preview_url)

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la prévisualisation de l'exercice: {str(e)}"
        )


@router.post("/ple_content", response_model=PleContentResponse)
async def get_ple_content(
    exercise_data: ExerciseData,
    req: Request,
    redis: Redis = Depends(get_redis)
) -> PleContentResponse:
    logger.info(f"Generating PLE content for exercise: {exercise_data.name or 'unnamed'}")
    try:
        workspace_service.sanitise_exercise_data(exercise_data)

        has_content = any([
            exercise_data.titre,
            exercise_data.enonce,
            exercise_data.forme,
            exercise_data.construction,
            exercise_data.evaluation,
        ])
        if not has_content:
            raise HTTPException(
                status_code=422,
                detail="L'exercice ne contient aucun contenu exploitable pour la génération PLE. "
                       "Veuillez remplir au moins le titre, l'énoncé ou le formulaire."
            )

        ple_content = workspace_service.from_json_to_ple(exercise_data)
        logger.info(f"Generated PLE content length: {len(ple_content)} characters")
        return PleContentResponse(ple_content=ple_content)

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la génération du contenu PLE: {str(e)}"
        )


@router.get("/users/me", response_model=PlatonUser)
async def get_current_user_profile(
    session_id: str = Depends(require_session_id),
    redis: Redis = Depends(get_redis),
) -> PlatonUser:
    session_data = await auth_service.get_session_user(redis, session_id)
    if not session_data:
        raise HTTPException(status_code=401, detail="Session expired")
    user_token = session_data.get("platon_access")
    username = session_data.get("username")
    if not user_token or not username:
        raise HTTPException(status_code=401, detail="Incomplete session data")
    try:
        return await platon_service.get_user_profile(username, user_token)
    except SandboxError as e:
        logger.error("Failed to fetch user profile for %s: %s", username, e)
        raise HTTPException(status_code=502, detail=f"Could not fetch user profile from PLaTon: {e}")


