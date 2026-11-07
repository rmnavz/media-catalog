from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .discover import (
    COLLECTION_NAME_RE,
    PLAYLIST_NAME_RE,
    SLUG_RE,
    CatalogFile,
    FileKind,
    franchise_slugs,
)
from .report import Report

IMDB_RE = re.compile(r"^tt\d+$")
PLACEHOLDER_IMDB = "tt0000000"
FORBIDDEN_KEYS = frozenset({"type", "source"})
PART_KEYS = frozenset({"season", "episode", "tvdb_season", "tvdb_episode"})
KOMETA_ID_KEYS = ("imdb_id", "tmdb_id", "tvdb_id")
ANIME_ID_KEYS = ("anidb_id", "anilist_id", "mal_id")


def load_json_array(path: Path, report: Report) -> list[Any] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        report.error(f"cannot read file: {exc}", path=path)
        return None

    if text.startswith("\ufeff"):
        report.error("UTF-8 BOM is not allowed; save as UTF-8 without BOM", path=path)
        text = text.lstrip("\ufeff")

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        report.error(f"invalid JSON: {exc}", path=path)
        return None

    if not isinstance(data, list):
        report.error("root value must be a JSON array", path=path)
        return None

    # Pretty-print hint (warn only).
    expected = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    normalized = text.replace("\r\n", "\n")
    if not normalized.endswith("\n"):
        report.warning("file should end with a trailing newline", path=path)
    elif normalized != expected:
        report.warning("JSON formatting differs from indent=2 pretty-print", path=path)

    return data


