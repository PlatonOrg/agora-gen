# app/services/models/schemas.py
from typing import Dict, Any, List

TYPE_MAP = {
    "text": "string",
    "code": "string",
    "list": "array",
    "number": "integer",
    "select": "string",
    "boolean": "boolean",
    "file": "string",
    "json": "object",
}
