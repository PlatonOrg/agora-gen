#!/usr/bin/env python3
"""
Benchmark runner.

Vector population for benchmarks must be done beforehand using:
    docker compose exec api python scripts/embedding/populate_exercise_vectors.py

This script only handles Phase 2: running the test suite against a given table.
"""

import argparse
import subprocess
import sys
from pathlib import Path

import torch

script_path = Path(__file__).resolve()
back_dir = script_path.parents[2]
sys.path.insert(0, str(back_dir))

from sentence_transformers import SentenceTransformer


def main(args):
    embed_model = args.embed_model
    provider = args.provider
    llm_model = args.llm
    dimension = args.dimension
    skip_llm = args.skip_llm

    device = "cuda" if torch.cuda.is_available() else "cpu"
    st_model = SentenceTransformer(embed_model, device=device)
    actual_dimension = st_model.get_sentence_embedding_dimension()
    if actual_dimension != dimension:
        print(f"Requested dimension {dimension} differs from model dimension {actual_dimension}. Using {actual_dimension}.")
        dimension = actual_dimension

    safe_embed_name = embed_model.split("/")[-1].replace("-", "_").replace(".", "_").lower()
    table_name = args.table or f"b_{safe_embed_name}_{dimension}"
    output_dir = Path(safe_embed_name)

    print(f"STARTING BENCHMARK — table={table_name}, model={embed_model}")

    cmd = [sys.executable, "scripts/benchmarks/run_tests.py"]
    if args.folder:
        cmd.extend(["-f", args.folder])
    if args.json:
        cmd.extend(["-j", args.json])
    if provider:
        cmd.extend(["-p", provider])
    if llm_model:
        cmd.extend(["-m", llm_model])
    if skip_llm:
        cmd.append("--skip-llm")
    cmd.extend(["-o", str(output_dir)])
    cmd.extend(["--table", table_name])
    cmd.extend(["--embed-model", embed_model])
    cmd.extend(["--embed-dim", str(dimension)])

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Test execution failed: {e}")
        return

    print(f"Benchmark finished. Results saved to: {output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run RAG Benchmark.")
    parser.add_argument("--embed-model", required=True, help="HuggingFace embedding model path or name")
    parser.add_argument("--dimension", type=int, required=True, help="Embedding dimension")
    parser.add_argument("--table", type=str, default=None, help="Vector table name (defaults to auto-generated)")
    parser.add_argument("-f", "--folder", type=str, help="Test folder path")
    parser.add_argument("-j", "--json", type=str, help="Test JSON file path")
    parser.add_argument("--provider", default=None, help="LLM provider name")
    parser.add_argument("--llm", default=None, help="LLM model ID")
    parser.add_argument("--skip-llm", action="store_true", help="Skip LLM generation")
    main(parser.parse_args())
