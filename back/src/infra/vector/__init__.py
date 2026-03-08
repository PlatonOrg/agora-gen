from src.infra.vector.models import (
    ExerciseMetadata,
    ExerciseParts,
    ExerciseResource,
    FilledTemplateParameter,
    TemplateParameter,
    TemplateResource,
)
from src.infra.vector.vector_utils import validate_table_name, physical_table_name
from src.infra.vector.sync_tracker import get_last_sync, set_last_sync, ensure_sync_tracker_table
from src.infra.vector.exercise_vector_service import ensure_populated as ensure_exercise_vectors_populated
from src.infra.vector.exercise_vector_service import run_incremental_sync as run_exercise_vector_sync
from src.infra.vector.exercise_vector_service import run_full_rebuild as rebuild_exercise_vectors
from src.infra.vector.exercise_vector_service import run_from_prefetched as run_exercise_vectors_from_prefetched
from src.infra.vector.platon_docs_vector_service import ensure_populated as ensure_platon_docs_populated

__all__ = [
    "ExerciseMetadata",
    "ExerciseParts",
    "ExerciseResource",
    "FilledTemplateParameter",
    "TemplateParameter",
    "TemplateResource",
    "validate_table_name",
    "physical_table_name",
    "get_last_sync",
    "set_last_sync",
    "ensure_sync_tracker_table",
    "ensure_exercise_vectors_populated",
    "run_exercise_vector_sync",
    "rebuild_exercise_vectors",
    "run_exercise_vectors_from_prefetched",
    "ensure_platon_docs_populated",
]
