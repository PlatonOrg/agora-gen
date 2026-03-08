#!/usr/bin/env python3

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

script_dir = Path(__file__).resolve().parent
back_dir = script_dir.parent.parent
project_root = back_dir.parent
sys.path.insert(0, str(back_dir))

os.chdir(project_root)

from src.core.logging_config import setup_logging
from src.core import path_constants

log_dir = script_dir / "results" / "logs"
logger = setup_logging("benchmark", log_dir=log_dir)

from src.workflows.workflow import handle_chat
from src.services.models.api import ChatRequest, ExerciseData, ChatMessage
from src.services.rag.retrieval_service import retrieval_service, initialize_rag_service
from src.services.rag.embedding_types import EmbeddingKind
from src.core.config_app import settings


RAG_TOP_K = 10


class TestRunner:
    """Handles running tests and collecting results."""

    def __init__(self, provider: Optional[str] = None, model: Optional[str] = None, user_token: Optional[str] = None, skip_llm: bool = False, output_dir: Optional[Path] = None):
        from src.core.di import get_llm_registry

        self._registry = get_llm_registry()

        effective_provider = provider or self._registry.default_provider_name
        if effective_provider not in self._registry.registered_names:
            raise ValueError(
                f"Provider '{effective_provider}' is not registered. "
                f"Available: {self._registry.registered_names}"
            )

        if provider is None and model is None:
            self.provider = effective_provider
            self.model = self._registry.default_model_for(self.provider)
        else:
            self.provider = effective_provider
            if model:
                self._registry._default_models[self.provider] = model
                logger.info("Using model: %s", model)
            elif effective_provider == "ollama":
                raise ValueError("When using ollama provider, you must specify a model with --model")
            self.model = self._registry.default_model_for(self.provider)

        self._registry._default_provider_name = self.provider

        self.user_token = user_token or settings.TEMP_PLATON_API_TOKEN
        if not self.user_token:
            raise ValueError("TEMP_PLATON_API_TOKEN not found in environment and not provided via argument")

        logger.info("Using provider: %s", self.provider)
        logger.info("Test runner initialized with provider=%s, model=%s", self.provider, self.model)

        self.skip_llm = skip_llm
        self.output_dir = output_dir

    async def run_test_case(self, test_case: Dict[str, Any], parent_exercise_data: Optional[ExerciseData] = None) -> Dict[str, Any]:
        """
        Run a single test case.

        Args:
            test_case: Test case dictionary from JSON file.
            parent_exercise_data: Exercise data from parent test case (for regeneration).

        Returns:
            Dictionary containing RAG results and LLM generation results.
        """
        request = test_case.get("request", "")
        fichiers = test_case.get("fichiers", "non")
        selected_components = test_case.get("composants", [])

        # Skip test cases with files for now
        if fichiers == "oui":
            logger.info(f"Skipping test case with files: {request[:50]}...")
            return None

        logger.info(f"Running test case: {request[:80]}...")

        result = {
            "test_case": {
                "request": request,
                "langue": test_case.get("langue"),
                "domaine": test_case.get("domaine"),
                "difficulté": test_case.get("difficulté"),
                "détail": test_case.get("détail"),
                "composants": selected_components,
                "type": test_case.get("type"),
                "has_parent": parent_exercise_data is not None
            },
            "rag_search": {},
            "llm_generation": {}
        }

        # Phase 1: RAG Search (only if no parent - first request)
        if parent_exercise_data is None:
            try:
                result["rag_search"] = await self._run_rag_search(request, test_case.get("expected_result"))
            except Exception as e:
                logger.exception(f"RAG search failed: {e}")
                result["rag_search"]["error"] = str(e)
        else:
            result["rag_search"] = {"skipped": "regeneration case - using parent exercise"}

        # Phase 2: LLM Generation
        if not self.skip_llm:
            try:
                result["llm_generation"] = await self._run_llm_generation(test_case, parent_exercise_data)
            except Exception as e:
                logger.exception(f"LLM generation failed: {e}")
                result["llm_generation"]["error"] = str(e)
        else:
            result["llm_generation"] = {"skipped": True}

        # Return result along with the exercise data for child regenerations
        return result

    async def _run_rag_search(self, request: str, expected_results: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        start_time = time.time()

        query = request
        results_by_kind = retrieval_service.retrieve_all_kinds_separately(query=query, top_k=RAG_TOP_K)

        elapsed_time = time.time() - start_time

        def chunk_to_dict(chunk: Any) -> Dict[str, Any]:
            """Convert a RetrievedChunk to a dictionary."""
            meta = chunk.metadata or {}
            base_info = {
                "id": meta.get("id") or meta.get("platon_id") or meta.get("resource_id") or meta.get("db_id"),
                "name": meta.get("name") or meta.get("title") or None,
                "score": chunk.score,
                "kind": chunk.doc_type
            }

            # Add extra metadata fields commonly present
            if meta.get("platon_id"):
                base_info["platon_id"] = meta.get("platon_id")
            if meta.get("db_id"):
                base_info["db_id"] = meta.get("db_id")
            if meta.get("resource_id"):
                base_info["resource_id"] = meta.get("resource_id")
            if meta.get("type"):
                base_info["type"] = meta.get("type")
            if meta.get("tag"):
                base_info["tag"] = meta.get("tag")
            if meta.get("template_id"):
                base_info["template_id"] = meta.get("template_id")
            if meta.get("template_name"):
                base_info["template_name"] = meta.get("template_name")

            return base_info

        # Convert all results to dictionaries
        all_results = [chunk_to_dict(chunk) for chunk in results_by_kind["all"]]
        components = [chunk_to_dict(chunk) for chunk in results_by_kind["components"]]
        templates = [chunk_to_dict(chunk) for chunk in results_by_kind["templates"]]
        exercises = [chunk_to_dict(chunk) for chunk in results_by_kind["exercises"]]
        template_exos = [chunk_to_dict(chunk) for chunk in results_by_kind["template_exos"]]

        # Identify which examples would be used (top 3 from overall results)
        identified_examples = []
        for chunk in results_by_kind["all"][:3]:
            meta = chunk.metadata or {}
            example_info = {
                "id": meta.get("id") or meta.get("platon_id") or meta.get("resource_id") or meta.get("db_id"),
                "name": meta.get("name") or meta.get("title"),
                "kind": chunk.doc_type,
                "score": chunk.score
            }
            if chunk.doc_type == EmbeddingKind.TEMPLATE.value:
                example_info["platon_id"] = meta.get("platon_id") or meta.get("resource_id")
            if chunk.doc_type == EmbeddingKind.TEMPLATE_EXO.value:
                example_info["template_id"] = meta.get("template_id")
                example_info["template_name"] = meta.get("template_name")
            identified_examples.append(example_info)

        rag_score = self._calculate_rag_score(expected_results, results_by_kind)

        return {
            "search_input": query,
            "elapsed_time_seconds": elapsed_time,
            "all_results": all_results,
            "top_10_per_kind": {
                "components": components,
                "templates": templates,
                "exercises": exercises,
                "template_exos": template_exos
            },
            "identified_examples": identified_examples,
            "rag_score": rag_score
        }

    def _calculate_rag_score(self, expected_results: Optional[List[Dict[str, Any]]], results_by_kind: Dict[str, List[Any]]) -> Optional[Dict[str, Any]]:
        if not expected_results:
            return None

        expected_ids = set()
        for exp in expected_results:
            exp_id = exp.get("id")
            if exp_id:
                expected_ids.add(exp_id)

        found_count = 0
        for chunk in results_by_kind["all"][:RAG_TOP_K]:
            meta = chunk.metadata or {}
            chunk_id = meta.get("id") or meta.get("platon_id") or meta.get("resource_id") or meta.get("db_id")
            if chunk_id in expected_ids:
                found_count += 1

        total_expected = len(expected_ids)
        if total_expected > 0:
            percentage = (found_count / total_expected) * 100
            return {
                "found": found_count,
                "total_expected": total_expected,
                "percentage": round(percentage, 2)
            }
        return None

    async def _run_llm_generation(self, test_case: Dict[str, Any], parent_exercise_data: Optional[ExerciseData] = None) -> Dict[str, Any]:
        """
        Run LLM generation and collect results.

        Args:
            test_case: The test case data.
            parent_exercise_data: Exercise data from parent test (for regeneration).

        Returns:
            Dictionary containing LLM generation results.
        """
        start_time = time.time()

        # Extract fields from test_case
        request = test_case.get("request", "")
        selected_components = test_case.get("composants", [])
        conversation_history = test_case.get("conversation_history", [])

        # Create exercise data - use parent if available, otherwise start fresh
        if parent_exercise_data:
            exercise_data = parent_exercise_data
        else:
            exercise_data = ExerciseData()

        # Create chat request
        chat_request = ChatRequest(
            exercise_state=exercise_data,
            user_request=request,
            user_selected_components=selected_components,
            conversation_history=conversation_history
        )

        # Capture generation input details
        generation_input = {
            "user_request": request,
            "selected_components": selected_components,
            "conversation_history": conversation_history
        }

        # Record exercise state details
        if exercise_data.components:
            generation_input["selected_components"] = exercise_data.components
        if exercise_data.template_id:
            generation_input["template_id"] = exercise_data.template_id
        if exercise_data.config_variables:
            generation_input["has_config_variables"] = True
            generation_input["config_variable_names"] = [
                var.get("name") for var in exercise_data.config_variables.get("inputs", [])
            ] if "inputs" in exercise_data.config_variables else []

        # Record current exercise parts
        exercise_parts = {}
        if exercise_data.titre:
            exercise_parts["titre"] = exercise_data.titre
        if exercise_data.enonce:
            exercise_parts["has_enonce"] = True
        if exercise_data.forme:
            exercise_parts["has_forme"] = True
        if exercise_data.sandbox:
            exercise_parts["has_sandbox"] = True
        if exercise_data.construction:
            exercise_parts["has_construction"] = True
        if exercise_data.evaluation:
            exercise_parts["has_evaluation"] = True
        if exercise_data.sandbox_variables:
            exercise_parts["sandbox_variable_names"] = list(exercise_data.sandbox_variables.keys())

        if exercise_parts:
            generation_input["exercise_data"] = exercise_parts

        # Call handle_chat
        response = await handle_chat(chat_request, self.user_token)

        elapsed_time = time.time() - start_time

        # Extract generation output
        generation_output = {
            "elapsed_time_seconds": elapsed_time,
            "error": None,
        }

        if response.error:
            generation_output["error"] = response.error
            generation_output["response_exercise_data"] = None
        else:
            # Record the processed output
            if response.exercise_data:
                ple_content = None
                if response.exercise_data.template_id:
                    # Template-based exercise
                    generation_output["type"] = "template"
                    generation_output["template_id"] = response.exercise_data.template_id
                    if response.exercise_data.config_variables and "inputs" in response.exercise_data.config_variables:
                        generation_output["config_variables"] = {
                            var["name"]: var["value"]
                            for var in response.exercise_data.config_variables["inputs"]
                        }
                else:
                    # Pure exercise
                    generation_output["type"] = "pure_exercise"
                    # Get PLE content
                    from src.services.workspace_service import workspace_service
                    ple_content = workspace_service.from_json_to_ple(response.exercise_data)
                    generation_output["ple_content"] = ple_content
            else:
                generation_output["response_exercise_data"] = None

            if response.url:
                generation_output["preview_url"] = response.url
                generation_output["preview_success"] = True
            else:
                generation_output["preview_success"] = False

            generation_output["message"] = response.message

        return {
            "input": generation_input,
            "output": generation_output
        }

    async def _run_test_case_recursive(self, test_case: Dict[str, Any], parent_exercise_data: Optional[ExerciseData] = None) -> Dict[str, Any]:
        """
        Recursively run a test case and its children (regeneration chain).

        Args:
            test_case: Test case dictionary from JSON file.
            parent_exercise_data: Exercise data from parent test (for regeneration).

        Returns:
            Dictionary containing test results including nested children.
        """
        # Run current test case
        result = await self.run_test_case(test_case, parent_exercise_data)

        if result is None:
            return None

        # Get the exercise data from this run for children
        current_exercise_data = None
        if result.get("llm_generation", {}).get("output", {}).get("response_exercise_data"):
            current_exercise_data = result["llm_generation"]["output"]["response_exercise_data"]

        # Check if there's a child (exercice_original means this test has a child)
        exercice_original = test_case.get("exercice_original")
        if exercice_original and current_exercise_data:
            # Run the child test case recursively
            child_result = await self._run_test_case_recursive(exercice_original, current_exercise_data)
            if child_result:
                result["child_regeneration"] = child_result

        # Clean up - remove the exercise data object from output (not JSON serializable)
        if "llm_generation" in result and "output" in result["llm_generation"]:
            if "response_exercise_data" in result["llm_generation"]["output"]:
                del result["llm_generation"]["output"]["response_exercise_data"]

        return result

    async def run_test_file(self, test_file_path: Path) -> List[Dict[str, Any]]:
        """
        Run all test cases from a JSON file.

        Args:
            test_file_path: Path to JSON file containing test cases.

        Returns:
            List of test results.
        """
        logger.info(f"Loading test file: {test_file_path}")

        with open(test_file_path, 'r', encoding='utf-8-sig') as f:
            test_cases = json.load(f)

        if not isinstance(test_cases, list):
            raise ValueError(f"Test file must contain a JSON array, got {type(test_cases)}")

        results = []
        for i, test_case in enumerate(test_cases):
            logger.info(f"Running test case {i+1}/{len(test_cases)}")
            # Run test case recursively to handle regeneration chains
            result = await self._run_test_case_recursive(test_case)
            if result:  # Only add if not skipped
                results.append(result)

        return results

    async def run_tests(self, test_path: Optional[Path] = None) -> Dict[str, Any]:
        """
        Run tests from specified path.

        Args:
            test_path: Path to test file or directory. If None, runs all tests.

        Returns:
            Dictionary containing all test results grouped by file.
        """
        tests_base_dir = path_constants.TESTS_DIR

        if test_path is None:
            # Run all tests in all subdirectories
            logger.info("Running all tests from all folders")
            test_files = list(tests_base_dir.rglob("*.json"))
        elif test_path.is_file():
            # Run single file
            test_files = [test_path]
        elif test_path.is_dir():
            # Run all JSON files in directory
            test_files = list(test_path.glob("*.json"))
        else:
            raise ValueError(f"Test path does not exist: {test_path}")

        if not test_files:
            raise ValueError(f"No test files found at: {test_path}")

        logger.info(f"Found {len(test_files)} test file(s) to run")

        all_results = {
            "metadata": {
                "provider": self.provider,
                "model": self.model,
                "temperature": os.environ.get("TEMP_GENERATION", "0.0"),
                "timestamp": datetime.now().isoformat(),
                "total_files": len(test_files),
                "skip_llm": self.skip_llm
            },
            "files": {}
        }

        for test_file in test_files:
            file_key = str(test_file.relative_to(tests_base_dir))
            logger.info(f"Processing file: {file_key}")

            try:
                results = await self.run_test_file(test_file)
                all_results["files"][file_key] = {
                    "total_cases": len(results),
                    "results": results
                }
            except Exception as e:
                logger.exception(f"Failed to process file {file_key}: {e}")
                all_results["files"][file_key] = {
                    "error": str(e)
                }

        # Save results if output_dir is set
        if self.output_dir:
            self.save_results(all_results, self.output_dir)

        return all_results

    def save_results(self, results: Dict[str, Any], output_dir: Path):
        """
        Save test results to JSON file.

        Args:
            results: Test results dictionary.
            output_dir: Directory to save results to.
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename with timestamp and provider
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.provider}_{timestamp}.json"
        output_path = output_dir / filename

        logger.info(f"Saving results to: {output_path}")

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        logger.info(f"Results saved successfully")


def print_usage():
    """Print usage information."""
    usage = """
Usage: python run_tests.py [OPTIONS]

Run tests from the tests folder and log RAG search and LLM generation results.

Options:
  -h, --help                Show this help message and exit
  -f, --folder FOLDER       Run tests from specific folder (e.g., tests/adele)
  -j, --json FILE           Run tests from specific JSON file
  -p, --provider PROVIDER   LLM provider (ollama, ragustave, gemini, groq). Default: use config.
  -m, --model MODEL         Model name. Default: use provider default. Required for ollama.
  -o, --output DIR          Name of the output subdirectory inside results/tests. If not provided, saves in results/tests
  --table TABLE             Table name for RAG service
  --embed-model MODEL       Embedding model name to use for RAG queries
  --embed-dim DIM           Embedding dimension for the model
  --skip-llm                Skip LLM generation, only perform RAG search

Examples:
  # Run all tests with default provider/model
  python run_tests.py

  # Run tests from specific folder
  python run_tests.py --folder tests/adele

  # Run specific test file
  python run_tests.py --json tests/adele/test2_Regeneration.json

  # Run with specific provider and model
  python run_tests.py --provider ollama --model llama3.1

  # Run with Gemini
  python run_tests.py --provider gemini
  
  # Run with specific embedding model and table
  python run_tests.py --table my_table --embed-model BAAI/bge-m3 --embed-dim 1024
"""
    print(usage)


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run tests from the tests folder",
        add_help=False
    )
    parser.add_argument('-h', '--help', action='store_true', help='Show help message')
    parser.add_argument('-f', '--folder', type=str, help='Test folder path (relative to tests/)')
    parser.add_argument('-j', '--json', type=str, help='Test JSON file path')
    parser.add_argument('-p', '--provider', type=str, help='LLM provider (must be registered in resources/llm_providers.json)')
    parser.add_argument('-m', '--model', type=str, help='Model name')
    parser.add_argument('-o', '--output', type=str, help='Name of the output subdirectory inside results/tests. If not provided, saves in results/tests')
    parser.add_argument('--table', type=str, help='Table name for RAG service')
    parser.add_argument('--skip-llm', action='store_true', help='Skip LLM generation, only perform RAG search')
    parser.add_argument('--embed-model', type=str, help='Embedding model name to use for RAG queries')
    parser.add_argument('--embed-dim', type=int, help='Embedding dimension for the model')

    args = parser.parse_args()

    if args.help:
        print_usage()
        return

    # Determine test path
    test_path = None
    tests_base_dir = path_constants.TESTS_DIR

    if args.json:
        candidate = Path(args.json)
        if candidate.is_absolute():
            test_path = candidate
        else:
            candidates = [tests_base_dir / candidate, Path(os.getcwd()) / candidate]
            test_path = next((p for p in candidates if p.exists()), None)
            if test_path is None:
                tried = " | ".join(str(p) for p in candidates)
                logger.error("Test file not found. Tried: %s", tried)
                sys.exit(1)
    elif args.folder:
        candidate = Path(args.folder)
        if candidate.is_absolute():
            test_path = candidate
        else:
            candidates = [tests_base_dir / candidate, Path(os.getcwd()) / candidate]
            test_path = next((p for p in candidates if p.exists()), None)
            if test_path is None:
                tried = " | ".join(str(p) for p in candidates)
                logger.error("Test folder not found. Tried: %s", tried)
                sys.exit(1)

    # Determine output directory
    if args.output:
        output_dir = script_dir / "results" / "tests" / args.output
    else:
        output_dir = script_dir / "results" / "tests"

    try:
        # Set embedding dimension if provided
        if args.embed_dim:
            settings.EMBED_DIM = args.embed_dim
            logger.info(f"Using embedding dimension: {args.embed_dim}")

        # Initialize RAG service
        logger.info("Initializing RAG service...")
        if args.table:
            initialize_rag_service(table_name=args.table, model_name=args.embed_model)
        else:
            initialize_rag_service(model_name=args.embed_model)

        # Initialize test runner
        runner = TestRunner(provider=args.provider, model=args.model, skip_llm=args.skip_llm)

        # Run tests
        results = await runner.run_tests(test_path)

        # Save results
        runner.save_results(results, output_dir)

        logger.info("Test run completed successfully!")

    except Exception as e:
        logger.exception(f"Test run failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

