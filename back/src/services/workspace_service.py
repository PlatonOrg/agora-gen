from typing import List, Dict, Any, Optional
import json
import logging
from src.services.platon_service import platon_service
from src.services.models.api import ComponentInstance, TemplateConfig
from src.services.models.platon import TemplateBasicInfo
from src.infra.llm.llm_call_logger import save_ple_output
from src.core import path_constants

logger = logging.getLogger(__name__)

REQUIRED_FIELDS_MAX_LENGTH = 1000
OTHER_FIELDS_MAX_LENGTH = 500

STANDARD_REQUIRED_FIELDS = {"title", "sandbox", "builder", "grader", "statement", "form", "solution", "hint", "theories"}

COMPONENTS_METADATA = None


def load_components_metadata():
    global COMPONENTS_METADATA
    if COMPONENTS_METADATA is None:
        try:
            with open(path_constants.COMPONENT_METADATA_PATH, 'r', encoding='utf-8') as f:
                COMPONENTS_METADATA = json.load(f)
        except Exception as e:
            logger.error(f"Error loading components metadata: {e}")
            COMPONENTS_METADATA = []
    return COMPONENTS_METADATA


def truncate_string_value(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[:max_length] + "..."


def truncate_compiled_variables(compiled_vars: Dict[str, Any]) -> Dict[str, Any]:
    def truncate_value(value: Any, field_name: str = None) -> Any:
        if field_name and field_name in STANDARD_REQUIRED_FIELDS:
            max_length = REQUIRED_FIELDS_MAX_LENGTH
        else:
            max_length = OTHER_FIELDS_MAX_LENGTH

        if isinstance(value, str):
            return truncate_string_value(value, max_length)
        elif isinstance(value, dict):
            return {k: truncate_value(v, k) for k, v in value.items() if k != "author"}
        elif isinstance(value, list):
            truncated_list = []
            for item in value:
                if isinstance(item, str):
                    truncated_list.append(truncate_string_value(item, max_length))
                elif isinstance(item, dict):
                    truncated_list.append({k: truncate_value(v, k) for k, v in item.items()})
                else:
                    truncated_list.append(item)
            return truncated_list
        else:
            return value

    truncated = {}
    for key, value in compiled_vars.items():
        if key == "author":
            continue
        truncated[key] = truncate_value(value, key)

    return truncated


class WorkspaceService:
    async def get_template_basic_info(self, template_id: str, token: str = None) -> TemplateBasicInfo:
        try:
            resource = await platon_service.get_resource(template_id, token)
            title = resource.get("name", "")
            description = resource.get("desc", "")

            main_plc_text = await platon_service.get_file_content(
                resource_id=template_id,
                filename="main.plc",
                version="latest",
                token=token
            )

            main_plc_content = json.loads(main_plc_text)

            return TemplateBasicInfo(
                title=title,
                description=description,
                main_plc_content=main_plc_content,
            )
        except Exception as e:
            logger.error(f"Error getting basic info for template {template_id}: {e}")
            raise

    async def extract_template_components(self, template_id: str, token: str = None, compiled_json: Optional[Dict[str, Any]] = None) -> List[str]:
        try:
            if compiled_json is None:
                compiled_data = await platon_service.compile_resource_json(
                    resource_id=template_id,
                    token=token
                )
            else:
                compiled_data = compiled_json

            components = []
            variables = compiled_data.get("variables", {})

            for var_name, var_value in variables.items():
                if isinstance(var_value, dict) and "cid" in var_value and "selector" in var_value:
                    selector = var_value.get("selector", "")
                    if selector:
                        components.append(selector)

            return components

        except Exception as e:
            logger.error(f"Error extracting components from template {template_id}: {e}")
            return []

    def _format_value(self, val: Any) -> str:
        if isinstance(val, str):
            return f'"{val}"'
        elif isinstance(val, (list, dict)):
            return json.dumps(val, ensure_ascii=False, indent=2)
        elif isinstance(val, bool):
            return "true" if val else "false"
        else:
            return str(val)

    def _variables_dict_to_ple(self, variables_dict: Dict[str, Any]) -> str:
        ple_lines = []

        for key, value in variables_dict.items():
            if key == "author":
                continue

            if key in ["sandbox", "title", "hint", "theories"]:
                if key in ["hint", "theories"] and (value is None or (isinstance(value, list) and len(value) == 0)):
                    continue
                ple_lines.append(f"{key} = {self._format_value(value)}")

            else:
                ple_lines.append(f"{key} ==\n{value}\n==")

        return "\n".join(ple_lines)

    def from_json_to_ple(self, exercise_data) -> str:
        logger.info(f"Transforming exercise data to PLE: {exercise_data}")
        variables_dict = {}

        if exercise_data.titre:
            variables_dict["title"] = exercise_data.titre
        if exercise_data.enonce:
            variables_dict["statement"] = exercise_data.enonce
        if exercise_data.forme:
            variables_dict["form"] = exercise_data.forme
        if exercise_data.solution:
            variables_dict["solution"] = exercise_data.solution
        if exercise_data.sandbox:
            variables_dict["sandbox"] = exercise_data.sandbox
        if exercise_data.construction:
            variables_dict["builder"] = exercise_data.construction
        if exercise_data.evaluation:
            variables_dict["grader"] = exercise_data.evaluation
        if exercise_data.indications:
            variables_dict["hint"] = exercise_data.indications
        if exercise_data.theories:
            variables_dict["theories"] = exercise_data.theories

        if exercise_data.sandbox_variables:
            variables_dict.update(exercise_data.sandbox_variables)

        base_ple = self._variables_dict_to_ple(variables_dict)

        component_lines = []
        for instance in (exercise_data.component_instances or []):
            component_lines.append(f"{instance.instanceName} = :{instance.selector}")
            for prop_key, prop_value in instance.properties.items():
                component_lines.append(
                    f"{instance.instanceName}.{prop_key} = {self._format_value(prop_value)}"
                )

        parts = [p for p in [base_ple, "\n".join(component_lines)] if p]
        ple_output = "\n".join(parts)
        save_ple_output(ple_output)
        return ple_output

    def transform_compil_variables_to_ple(self, compil_variables: Dict[str, Any]) -> str:
        logger.info(f"Transforming compil_variables to PLE: {compil_variables}")
        return self._variables_dict_to_ple(compil_variables)

    def parse_component_instances_from_sandbox(self, sandbox_variables: Dict[str, Any]) -> List[ComponentInstance]:
        import uuid
        component_instances = []

        if not sandbox_variables:
            return component_instances

        metadata_list = load_components_metadata()
        metadata_by_tag = {comp.get('tag'): comp for comp in metadata_list if comp.get('tag')}

        for var_name, var_value in sandbox_variables.items():
            if isinstance(var_value, dict) and 'selector' in var_value:
                selector = var_value.get('selector')
                metadata = metadata_by_tag.get(selector)

                if not metadata:
                    logger.warning("Unknown component selector '%s' for variable '%s' — skipping", selector, var_name)
                    continue

                properties = {k: v for k, v in var_value.items() if k not in ['cid', 'selector']}
                category = metadata.get('category', 'Widget')

                component_instances.append(ComponentInstance(
                    id=str(uuid.uuid4()),
                    selector=selector,
                    componentName=metadata.get('name', selector),
                    instanceName=var_name,
                    category=category,
                    properties=properties,
                ))

        return component_instances

    def sanitise_exercise_data(self, exercise_data: Any) -> None:
        """Strip component dicts from sandbox_variables and merge them into component_instances.

        Called on any ExerciseData that arrives from the frontend, which may
        still carry component dicts in sandbox_variables alongside (or instead
        of) a fully populated component_instances list.
        """
        if not exercise_data.sandbox_variables:
            return

        mixed_components = self.parse_component_instances_from_sandbox(exercise_data.sandbox_variables)
        if not mixed_components:
            return

        existing_names = {ci.instanceName for ci in exercise_data.component_instances}
        for ci in mixed_components:
            if ci.instanceName not in existing_names:
                exercise_data.component_instances.append(ci)

        exercise_data.sandbox_variables = {
            k: v for k, v in exercise_data.sandbox_variables.items()
            if not (isinstance(v, dict) and 'selector' in v)
        }

    async def get_template_config(self, template_id: str, token: str = None) -> TemplateConfig:
        try:
            basic_info = await self.get_template_basic_info(template_id, token)

            compiled_data = await platon_service.compile_resource_json(
                resource_id=template_id,
                token=token
            )
            variables = compiled_data.get("variables", {})

            logger.info(f"Compiled data for template {template_id}: {compiled_data}")

            components = await self.extract_template_components(template_id, token, compiled_json=compiled_data)

            return TemplateConfig(
                title=basic_info.title,
                description=basic_info.description,
                variables=basic_info.main_plc_content,
                components=components,
                compiled_data=variables
            )
        except Exception as e:
            logger.error(f"Error getting template config for {template_id}: {e}")
            raise


workspace_service = WorkspaceService()
