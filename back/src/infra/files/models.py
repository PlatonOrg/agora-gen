from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FileSummaryResult:
    file_id: str
    filename: str
    extracted_text: str
    summary: str

