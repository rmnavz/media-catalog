from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from .discover import CatalogFile, FileKind
from .report import Report
from .static import _is_positive_int, row_shape


def _index_collection(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if isinstance(row.get("imdb_id"), str):
            index[f"imdb:{row['imdb_id']}"].append(row)
        if _is_positive_int(row.get("tmdb_id")):
            index[f"tmdb:{row['tmdb_id']}"].append(row)
        if _is_positive_int(row.get("tvdb_id")):
            index[f"tvdb:{row['tvdb_id']}"].append(row)
        name = row.get("name")
        year = row.get("year")
        if isinstance(name, str) and isinstance(year, int):
            index[f"name:{name.casefold()}|{year}"].append(row)
    return index


def validate_membership(
    *,
    repo: Path,
    collections: dict[str, list[dict[str, Any]]],
    playlists: list[tuple[CatalogFile, list[dict[str, Any]]]],
    report: Report,
) -> None:
    """Playlist titles must resolve into the sibling franchise/thematic collection."""
    for meta, rows in playlists:
        if not meta.slug:
            continue
        coll_rows = collections.get(meta.slug)
        if coll_rows is None:
            # Try loading path hint only via map miss.
            report.error(
                f"no collection found for playlist slug '{meta.slug}'",
                path=meta.path,
            )
            continue

        index = _index_collection(coll_rows)
        playlist_keys: set[str] = set()

        for i, row in enumerate(rows):
            shape = row_shape(row)
            matched = False
            used_key = None

            if shape in ("season", "episode"):
                key = f"tvdb:{row.get('tvdb_id')}"
                if key in index:
                    matched = True
                    used_key = key
                else:
                    report.error(
                        f"playlist {shape} tvdb_id={row.get('tvdb_id')} "
                        "not present on any collection series row",
                        path=meta.path,
                        index=i,
                    )
            else:
                candidates = []
                if isinstance(row.get("imdb_id"), str):
                    candidates.append(f"imdb:{row['imdb_id']}")
                if _is_positive_int(row.get("tmdb_id")):
                    candidates.append(f"tmdb:{row['tmdb_id']}")
                if _is_positive_int(row.get("tvdb_id")):
                    candidates.append(f"tvdb:{row['tvdb_id']}")
                for key in candidates:
                    if key in index:
                        matched = True
                        used_key = key
                        break
                if not matched:
                    name = row.get("name")
                    year = row.get("year")
                    name_key = f"name:{str(name).casefold()}|{year}"
                    if name_key in index:
                        matched = True
                        used_key = name_key
                        report.warning(
                            "matched collection by name/year only; ids may drift",
                            path=meta.path,
                            index=i,
                        )
                    else:
                        report.error(
                            f"playlist title not in collection: {name} ({year})",
                            path=meta.path,
                            index=i,
                        )

            if matched and used_key:
                playlist_keys.add(used_key)
                # Soft-check name/year: ok if any collection row with this id matches.
                coll_hits = index[used_key]
                if not any(
                    row.get("name") == c.get("name") and row.get("year") == c.get("year")
                    for c in coll_hits
                ):
                    sample = coll_hits[0]
                    report.warning(
                        "name/year differs from collection entry for same id "
                        f"({sample.get('name')} {sample.get('year')} vs "
                        f"{row.get('name')} {row.get('year')})",
                        path=meta.path,
                        index=i,
                    )

        # Collection titles never appearing in this playlist — info only for release/chrono.
        if meta.order in ("release", "chronological"):
            missing = []
            for row in coll_rows:
                keys = []
                if _is_positive_int(row.get("tvdb_id")):
                    keys.append(f"tvdb:{row['tvdb_id']}")
                if isinstance(row.get("imdb_id"), str):
                    keys.append(f"imdb:{row['imdb_id']}")
                if _is_positive_int(row.get("tmdb_id")):
                    keys.append(f"tmdb:{row['tmdb_id']}")
                if keys and not any(k in playlist_keys for k in keys):
                    missing.append(f"{row.get('name')} ({row.get('year')})")
            seen: set[str] = set()
            uniq: list[str] = []
            for item in missing:
                if item not in seen:
                    seen.add(item)
                    uniq.append(item)
            if uniq:
                report.info(
                    f"{len(uniq)} collection title(s) absent from this playlist "
                    f"(ok if intentional subset)",
                    path=meta.path,
                    details=uniq,
                )


def group_loaded(
    files: list[CatalogFile],
    loaded: dict[Path, list[dict[str, Any]]],
) -> tuple[dict[str, list[dict[str, Any]]], list[tuple[CatalogFile, list[dict[str, Any]]]]]:
    collections: dict[str, list[dict[str, Any]]] = {}
    playlists: list[tuple[CatalogFile, list[dict[str, Any]]]] = []
    for meta in files:
        rows = loaded.get(meta.path, [])
        if meta.kind == FileKind.COLLECTION and meta.slug:
            collections[meta.slug] = rows
        elif meta.kind == FileKind.PLAYLIST:
            playlists.append((meta, rows))
    return collections, playlists
