from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import httpx

from .cache import IdCache
from .report import Report
from .static import _is_positive_int, row_shape


class LiveVerifier:
    def __init__(
        self,
        *,
        cache: IdCache,
        refresh: bool = False,
        tmdb_api_key: str | None = None,
        tmdb_token: str | None = None,
        tvdb_api_key: str | None = None,
        tvdb_pin: str | None = None,
    ) -> None:
        self.cache = cache
        self.refresh = refresh
        self.tmdb_api_key = tmdb_api_key or os.getenv("TMDB_API_KEY") or None
        self.tmdb_token = tmdb_token or os.getenv("TMDB_READ_ACCESS_TOKEN") or None
        self.tvdb_api_key = tvdb_api_key or os.getenv("TVDB_API_KEY") or None
        self.tvdb_pin = tvdb_pin or os.getenv("TVDB_PIN") or None
        self._client = httpx.Client(timeout=30.0, follow_redirects=True)
        self._tvdb_token: str | None = None
        self._tvdb_series_episodes: dict[int, set[tuple[int, int]]] = {}
        self._tvdb_series_seasons: dict[int, set[int]] = {}

    def close(self) -> None:
        self._client.close()
        self.cache.save()

    def __enter__(self) -> LiveVerifier:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @property
    def tmdb_enabled(self) -> bool:
        return bool(self.tmdb_api_key or self.tmdb_token)

    @property
    def tvdb_enabled(self) -> bool:
        return bool(self.tvdb_api_key)

    def ensure_credentials(self, report: Report) -> bool:
        ok = True
        if not self.tmdb_enabled:
            report.warning("TMDB credentials missing; skipping TMDB live checks (.env)")
        if not self.tvdb_enabled:
            report.warning("TVDB_API_KEY missing; skipping TVDb live checks (.env)")
        if not self.tmdb_enabled and not self.tvdb_enabled:
            report.error("no live API credentials configured; see .env.example")
            ok = False
        return ok

    def verify_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        path: Path,
        report: Report,
    ) -> None:
        for index, row in enumerate(rows):
            shape = row_shape(row)
            kind = row.get("kind")
            if shape == "movie" or (shape == "whole" and kind == "movie"):
                self._verify_movie(row, path=path, index=index, report=report)
            elif shape == "whole" and kind == "series":
                self._verify_series(row, path=path, index=index, report=report)
            elif shape == "season":
                self._verify_season(row, path=path, index=index, report=report)
            elif shape == "episode":
                self._verify_episode(row, path=path, index=index, report=report)

    def _verify_movie(
        self, row: dict[str, Any], *, path: Path, index: int, report: Report
    ) -> None:
        tmdb_id = row.get("tmdb_id")
        if self.tmdb_enabled and _is_positive_int(tmdb_id):
            meta = self._tmdb_movie(int(tmdb_id))
            if meta is None:
                report.error(f"TMDB movie id {tmdb_id} not found", path=path, index=index)
            else:
                self._soft_title_year(
                    row,
                    api_title=meta.get("title") or meta.get("original_title"),
                    api_year=_year_from_date(meta.get("release_date")),
                    path=path,
                    index=index,
                    report=report,
                    source="TMDB",
                )

    def _verify_series(
        self, row: dict[str, Any], *, path: Path, index: int, report: Report
    ) -> None:
        tmdb_id = row.get("tmdb_id")
        if self.tmdb_enabled and _is_positive_int(tmdb_id):
            meta = self._tmdb_tv(int(tmdb_id))
            if meta is None:
                report.error(f"TMDB tv id {tmdb_id} not found", path=path, index=index)
            else:
                self._soft_title_year(
                    row,
                    api_title=meta.get("name") or meta.get("original_name"),
                    api_year=_year_from_date(meta.get("first_air_date")),
                    path=path,
                    index=index,
                    report=report,
                    source="TMDB",
                )

        tvdb_id = row.get("tvdb_id")
        if self.tvdb_enabled and _is_positive_int(tvdb_id):
            meta = self._tvdb_series(int(tvdb_id))
            if meta is None:
                report.error(f"TVDb series id {tvdb_id} not found", path=path, index=index)
            else:
                self._soft_title_year(
                    row,
                    api_title=meta.get("name"),
                    api_year=_year_from_date(meta.get("firstAired") or meta.get("first_air_time")),
                    path=path,
                    index=index,
                    report=report,
                    source="TVDb",
                )

    def _verify_season(
        self, row: dict[str, Any], *, path: Path, index: int, report: Report
    ) -> None:
        if not self.tvdb_enabled:
            return
        tvdb_id = row.get("tvdb_id")
        season = row.get("season")
        if not (_is_positive_int(tvdb_id) and _is_positive_int(season)):
            return
        seasons = self._tvdb_seasons(int(tvdb_id))
        if seasons is None:
            report.error(f"TVDb series id {tvdb_id} not found", path=path, index=index)
            return
        if int(season) not in seasons:
            report.error(
                f"TVDb series {tvdb_id} has no season {season}",
                path=path,
                index=index,
            )

    def _verify_episode(
        self, row: dict[str, Any], *, path: Path, index: int, report: Report
    ) -> None:
        if not self.tvdb_enabled:
            return
        tvdb_id = row.get("tvdb_id")
        season = row.get("season")
        episode = row.get("episode")
        if not (
            _is_positive_int(tvdb_id) and _is_positive_int(season) and _is_positive_int(episode)
        ):
            return
        episodes = self._tvdb_episodes(int(tvdb_id))
        if episodes is None:
            report.error(f"TVDb series id {tvdb_id} not found", path=path, index=index)
            return
        if (int(season), int(episode)) not in episodes:
            report.error(
                f"TVDb series {tvdb_id} has no S{int(season):02d}E{int(episode):02d}",
                path=path,
                index=index,
            )

    def _soft_title_year(
        self,
        row: dict[str, Any],
        *,
        api_title: str | None,
        api_year: int | None,
        path: Path,
        index: int,
        report: Report,
        source: str,
    ) -> None:
        if api_year and isinstance(row.get("year"), int) and abs(api_year - row["year"]) > 1:
            report.warning(
                f"{source} year {api_year} differs from row year {row['year']}",
                path=path,
                index=index,
            )
        if api_title and isinstance(row.get("name"), str):
            if api_title.casefold() != row["name"].casefold():
                report.warning(
                    f"{source} title '{api_title}' differs from row name '{row['name']}'",
                    path=path,
                    index=index,
                )

    # --- TMDB ---

    def _tmdb_headers_params(self) -> tuple[dict[str, str], dict[str, str]]:
        headers: dict[str, str] = {"Accept": "application/json"}
        params: dict[str, str] = {}
        if self.tmdb_token:
            headers["Authorization"] = f"Bearer {self.tmdb_token}"
        elif self.tmdb_api_key:
            params["api_key"] = self.tmdb_api_key
        return headers, params

    def _tmdb_movie(self, tmdb_id: int) -> dict[str, Any] | None:
        key = f"tmdb:movie:{tmdb_id}"
        cached = self.cache.get(key, refresh=self.refresh)
        if cached is not None:
            return None if cached.get("ok") is False else cached.get("data")

        headers, params = self._tmdb_headers_params()
        resp = self._client.get(
            f"https://api.themoviedb.org/3/movie/{tmdb_id}",
            headers=headers,
            params=params,
        )
        if resp.status_code == 404:
            self.cache.set(key, {"ok": False})
            return None
        resp.raise_for_status()
        data = resp.json()
        self.cache.set(
            key,
            {
                "ok": True,
                "data": {
                    "title": data.get("title"),
                    "original_title": data.get("original_title"),
                    "release_date": data.get("release_date"),
                },
            },
        )
        return self.cache.entries[key]["data"]

    def _tmdb_tv(self, tmdb_id: int) -> dict[str, Any] | None:
        key = f"tmdb:tv:{tmdb_id}"
        cached = self.cache.get(key, refresh=self.refresh)
        if cached is not None:
            return None if cached.get("ok") is False else cached.get("data")

        headers, params = self._tmdb_headers_params()
        resp = self._client.get(
            f"https://api.themoviedb.org/3/tv/{tmdb_id}",
            headers=headers,
            params=params,
        )
        if resp.status_code == 404:
            self.cache.set(key, {"ok": False})
            return None
        resp.raise_for_status()
        data = resp.json()
        self.cache.set(
            key,
            {
                "ok": True,
                "data": {
                    "name": data.get("name"),
                    "original_name": data.get("original_name"),
                    "first_air_date": data.get("first_air_date"),
                },
            },
        )
        return self.cache.entries[key]["data"]

    # --- TVDb ---

    def _tvdb_login(self) -> str:
        if self._tvdb_token:
            return self._tvdb_token
        body: dict[str, str] = {"apikey": self.tvdb_api_key or ""}
        if self.tvdb_pin:
            body["pin"] = self.tvdb_pin
        resp = self._client.post("https://api4.thetvdb.com/v4/login", json=body)
        resp.raise_for_status()
        token = resp.json().get("data", {}).get("token")
        if not token:
            raise RuntimeError("TVDb login did not return a token")
        self._tvdb_token = token
        return token

    def _tvdb_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._tvdb_login()}",
        }

    def _tvdb_series(self, tvdb_id: int) -> dict[str, Any] | None:
        key = f"tvdb:series:{tvdb_id}"
        cached = self.cache.get(key, refresh=self.refresh)
        if cached is not None:
            return None if cached.get("ok") is False else cached.get("data")

        resp = self._client.get(
            f"https://api4.thetvdb.com/v4/series/{tvdb_id}",
            headers=self._tvdb_headers(),
        )
        if resp.status_code == 404:
            self.cache.set(key, {"ok": False})
            return None
        resp.raise_for_status()
        data = resp.json().get("data") or {}
        payload = {
            "name": data.get("name"),
            "firstAired": data.get("firstAired"),
        }
        self.cache.set(key, {"ok": True, "data": payload})
        return payload

    def _tvdb_episodes(self, tvdb_id: int) -> set[tuple[int, int]] | None:
        if tvdb_id in self._tvdb_series_episodes and not self.refresh:
            return self._tvdb_series_episodes[tvdb_id]

        key = f"tvdb:episodes:{tvdb_id}"
        cached = self.cache.get(key, refresh=self.refresh)
        if cached is not None:
            if cached.get("ok") is False:
                return None
            pairs = { (int(s), int(e)) for s, e in cached.get("episodes", []) }
            seasons = {s for s, _ in pairs}
            self._tvdb_series_episodes[tvdb_id] = pairs
            self._tvdb_series_seasons[tvdb_id] = seasons
            return pairs

        # Confirm series exists first.
        if self._tvdb_series(tvdb_id) is None:
            self.cache.set(key, {"ok": False})
            return None

        pairs: set[tuple[int, int]] = set()
        page = 0
        while True:
            resp = self._client.get(
                f"https://api4.thetvdb.com/v4/series/{tvdb_id}/episodes/default",
                headers=self._tvdb_headers(),
                params={"page": page},
            )
            if resp.status_code == 404:
                self.cache.set(key, {"ok": False})
                return None
            resp.raise_for_status()
            payload = resp.json()
            for ep in payload.get("data", {}).get("episodes") or payload.get("data") or []:
                if not isinstance(ep, dict):
                    continue
                s = ep.get("seasonNumber", ep.get("season"))
                n = ep.get("number", ep.get("episodeNumber"))
                if isinstance(s, int) and isinstance(n, int) and s > 0 and n > 0:
                    pairs.add((s, n))
            links = payload.get("links") or {}
            next_page = links.get("next")
            if next_page is None:
                break
            page = int(next_page)
            time.sleep(0.05)

        self.cache.set(
            key,
            {"ok": True, "episodes": [[s, e] for s, e in sorted(pairs)]},
        )
        self._tvdb_series_episodes[tvdb_id] = pairs
        self._tvdb_series_seasons[tvdb_id] = {s for s, _ in pairs}
        return pairs

    def _tvdb_seasons(self, tvdb_id: int) -> set[int] | None:
        if tvdb_id in self._tvdb_series_seasons and not self.refresh:
            return self._tvdb_series_seasons[tvdb_id]
        episodes = self._tvdb_episodes(tvdb_id)
        if episodes is None:
            return None
        return self._tvdb_series_seasons.get(tvdb_id, {s for s, _ in episodes})


def _year_from_date(value: Any) -> int | None:
    if not isinstance(value, str) or len(value) < 4:
        return None
    try:
        return int(value[:4])
    except ValueError:
        return None
