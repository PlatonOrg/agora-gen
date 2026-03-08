# fullstack
The front and backend of the agora project, the platon exercise generator using AI

## Commands

launch and build all containers

```bash
docker compose up --build -d
```

stop all containers

```bash
docker compose down
```

To access the database inside container, run :

```bash
docker compose exec db psql -U agora -d agora_db
```

To dump database content to a file, run :

```bash
docker compose exec db pg_dump -U agora -d agora_db -f dump.sql
```

To list the models inside ollama

```bash
docker compose exec ollama ollama list
```

## Set up

you will have to do the following things the frist time you launch the backend

- set up the `.env` file
- configure LLM providers in `resources/llm_providers.json`
- set up the database

### LLM Provider Configuration

LLM providers are declared in `resources/llm_providers.json`. Each entry specifies a provider name, kind, credentials, and default model. One entry must have `"default": true` to designate the system-wide active provider.

Example:
```json
[
  {
    "name": "groq",
    "kind": "openai_compatible",
    "base_url": "https://api.groq.com/openai/v1",
    "api_key": "${ENV_API_KEY}",
    "default_model": "openai/gpt-oss-120b",
    "default": true
  },
  {
    "name": "ragustave",
    "kind": "ragustave",
    "base_url": "https://ragarenn.eskemm-numerique.fr/demo@univ-eiffel/api",
    "api_key": "${ENV_API_KEY}",
    "default_model": "RedHatAI/Llama-3.3-70B-Instruct-FP8-dynamic"
  }
]
```

Supported kinds: `openai_compatible`, `ragustave`, `gemini`, `ollama`, `openrouter`, `cerebras`.

### To set up the database from scratch

```bash
docker compose exec api python scripts/db/db_static_content.py
```

To populate the vector database for RAG :

```bash
docker compose exec api python scripts/db/db_populate_vectors.py
```

### To populate the database from a database dump (`database.dump`)

```bash
python .\back\scripts\db\db_restore.py .\back\resources\backups\agora_db_timestamp.dump
```
 
## urls and ports

the backend is available at `http://localhost:8000`

the swagger api is available at `http://localhost:8000/docs`

## benchmark 

run a benchmark for the multilingual-e5-large-instruct embedding model with weighted tests and dimension 1024, skipping LLM benchmarks:
```bash
docker compose exec api python scripts/benchmarks/run_benchmark.py --embed-model /opt/models/multilingual-e5-large-instruct -j weighted/simple.json --dimension 1024 --skip-llm
```

download an embedding model :

```bash
docker compose exec api python scripts/benchmarks/download_models.py OrdalieTech/Solon-embeddings-large-0.1 
```

## Tests

To run the tests, you can use the following command:

```bash
docker compose exec api pytest -v
```

To run a specific package of tests, you can use the following command:

```bash
docker compose exec api pytest -v tests/package_name
```

To update the log db tables (this deletes all previous log data !):

```bash
docker compose exec api python scripts/db/db_setup_log_tables.py
```

```SQL
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
```

to restore dump.sql : 

```bash
docker compose exec db psql -U agora -d agora_db -f dump.sql
```