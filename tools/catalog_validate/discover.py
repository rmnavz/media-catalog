from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PLAYLIST_NAME_RE = re.compile(
    r"^(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)-(?P<order>chronological|release|recommended)\.playlist\.json$"
)
COLLECTION_NAME_RE = re.compile(r"^(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)\.collections\.json$")
CATEGORIES = frozenset({"franchise", "thematic"})


class FileKind(str, Enum):
    COLLECTION = "collection"
    PLAYLIST = "playlist"
    TEMPLATE = "template"


@dataclass(frozen=True)
class CatalogFile:
    path: Path
    kind: FileKind
    slug: str | None = None
    category: str | None = None
    order: str | None = None

    @property
    def is_template(self) -> bool:
        return self.kind == FileKind.TEMPLATE


def repo_root_from(start: Path | None = None) -> Path:
    here = (start or Path.cwd()).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "collections").is_dir() and (candidate / "playlists").is_dir():
            return candidate
    raise FileNotFoundError("Could not find media-catalog root (collections/ + playlists/)")


def classify_path(repo: Path, path: Path) -> CatalogFile | None:
    rel = path.resolve().relative_to(repo.resolve())
    parts = rel.parts
    name = path.name

    if name.startswith("_template") and name.endswith((".collections.json", ".playlist.json")):
        kind = FileKind.TEMPLATE
        if name.endswith(".collections.json"):
            return CatalogFile(path=path, kind=kind)
        return CatalogFile(path=path, kind=kind)

    if len(parts) >= 3 and parts[0] == "collections" and parts[1] in CATEGORIES:
        match = COLLECTION_NAME_RE.match(name)
        if not match:
            return None
        return CatalogFile(
            path=path,
            kind=FileKind.COLLECTION,
            slug=match.group("slug"),
            category=parts[1],
        )

    if len(parts) == 2 and parts[0] == "playlists":
        match = PLAYLIST_NAME_RE.match(name)
        if not match:
            return None
        return CatalogFile(
            path=path,
            kind=FileKind.PLAYLIST,
            slug=match.group("slug"),
            order=match.group("order"),
        )

    return None


def discover(
    repo: Path,
    *,
    path: Path | None = None,
    slug: str | None = None,
) -> list[CatalogFile]:
    if path is not None:
        target = path if path.is_absolute() else (repo / path)
        if not target.exists():
            raise FileNotFoundError(f"Path not found: {target}")
        classified = classify_path(repo, target)
        if classified is None:
            raise ValueError(f"Not a catalog JSON file: {target}")
        files = [classified]
        if classified.kind == FileKind.PLAYLIST and classified.slug:
            # Always include sibling collection when checking a playlist.
            coll = repo / "collections" / "franchise" / f"{classified.slug}.collections.json"
            if coll.exists():
                sibling = classify_path(repo, coll)
                if sibling and sibling not in files:
                    files.insert(0, sibling)
            thematic = repo / "collections" / "thematic" / f"{classified.slug}.collections.json"
            if thematic.exists():
                sibling = classify_path(repo, thematic)
                if sibling and sibling not in files:
                    files.insert(0, sibling)
        return files

    files: list[CatalogFile] = []
    for pattern in (
        "collections/*/*.collections.json",
        "playlists/*.playlist.json",
    ):
        for found in sorted(repo.glob(pattern)):
            if found.name.startswith("_"):
                continue
            classified = classify_path(repo, found)
            if classified is None:
                continue
            if slug and classified.slug != slug:
                continue
            files.append(classified)
    return files


def franchise_slugs(repo: Path) -> list[str]:
    slugs = []
    for path in sorted((repo / "collections" / "franchise").glob("*.collections.json")):
        if path.name.startswith("_"):
            continue
        match = COLLECTION_NAME_RE.match(path.name)
        if match:
            slugs.append(match.group("slug"))
    return slugs