def _is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _anime_id_tuple(row: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(row.get(k) for k in ANIME_ID_KEYS)


def row_shape(row: dict[str, Any]) -> str:
    has_season = "season" in row
    has_episode = "episode" in row or "tvdb_episode" in row
    if has_episode:
        return "episode"
    if has_season or "tvdb_season" in row:
        return "season"
    if row.get("kind") == "movie":
        return "movie"
    return "whole"


def validate_row(
    row: Any,
    *,
    path: Path,
    index: int,
    report: Report,
    allow_parts: bool,
    playlist_order: str | None = None,
) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        report.error("row must be an object", path=path, index=index)
        return None

    for key in FORBIDDEN_KEYS:
        if key in row:
            report.error(
                f"forbidden key '{key}' (Kometa treats type/source+id as an id instruction)",
                path=path,
                index=index,
            )

    name = row.get("name")
    year = row.get("year")
    kind = row.get("kind")

    if not isinstance(name, str) or not name.strip():
        report.error("name must be a non-empty string", path=path, index=index)
    if not isinstance(year, int) or isinstance(year, bool) or year < 1870 or year > 2100:
        report.error("year must be an integer release/first-air year", path=path, index=index)
    if kind not in ("movie", "series"):
        report.error("kind must be 'movie' or 'series'", path=path, index=index)

    shape = row_shape(row)

    if shape in ("season", "episode") and not allow_parts:
        report.error(
            f"{shape} rows are not valid in collection files",
            path=path,
            index=index,
        )
    elif (
        allow_parts
        and playlist_order in ("chronological", "release")
        and shape == "episode"
    ):
        report.error(
            f"episode split not allowed on -{playlist_order}; "
            "use season rows here, or put episode rows on -recommended",
            path=path,
            index=index,
        )

    if shape == "movie":
        _validate_movie_row(row, path=path, index=index, report=report)
    elif shape == "whole":
        _validate_whole_row(row, path=path, index=index, report=report)
    elif shape == "season":
        _validate_season_row(row, path=path, index=index, report=report)
    elif shape == "episode":
        _validate_episode_row(row, path=path, index=index, report=report)

    # Placeholder ids outside templates.
    if row.get("imdb_id") == PLACEHOLDER_IMDB:
        report.error(f"placeholder imdb_id {PLACEHOLDER_IMDB}", path=path, index=index)
    for key in ("tmdb_id", "tvdb_id", *ANIME_ID_KEYS):
        if key in row and row[key] == 0:
            report.error(f"placeholder {key}=0", path=path, index=index)

    if kind == "series" and shape == "whole" and "tvdb_id" not in row:
        report.warning("series row missing tvdb_id", path=path, index=index)

    if any(k in row for k in ANIME_ID_KEYS) or (
        isinstance(name, str) and _looks_anime_hint(name)
    ):
        missing = [k for k in ANIME_ID_KEYS if k not in row]
        if missing and shape in ("movie", "whole"):
            # Only warn when at least one anime id is already present (explicit anime row).
            if any(k in row for k in ANIME_ID_KEYS):
                report.warning(
                    f"anime row missing {', '.join(missing)}",
                    path=path,
                    index=index,
                )

    return row


def _looks_anime_hint(name: str) -> bool:
    return False  # reserved; anime detection stays id-driven


def _validate_id_formats(row: dict[str, Any], *, path: Path, index: int, report: Report) -> None:
    if "imdb_id" in row:
        imdb = row["imdb_id"]
        if not isinstance(imdb, str) or not IMDB_RE.match(imdb):
            report.error("imdb_id must match ^tt\\d+$", path=path, index=index)
    for key in ("tmdb_id", "tvdb_id", *ANIME_ID_KEYS):
        if key in row and not _is_positive_int(row[key]):
            report.error(f"{key} must be a positive integer", path=path, index=index)


def _validate_movie_row(
    row: dict[str, Any], *, path: Path, index: int, report: Report
) -> None:
    if row.get("kind") != "movie":
        report.error("movie-shaped row must have kind=movie", path=path, index=index)
    bad_parts = PART_KEYS.intersection(row)
    if bad_parts:
        report.error(
            f"movie row must not include part keys: {', '.join(sorted(bad_parts))}",
            path=path,
            index=index,
        )
    if "tvdb_id" in row:
        report.warning("movie row usually should not include tvdb_id", path=path, index=index)
    if "imdb_id" not in row and "tmdb_id" not in row:
        report.error("movie row needs imdb_id and/or tmdb_id", path=path, index=index)
    _validate_id_formats(row, path=path, index=index, report=report)


def _validate_whole_row(
    row: dict[str, Any], *, path: Path, index: int, report: Report
) -> None:
    bad_parts = PART_KEYS.intersection(row)
    if bad_parts:
        report.error(
            f"whole-title row must not include part keys: {', '.join(sorted(bad_parts))}",
            path=path,
            index=index,
        )
    if not any(k in row for k in KOMETA_ID_KEYS):
        report.error(
            "whole-title row needs at least one of imdb_id, tmdb_id, tvdb_id",
            path=path,
            index=index,
        )
    _validate_id_formats(row, path=path, index=index, report=report)


def _validate_season_row(
    row: dict[str, Any], *, path: Path, index: int, report: Report
) -> None:
    if row.get("kind") != "series":
        report.error("season row must have kind=series", path=path, index=index)
    if "imdb_id" in row or "tmdb_id" in row:
        report.error(
            "season row must not include imdb_id/tmdb_id (breaks season match)",
            path=path,
            index=index,
        )
    if not _is_positive_int(row.get("tvdb_id")):
        report.error("season row requires positive tvdb_id", path=path, index=index)
    season = row.get("season")
    if not _is_positive_int(season):
        report.error("season must be a positive 1-based integer", path=path, index=index)
    expected = f"{row.get('tvdb_id')}_{season}"
    if row.get("tvdb_season") != expected:
        report.error(
            f"tvdb_season must be '{expected}'",
            path=path,
            index=index,
        )
    if "episode" in row or "tvdb_episode" in row:
        report.error("season row must not include episode fields", path=path, index=index)
    _validate_id_formats(
        {k: v for k, v in row.items() if k in ("tvdb_id", *ANIME_ID_KEYS)},
        path=path,
        index=index,
        report=report,
    )


def _validate_episode_row(
    row: dict[str, Any], *, path: Path, index: int, report: Report
) -> None:
    if row.get("kind") != "series":
        report.error("episode row must have kind=series", path=path, index=index)
    if "imdb_id" in row or "tmdb_id" in row:
        report.error(
            "episode row must not include imdb_id/tmdb_id (breaks episode match)",
            path=path,
            index=index,
        )
    if not _is_positive_int(row.get("tvdb_id")):
        report.error("episode row requires positive tvdb_id", path=path, index=index)
    season = row.get("season")
    episode = row.get("episode")
    if not _is_positive_int(season):
        report.error("season must be a positive 1-based integer", path=path, index=index)
    if not _is_positive_int(episode):
        report.error("episode must be a positive 1-based integer", path=path, index=index)
    if "tvdb_season" in row:
        report.error("episode row must not include tvdb_season", path=path, index=index)
    te = row.get("tvdb_episode")
    if not isinstance(te, dict):
        report.error("episode row requires tvdb_episode object", path=path, index=index)
    else:
        if te.get("tvdb_id") != row.get("tvdb_id"):
            report.error("tvdb_episode.tvdb_id must match row tvdb_id", path=path, index=index)
        if te.get("season") != season:
            report.error("tvdb_episode.season must match row season", path=path, index=index)
        if te.get("episode") != episode:
            report.error("tvdb_episode.episode must match row episode", path=path, index=index)
    _validate_id_formats(
        {k: v for k, v in row.items() if k in ("tvdb_id", *ANIME_ID_KEYS)},
        path=path,
        index=index,
        report=report,
    )


def _kometa_keys(row: dict[str, Any]) -> list[str]:
    keys = []
    if isinstance(row.get("imdb_id"), str):
        keys.append(f"imdb:{row['imdb_id']}")
    if _is_positive_int(row.get("tmdb_id")):
        keys.append(f"tmdb:{row['tmdb_id']}")
    if _is_positive_int(row.get("tvdb_id")):
        keys.append(f"tvdb:{row['tvdb_id']}")
    return keys


def validate_collection_duplicates(
    rows: list[dict[str, Any]], *, path: Path, report: Report
) -> None:
    """Allow shared Kometa ids only when anime ids differ (Pokémon/Monogatari eras)."""
    seen: dict[str, list[tuple[int, tuple[Any, ...]]]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        anime = _anime_id_tuple(row)
        for key in _kometa_keys(row):
            seen.setdefault(key, []).append((index, anime))

    for key, occurrences in seen.items():
        if len(occurrences) < 2:
            continue
        # Distinct anime-id tuples → allowed shared Kometa identity.
        anime_sets = {occ[1] for occ in occurrences}
        if len(anime_sets) > 1 and all(
            any(v is not None for v in anime) for anime in anime_sets
        ):
            continue
        # Identical anime tuples (or no anime ids) → true duplicate.
        indexes = ", ".join(str(i) for i, _ in occurrences)
        report.error(
            f"duplicate title id {key} at indexes [{indexes}] "
            "(shared Kometa ids only allowed when anidb/anilist/mal differ)",
            path=path,
        )


def validate_playlist_duplicates(
    rows: list[dict[str, Any]], *, path: Path, report: Report
) -> None:
    # Shared Kometa ids across AniDB-era rows are allowed (Pokémon/Monogatari).
    whole_seen: dict[str, list[tuple[int, tuple[Any, ...]]]] = {}
    part_seen: dict[str, int] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        shape = row_shape(row)
        if shape == "season":
            part_key = f"season:{row.get('tvdb_season')}"
            if part_key in part_seen:
                report.error(
                    f"duplicate season target {row.get('tvdb_season')} "
                    f"(also at index {part_seen[part_key]})",
                    path=path,
                    index=index,
                )
            else:
                part_seen[part_key] = index
        elif shape == "episode":
            te = row.get("tvdb_episode") or {}
            part_key = f"episode:{te.get('tvdb_id')}:{te.get('season')}:{te.get('episode')}"
            if part_key in part_seen:
                report.error(
                    f"duplicate episode target {part_key.removeprefix('episode:')} "
                    f"(also at index {part_seen[part_key]})",
                    path=path,
                    index=index,
                )
            else:
                part_seen[part_key] = index
        else:
            anime = _anime_id_tuple(row)
            for key in _kometa_keys(row):
                whole_seen.setdefault(key, []).append((index, anime))

    for key, occurrences in whole_seen.items():
        if len(occurrences) < 2:
            continue
        anime_sets = {occ[1] for occ in occurrences}
        if len(anime_sets) > 1 and all(
            any(v is not None for v in anime) for anime in anime_sets
        ):
            continue
        indexes = ", ".join(str(i) for i, _ in occurrences)
        report.error(
            f"duplicate whole-title id {key} at indexes [{indexes}]",
            path=path,
        )


def validate_file(meta: CatalogFile, report: Report) -> list[dict[str, Any]]:
    rows_raw = load_json_array(meta.path, report)
    if rows_raw is None:
        return []

    if meta.slug and not SLUG_RE.match(meta.slug):
        report.error(f"slug '{meta.slug}' must be lowercase kebab-case", path=meta.path)

    if meta.kind == FileKind.COLLECTION:
        if meta.category not in ("franchise", "thematic"):
            report.error(f"unknown collection category '{meta.category}'", path=meta.path)
        if not COLLECTION_NAME_RE.match(meta.path.name):
            report.error("collection filename must be <slug>.collections.json", path=meta.path)
    elif meta.kind == FileKind.PLAYLIST:
        if not PLAYLIST_NAME_RE.match(meta.path.name):
            report.error(
                "playlist filename must be <slug>-{chronological|release|recommended}.playlist.json",
                path=meta.path,
            )

    allow_parts = meta.kind == FileKind.PLAYLIST
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(rows_raw):
        validated = validate_row(
            item,
            path=meta.path,
            index=index,
            report=report,
            allow_parts=allow_parts,
            playlist_order=meta.order,
        )
        if validated is not None:
            rows.append(validated)

    if meta.kind == FileKind.COLLECTION:
        validate_collection_duplicates(rows, path=meta.path, report=report)
    elif meta.kind == FileKind.PLAYLIST:
        validate_playlist_duplicates(rows, path=meta.path, report=report)

    return rows


def validate_naming_coverage(repo: Path, files: list[CatalogFile], report: Report) -> None:
    """Franchise collections should have release + chronological playlists."""
    selected_slugs = {f.slug for f in files if f.kind == FileKind.COLLECTION and f.category == "franchise"}
    if not selected_slugs:
        # Whole-repo or playlist-only: still check franchise set when scanning all.
        playlist_slugs = {f.slug for f in files if f.kind == FileKind.PLAYLIST}
        if len(files) > 5 or not playlist_slugs:
            selected_slugs = set(franchise_slugs(repo))
        else:
            selected_slugs = {s for s in playlist_slugs if s}

    for slug in sorted(selected_slugs):
        coll = repo / "collections" / "franchise" / f"{slug}.collections.json"
        if not coll.exists():
            report.error(f"missing franchise collection for slug '{slug}'")
            continue
        for order in ("release", "chronological"):
            path = repo / "playlists" / f"{slug}-{order}.playlist.json"
            if not path.exists():
                report.error(f"missing playlist {path.relative_to(repo).as_posix()}")


def validate_path_naming_rejects(repo: Path, report: Report) -> None:
    """Flag JSON files under collections/playlists that do not match conventions."""
    for path in sorted((repo / "collections").rglob("*.json")):
        if path.name.startswith("_") or path.name == ".gitkeep":
            continue
        rel = path.relative_to(repo)
        parts = rel.parts
        if len(parts) != 3 or parts[1] not in ("franchise", "thematic"):
            report.error(
                f"collection must live at collections/<category>/<slug>.collections.json "
                f"(found {rel.as_posix()})"
            )
            continue
        if not COLLECTION_NAME_RE.match(path.name):
            report.error(
                f"bad collection filename (expected <slug>.collections.json): {rel.as_posix()}"
            )

    for path in sorted((repo / "playlists").glob("*.json")):
        if path.name.startswith("_"):
            continue
        if not PLAYLIST_NAME_RE.match(path.name):
            report.error(
                "bad playlist filename "
                f"(expected <slug>-{{chronological|release|recommended}}.playlist.json): "
                f"{path.relative_to(repo).as_posix()}"
            )
