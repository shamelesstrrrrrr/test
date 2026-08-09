from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .config import BackendSettings
from .schemas import ProcessingFileBrowserEntry, ProcessingFileBrowserResponse, ProcessingFileBrowserRoot


def _allowed_roots(settings: BackendSettings) -> list[Path]:
    roots: list[Path] = []
    for root in settings.processing_file_browser_roots:
        try:
            resolved = root.expanduser().resolve()
        except OSError:
            continue
        if resolved.exists() and resolved not in roots:
            roots.append(resolved)
    return roots


def _is_relative_to(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _resolve_browser_path(settings: BackendSettings, raw_path: str | None) -> Path:
    roots = _allowed_roots(settings)
    if not roots:
        raise FileNotFoundError("没有可浏览的根目录")

    if not raw_path:
        return roots[0]

    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = roots[0] / candidate

    try:
        resolved = candidate.resolve()
    except OSError as exc:
        raise FileNotFoundError(f"路径不存在或不可访问：{raw_path}") from exc

    if not any(_is_relative_to(resolved, root) for root in roots):
        allowed = ", ".join(str(root) for root in roots)
        raise PermissionError(f"路径不在允许浏览范围内：{resolved}；允许范围：{allowed}")

    if not resolved.exists():
        raise FileNotFoundError(f"路径不存在：{resolved}")

    return resolved.parent if resolved.is_file() else resolved


def _parent_path(current: Path, roots: list[Path]) -> str | None:
    parent = current.parent
    if parent == current:
        return None
    if any(_is_relative_to(parent, root) for root in roots):
        return str(parent)
    return None


def _modified_at(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def _entry_for_path(path: Path) -> ProcessingFileBrowserEntry | None:
    try:
        stat = path.stat()
        is_dir = path.is_dir()
    except OSError:
        return None

    return ProcessingFileBrowserEntry(
        name=path.name or str(path),
        path=str(path),
        is_dir=is_dir,
        size=None if is_dir else stat.st_size,
        modified_at=_modified_at(stat.st_mtime),
    )


def browse_processing_files(settings: BackendSettings, path: str | None = None) -> ProcessingFileBrowserResponse:
    roots = _allowed_roots(settings)
    current = _resolve_browser_path(settings, path)

    entries: list[ProcessingFileBrowserEntry] = []
    try:
        children = list(current.iterdir())
    except OSError as exc:
        raise PermissionError(f"无法读取目录：{current}") from exc

    for child in children:
        entry = _entry_for_path(child)
        if entry is not None:
            entries.append(entry)

    entries.sort(key=lambda entry: (not entry.is_dir, entry.name.lower()))

    return ProcessingFileBrowserResponse(
        current_path=str(current),
        parent_path=_parent_path(current, roots),
        roots=[ProcessingFileBrowserRoot(name=str(root), path=str(root)) for root in roots],
        entries=entries,
    )
