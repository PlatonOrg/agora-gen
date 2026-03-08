import json
import os
from datetime import datetime
from typing import Dict, Any, Optional, List
import tiktoken

from src.core import path_constants


def _debug_log_path(*subdirs: str) -> str:
    """Build and ensure a debug log subdirectory under path_constants.DEBUG_LOG_DIR."""
    path = os.path.join(path_constants.DEBUG_LOG_DIR, *subdirs)
    os.makedirs(path, exist_ok=True)
    return path


def count_tokens(text: str) -> int:
    """Count the number of tokens in the given text using tiktoken."""
    encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))

def log_llm_call(inputs: Dict[str, Any], response: Optional[Dict[str, Any]] = None, exception: Optional[Exception] = None) -> None:
    """
    Logs the inputs and response of an LLM call to a JSON file.
    Creates a new JSON file for each call with a timestamp.
    """
    log_dir = _debug_log_path("llm_calls")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{log_dir}/llm_call_{timestamp}.json"

    log_data = {
        "timestamp": datetime.now().isoformat(),
        "inputs": inputs,
    }
    if exception:
        log_data["exception"] = str(exception)
        log_data["exception_type"] = type(exception).__name__
    else:
        log_data["response"] = response

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)

    # Also save system prompt to a txt file
    txt_filename = filename.replace('.json', '_system_prompt.txt')
    with open(txt_filename, 'w', encoding='utf-8') as f:
        token_count = count_tokens(inputs["system_prompt"])
        f.write(f"Token count: {token_count}\n\n")
        f.write(inputs["system_prompt"])


def save_ple_output(ple_content: str) -> None:
    """
    Saves the PLE output to a txt file.
    """
    ple_dir = _debug_log_path("ple_outputs")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{ple_dir}/ple_output_{timestamp}.txt"

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(ple_content)


def save_examples_used(examples: List[Dict[str, Any]]) -> None:
    """
    Saves the list of examples used for generation to a txt file.
    """
    examples_dir = _debug_log_path("examples_used")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{examples_dir}/examples_used_{timestamp}.txt"

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(f"Examples used for generation ({len(examples)} examples):\n\n")
        for i, example in enumerate(examples, 1):
            example_id = example.get('id', 'unknown')
            example_json = json.dumps(example, indent=2, ensure_ascii=False)
            token_count = count_tokens(example_json)
            f.write(f"Example {i} - ID: {example_id} - Token count: {token_count}\n")
            f.write(example_json)
            f.write("\n\n")


def save_final_exercise_data(exercise_data) -> None:
    """
    Saves the final ExerciseData object after pure generation to a JSON file.
    """
    final_dir = _debug_log_path("final_exercise_data")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{final_dir}/final_exercise_data_{timestamp}.json"

    data_dict = exercise_data.model_dump()

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data_dict, f, ensure_ascii=False, indent=2)
