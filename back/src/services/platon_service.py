import httpx
import logging
from typing import Optional, List, Dict, Any
from src.services.models.platon import (
    ExerciseState,
    SandboxError,
    SandboxRuntimeError,
    PlatonLogEntry,
    PreviewResult,
    EvaluateResult,
    EvaluateFeedback,
    PublishExerciseRequest,
    PublishExerciseResponse,
    PlatonUser,
)

logger = logging.getLogger("uvicorn")


class PlatonService:
    """
    Async Service to interact with the Platon API.
    """

    def __init__(
        self,
        base_url: str,
        player_url: str,
        timeout: float,
        token: Optional[str] = None,
    ) -> None:
        self._base_url = base_url
        self._player_url = player_url
        self._timeout = timeout
        self.token = token or ""
        self.headers = {
            "Content-Type": "application/json"
        }
        if self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"

        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers=self.headers,
            timeout=self._timeout,
        )

    async def _request(self, method: str, endpoint: str, json_data: dict | None = None, params: dict | None = None) -> dict:
        """Internal helper for async requests with error handling."""
        try:
            response = await self._client.request(
                method,
                endpoint,
                json=json_data,
                params=params
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error("Platon API Error %s: %s", e.response.status_code, e.response.text)
            try:
                payload = e.response.json()
            except Exception:
                payload = {"text": e.response.text}
            raise SandboxError(f"API Error {e.response.status_code}", payload)
        except Exception as e:
            logger.error("Platon Connection Error: %s", e)
            raise SandboxError(f"Connection failed: {e}")

    async def _request_with_token(self, method: str, endpoint: str, token: str = None, json_data: dict | None = None, params: dict | None = None) -> dict:
        """Internal helper for async requests with a specific user token."""
        # Use provided token, otherwise fall back to global token
        auth_token = token or self.token

        headers = {"Content-Type": "application/json"}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        async with httpx.AsyncClient(
                base_url=self._base_url,
                headers=headers,
                timeout=self._timeout,
        ) as client:
            try:
                response = await client.request(
                    method,
                    endpoint,
                    json=json_data,
                    params=params
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error("Platon API Error %s: %s", e.response.status_code, e.response.text)
                try:
                    payload = e.response.json()
                except Exception:
                    payload = {"text": e.response.text}
                raise SandboxError(f"API Error {e.response.status_code}", payload)
            except Exception as e:
                logger.error("Platon Connection Error: %s", e)
                raise SandboxError(f"Connection failed: {e}")

    def _extract_exercise_state(self, evaluate_data: dict, preview_url: str = None) -> ExerciseState:
        """Parses the raw JSON response into a clean Pydantic model."""
        exercise = evaluate_data.get("exercise", {})
        session_id = exercise.get("sessionId", "")

        raw_logs = exercise.get("platon_logs", [])
        platon_logs: List[PlatonLogEntry] = []
        for entry in raw_logs:
            if isinstance(entry, dict) and "message" in entry and "type" in entry:
                platon_logs.append(
                    PlatonLogEntry(message=entry["message"], type=entry["type"])
                )

        return ExerciseState(
            session_id=session_id,
            title=exercise.get("title"),
            statement=exercise.get("statement"),
            form=exercise.get("form"),
            preview_url=preview_url,
            platon_logs=platon_logs,
        )

    def _build_files(self, **sources: str | None) -> list[dict]:
        """Helper to build files list from source parameters."""
        return [
            {"path": f"main.{ext}", "content": content}
            for ext, content in sources.items()
            if content
        ]

    # --- Public Methods ---

    async def check_resource_exists(self, resource_id: str) -> bool:
        try:
            await self._request("GET", f"/resources/{resource_id}")
            return True
        except SandboxError:
            return False

    async def create_exercise_preview(self, ple: str | None = None, plo: str = None, plc: str = None) -> PreviewResult:
        files = self._build_files(ple=ple, plo=plo, plc=plc)

        # 1. Request Preview Creation
        preview_data = await self._request("POST", "/resources/preview", json_data={"files": files})

        if not preview_data.get("success"):
            raise SandboxError("Preview creation failed", preview_data)

        resource = preview_data.get("resource", {})
        resource_id = resource.get("id")

        if not resource_id:
            raise SandboxError("No resource ID returned", preview_data)

        # 2. Evaluate
        evaluate_payload = {"resource": resource_id, "version": "latest"}
        evaluate_data = await self._request("POST", "/player/preview", json_data=evaluate_payload)

        if evaluate_data.get("success") is False:
            raise SandboxError("Sandbox evaluation failed", evaluate_data)

        # Construct the User-Facing URL
        user_preview_url = f"{self._player_url}/{resource_id}?version=latest&editor-preview"

        preview_result = PreviewResult(
            state=self._extract_exercise_state(evaluate_data, preview_url=user_preview_url),
            resource_id=resource_id,
        )

        # A 200 response does not guarantee a healthy preview: the Platon sandbox
        # can still report Python/JS runtime errors via `platon_logs`.  We treat
        # those exactly like compilation failures so the retry-with-LLM-correction
        # loop can attempt a fix.
        if preview_result.state.has_runtime_errors:
            error_summary = "; ".join(
                entry.message for entry in preview_result.state.runtime_error_logs
            )
            logger.warning(
                "Sandbox runtime error(s) detected in platon_logs for resource %s: %s",
                resource_id,
                error_summary,
            )
            raise SandboxRuntimeError(preview_result.state.runtime_error_logs)

        return preview_result

    async def evaluate_exercise(self, session_id: str) -> EvaluateResult:
        payload = {
            "answers": {},
            "action": "CHECK_ANSWER",
            "sessionId": session_id,
        }
        data = await self._request("POST", "/player/evaluate", json_data=payload)

        exercise = data.get("exercise")
        if exercise is None:
            logger.warning(
                "evaluate_exercise: Platon response missing 'exercise' key for session %s — treating as no errors. Raw: %s",
                session_id,
                str(data)[:500],
            )
            return EvaluateResult(session_id=session_id)

        raw_feedbacks = exercise.get("feedbacks", [])
        logger.info(f"evaluate_exercise: Received {len(raw_feedbacks)} feedback entries for session {session_id} : {str(raw_feedbacks)}")
        feedbacks = [
            EvaluateFeedback(
                content=fb.get("content", ""),
                type=fb.get("type", "info"),
            )
            for fb in raw_feedbacks
            if isinstance(fb, dict)
        ]

        raw_logs = exercise.get("platon_logs", [])
        logger.info(f"evaluate_exercise: Received {len(raw_logs)} platon_logs for session {session_id} : {str(raw_logs)}")
        platon_logs: List[PlatonLogEntry] = [
            PlatonLogEntry(message=entry["message"], type=entry["type"])
            for entry in raw_logs
            if isinstance(entry, dict) and "message" in entry and "type" in entry
        ]

        result = EvaluateResult(
            session_id=exercise.get("sessionId", session_id),
            title=exercise.get("title"),
            form=exercise.get("form"),
            feedbacks=feedbacks,
            platon_logs=platon_logs,
        )

        if result.has_runtime_errors:
            error_summary = "; ".join(entry.message for entry in result.runtime_error_logs)
            logger.warning(
                "Grader runtime error(s) detected in evaluate platon_logs for session %s: %s",
                session_id,
                error_summary,
            )
            raise SandboxRuntimeError(result.runtime_error_logs, source="grader")

        return result

    async def get_cercle_tree(self, token: str = None) -> Dict[str, Any]:
        return await self._request_with_token("GET", "/resources/tree", token)

    async def get_ready_exercises(
        self,
        offset: int = 0,
        limit: Optional[int] = 50,
        configurable: Optional[bool] = None,
        token: Optional[str] = None,
        period: Optional[int] = None,
    ) -> List[Dict[str, Any]]:

        def build_params(with_limit: bool) -> dict[str, Any]:
            params: dict[str, Any] = {
                "types": "EXERCISE",
                "status": "READY",
                "order": "UPDATED_AT",
                "direction": "DESC",
                "offset": offset,
            }
            if with_limit and limit is not None:
                params["limit"] = limit
            if configurable is not None:
                params["configurable"] = str(configurable).lower()
            if period is not None:
                params["period"] = period
            return params

        if token:
            client = httpx.AsyncClient(
                base_url=self._base_url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                },
                timeout=self._timeout,
            )
            close_client = True
        else:
            client = self._client
            close_client = False

        try:
            response = await client.get("/resources", params=build_params(with_limit=True))
            if response.status_code == 400 and limit is not None:
                response = await client.get("/resources", params=build_params(with_limit=False))
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or not payload.get("success", True):
                return []
            return payload.get("resources", []) or []
        finally:
            if close_client:
                await client.aclose()

    async def get_file_content(
        self,
        resource_id: str,
        filename: str,
        version: str = "latest",
        token: Optional[str] = None,
    ) -> str:
        auth_token = token or self.token
        headers = {"Content-Type": "application/json"}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        async with httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            timeout=self._timeout,
        ) as client:
            response = await client.get(
                f"/files/{resource_id}/{filename}",
                params={"version": version},
            )
            response.raise_for_status()
            return response.text

    async def compile_resource_json(
        self,
        resource_id: str,
        token: Optional[str] = None,
    ) -> Dict[str, Any]:
        auth_token = token or self.token
        headers = {"Content-Type": "application/json"}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        async with httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            timeout=self._timeout,
        ) as client:
            response = await client.post(f"/files/compile/{resource_id}/json")
            response.raise_for_status()
            return response.json()

    async def create_exercise(self, exercise_data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/resources", json_data=exercise_data)

    async def close(self):
        await self._client.aclose()

    async def get_filtered_resources(
        self,
        types: str,
        status: str = "READY",
        configurable: bool | None = None,
        topics: List[str] | None = None,
        levels: List[str] | None = None,
        parents: List[str] | None = None,
        token: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"types": types, "status": status}
        if configurable is not None:
            params["configurable"] = str(configurable).lower()
        if topics:
            params["topics"] = topics
        if levels:
            params["levels"] = levels
        if parents:
            params["parents"] = parents
        if search:
            params["search"] = search
        params["limit"] = limit

        response = await self._request_with_token(
            method="GET",
            endpoint="/resources",
            token=token,
            params=params,
        )

        if not isinstance(response, dict):
            return []
        return response.get("resources", [])

    async def get_resource(self, resource_id: str, token: str | None = None) -> Dict[str, Any]:
        data = await self._request_with_token(
            method="GET",
            endpoint=f"/resources/{resource_id}",
            token=token,
        )
        if not isinstance(data, dict):
            raise RuntimeError(f"Invalid Platon response: {data}")
        if not data.get("success", True):
            raise RuntimeError(f"Platon API error: {data}")
        return data.get("resource", data)

    def generate_ple_content(self, template_id: str) -> str:
        return f"@extends /{template_id}:latest/main.ple"

    async def extract_exercise_components(self, exercise_id: str, token: str = None, compiled_json: Optional[Dict[str, Any]] = None) -> List[str]:
        """
        Extract component names from an exercise by compiling it to JSON and
        looking for variables that contain components (objects with 'cid' property).
        Returns a list of component selector names.
        """
        try:
            if compiled_json is None:
                # Compile the exercise to JSON
                compiled_data = await self.compile_resource_json(
                    resource_id=exercise_id,
                    token=token
                )
            else:
                compiled_data = compiled_json

            components = []
            variables = compiled_data.get("variables", {})

            # Iterate through variables to find components
            for var_name, var_value in variables.items():
                if isinstance(var_value, dict) and "cid" in var_value and "selector" in var_value:
                    selector = var_value.get("selector", "")
                    if selector:
                        components.append(selector)

            return components

        except Exception as e:
            logger.error(f"Error extracting components from exercise {exercise_id}: {e}")
            return []

    async def publish_exercise(self, request: PublishExerciseRequest, token: str) -> PublishExerciseResponse:
        data = await self._request_with_token("POST", "/resources", token=token, json_data=request.model_dump(exclude_none=True))
        resource = data.get("resource", data)
        resource_id = resource.get("id")
        if not resource_id:
            raise SandboxError("Platon did not return a resource id after publish", data)
        return PublishExerciseResponse(id=resource_id)

    async def get_user_profile(self, username: str, token: str) -> PlatonUser:
        data = await self._request_with_token("GET", f"/users/{username}", token=token)
        resource = data.get("resource")
        if not resource:
            raise SandboxError("Platon did not return a user resource", data)
        return PlatonUser(
            id=resource["id"],
            username=resource["username"],
            firstName=resource.get("firstName"),
            lastName=resource.get("lastName"),
            email=resource.get("email"),
            role=resource.get("role"),
            active=resource.get("active"),
            hasPassword=resource.get("hasPassword"),
            createdAt=resource.get("createdAt"),
            updatedAt=resource.get("updatedAt"),
            lastLogin=resource.get("lastLogin"),
            firstLogin=resource.get("firstLogin"),
            lastActivity=resource.get("lastActivity"),
            discordId=resource.get("discordId"),
        )

    async def get_topics(self, token: Optional[str] = None) -> List[Dict[str, Any]]:
        used_token = token or self.token
        data = await self._request_with_token("GET", "/topics", token=used_token)
        if not isinstance(data, dict):
            return []
        return data.get("resources", [])

    async def get_levels(self, token: Optional[str] = None) -> List[Dict[str, Any]]:
        used_token = token or self.token
        data = await self._request_with_token("GET", "/levels", token=used_token)
        if not isinstance(data, dict):
            return []
        return data.get("resources", [])

def _create_platon_service() -> PlatonService:
    """Build the module-level singleton from settings (composition boundary)."""
    from src.core.config_app import settings
    return PlatonService(
        base_url=settings.PLATON_BASE_URL,
        player_url=settings.PLATON_PLAYER_URL,
        timeout=settings.PLATON_TIMEOUT_SECONDS,
        token=settings.PLATON_API_TOKEN,
    )


platon_service = _create_platon_service()
