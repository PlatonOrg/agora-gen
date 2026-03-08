"""
Platon documentation downloader.

Downloads all .mdx files from the PlatonOrg/platon GitHub repository
(apps/docs/ subtree) into the local resources/docs/platon_docs directory.
Image code is stripped from the files after download to keep the corpus
clean for the embedding pipeline.

Change detection
----------------
The GitHub API returns a SHA for the recursive tree object.  We persist
this SHA locally in a sentinel file (_TREE_SHA_FILE).  On each startup we
compare the remote SHA against the stored one:

- If they match  → no changes upstream; skip all network I/O.
- If they differ → download only new/changed files, delete files that no
                   longer exist in the remote tree, then update the SHA.

This makes the "already up-to-date" path virtually free (one API call) while
ensuring that additions, deletions, and edits are all captured.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.core.path_constants import PLATON_DOCS_DIR

logger = logging.getLogger(__name__)

_REPO = "PlatonOrg/platon"
_BRANCH = "main"
_DOCS_PREFIX = "apps/docs/"
_TREE_API_URL = (
    f"https://api.github.com/repos/{_REPO}/git/trees/{_BRANCH}?recursive=1"
)
_RAW_BASE_URL = f"https://raw.githubusercontent.com/{_REPO}/{_BRANCH}"

_OUTPUT_ROOT = PLATON_DOCS_DIR.parent
_TREE_SHA_FILE = _OUTPUT_ROOT / ".tree_sha"


# ---------------------------------------------------------------------------
# Low-level HTTP
# ---------------------------------------------------------------------------

def _http_get(url: str, github_token: Optional[str] = None) -> bytes:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "agora-platon-docs-downloader",
    }
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
    request = Request(url, headers=headers)
    with urlopen(request, timeout=30) as response:
        return response.read()


# ---------------------------------------------------------------------------
# GitHub tree listing
# ---------------------------------------------------------------------------

def _fetch_tree(github_token: Optional[str] = None) -> tuple[str, list[str]]:
    """Return (tree_sha, sorted_list_of_mdx_repo_paths)."""
    raw = _http_get(_TREE_API_URL, github_token=github_token)
    payload = json.loads(raw.decode("utf-8"))
    tree_sha: str = payload.get("sha", "")
    paths = sorted(
        item["path"]
        for item in payload.get("tree", [])
        if item.get("type") == "blob"
        and item["path"].startswith(_DOCS_PREFIX)
        and item["path"].endswith(".mdx")
    )
    return tree_sha, paths


# ---------------------------------------------------------------------------
# SHA sentinel helpers
# ---------------------------------------------------------------------------

def _read_stored_sha() -> str:
    if _TREE_SHA_FILE.exists():
        return _TREE_SHA_FILE.read_text(encoding="utf-8").strip()
    return ""


def _write_stored_sha(sha: str) -> None:
    _TREE_SHA_FILE.write_text(sha, encoding="utf-8")


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def _download_files(paths: list[str], github_token: Optional[str] = None) -> int:
    count = 0
    total = len(paths)
    for i, repo_path in enumerate(paths, start=1):
        relative = repo_path[len(_DOCS_PREFIX):]
        destination = _OUTPUT_ROOT / relative
        destination.parent.mkdir(parents=True, exist_ok=True)

        raw_url = f"{_RAW_BASE_URL}/{repo_path}"
        try:
            content = _http_get(raw_url, github_token=github_token)
        except (HTTPError, URLError) as exc:
            logger.warning("Platon docs: failed to download %s — %s", repo_path, exc)
            continue

        destination.write_bytes(content)
        count += 1
        _progress(i, total, destination.name)

    return count


def _delete_stale_files(remote_paths: list[str]) -> int:
    """Remove local .mdx files that no longer exist in the remote tree."""
    remote_relatives = {p[len(_DOCS_PREFIX):] for p in remote_paths}
    removed = 0
    for local_file in list(_OUTPUT_ROOT.rglob("*.mdx")):
        try:
            relative = local_file.relative_to(_OUTPUT_ROOT).as_posix()
        except ValueError:
            continue
        if relative not in remote_relatives:
            local_file.unlink(missing_ok=True)
            logger.info("Platon docs: removed stale file %s", relative)
            removed += 1
    return removed


def _progress(done: int, total: int, label: str) -> None:
    pct = int(done / total * 100) if total else 100
    bar_len = 30
    filled = int(bar_len * done / total) if total else bar_len
    bar = "█" * filled + "░" * (bar_len - filled)
    line = f"\r  [{bar}] {done}/{total} ({pct}%)  {label:<40}"
    sys.stdout.write(line)
    sys.stdout.flush()
    if done == total:
        sys.stdout.write("\n")
        sys.stdout.flush()


# ---------------------------------------------------------------------------
# Post-processing
# ---------------------------------------------------------------------------

_MD_IMAGE = re.compile(r"!\[[^\]]*]\([^)]+\)")
_HTML_IMG = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_JSX_IMAGE = re.compile(r"<Image\b[\s\S]*?/>", re.IGNORECASE)
_IMG_IMPORT = re.compile(
    r'^\s*import\s+\w+\s+from\s+["\'][^"\']+\.(png|jpg|jpeg|gif|svg|webp|avif|bmp)["\'];?\s*$',
    re.IGNORECASE,
)


def _strip_images(text: str) -> str:
    text = _MD_IMAGE.sub("", text)
    text = _HTML_IMG.sub("", text)
    text = _JSX_IMAGE.sub("", text)
    text = "\n".join(
        line for line in text.splitlines() if not _IMG_IMPORT.match(line)
    )
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def _clean_files(output_root: Path) -> int:
    changed = 0
    for mdx_file in output_root.rglob("*.mdx"):
        original = mdx_file.read_text(encoding="utf-8")
        cleaned = _strip_images(original)
        if cleaned != original:
            mdx_file.write_text(cleaned, encoding="utf-8")
            changed += 1
    return changed


def _remove_public_dir(output_root: Path) -> None:
    public = output_root / "public"
    if public.exists():
        import shutil
        shutil.rmtree(public)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_docs_present() -> bool:
    """Return True when at least one .mdx file exists under PLATON_DOCS_DIR."""
    if not PLATON_DOCS_DIR.exists():
        return False
    return any(PLATON_DOCS_DIR.rglob("*.mdx"))


def check_docs_changed(github_token: Optional[str] = None) -> tuple[bool, str]:
    """
    Compare the remote tree SHA with the locally stored one.

    Returns:
        (changed, remote_sha) where *changed* is True when the remote content
        differs from what was last downloaded.

    Raises:
        RuntimeError: If the GitHub API request fails.
    """
    try:
        remote_sha, _ = _fetch_tree(github_token=github_token)
    except (HTTPError, URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Failed to fetch Platon docs tree SHA from GitHub: {exc}"
        ) from exc

    stored_sha = _read_stored_sha()
    return remote_sha != stored_sha, remote_sha


def download_platon_docs(github_token: Optional[str] = None) -> tuple[int, str]:
    """
    Download all Platon documentation .mdx files from GitHub and clean them.

    Also deletes local files that were removed upstream and updates the stored
    tree SHA so that subsequent calls can detect whether a re-download is needed.

    This is a synchronous, blocking call — invoke from a startup coroutine via
    ``asyncio.to_thread``.

    Args:
        github_token: Optional GitHub personal access token.

    Returns:
        (downloaded_count, remote_tree_sha)

    Raises:
        RuntimeError: If the GitHub tree listing request fails.
    """
    _OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    try:
        remote_sha, mdx_paths = _fetch_tree(github_token=github_token)
    except (HTTPError, URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Failed to fetch Platon docs file listing from GitHub: {exc}"
        ) from exc

    if not mdx_paths:
        raise RuntimeError("No .mdx files found under apps/docs in the Platon repository.")

    logger.info(
        "Downloading %d Platon documentation files into %s…", len(mdx_paths), _OUTPUT_ROOT
    )
    print(f"\n  Downloading {len(mdx_paths)} Platon doc files…", flush=True)

    downloaded = _download_files(mdx_paths, github_token=github_token)
    stale = _delete_stale_files(mdx_paths)
    cleaned = _clean_files(_OUTPUT_ROOT)
    _remove_public_dir(_OUTPUT_ROOT)
    _write_stored_sha(remote_sha)

    logger.info(
        "Platon docs download complete: %d/%d downloaded, %d stale removed, %d cleaned.",
        downloaded, len(mdx_paths), stale, cleaned,
    )
    return downloaded, remote_sha
