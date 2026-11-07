# media-catalog

Shareable lists of movies and series for [Kometa](https://kometa.wiki/) / Plex and other tools that can read the same JSON.

**Repo:** https://github.com/rmnavz/media-catalog  
**License:** [CC0 1.0](LICENSE) — personal catalog dedicated to the public domain; reuse or fork freely if useful.

Kometa loads these files with the [`text_file`](https://kometa.wiki/en/latest/files/builders/textfile/#json-list-example) builder.

Personal lists (plan to watch, watching, watched) belong in the private **media-library** repo, not here.

## Layout

```text
collections/<category>/<slug>.collections.json
playlists/<franchise-slug>-chronological.playlist.json
playlists/<franchise-slug>-release.playlist.json
playlists/<franchise-slug>-recommended.playlist.json   # optional guided path
```

Collection categories (only where a maintained list beats Kometa/Plex filters):

| Category | For |
| --- | --- |
| `franchise` | Universes and franchises you curate by hand (Star Wars, MCU, Potter) |
| `thematic` | Hand-picked themes with no reliable metadata rule (cyberpunk essentials, comfort rewatch) |

Skip JSON for studio, network, genre, decade, awards, charts, and most holiday/seasonal sets — use Kometa defaults or Plex `smart_filter` instead. Add a holiday JSON only if you want a stricter curated pack than Kometa’s seasonal defaults.

**Collections** hold membership (each title once). **Playlists** hold watch order.

| Playlist suffix | Order meaning |
| --- | --- |
| `-chronological` | In-universe timeline; season splits OK when series interleave |
| `-release` | Theatrical / first-air premiere order; season splits OK when a series runs across the timeline |
| `-recommended` | Guided / alternate order; season and episode splits OK |

Playlist titles must match the franchise collection (same `name` / ids). Do not invent a second identity for the same title.

Copy `collections/_template.collections.json` or `playlists/_template.playlist.json` into the right place, rename the slug, replace the example rows, and drop keys you do not have.

Kometa raw URLs (branch `main`):

```text
https://raw.githubusercontent.com/rmnavz/media-catalog/main/collections/franchise/star-wars.collections.json
https://raw.githubusercontent.com/rmnavz/media-catalog/main/playlists/star-wars-chronological.playlist.json
https://raw.githubusercontent.com/rmnavz/media-catalog/main/playlists/star-wars-release.playlist.json
```

Wire playlists with both libraries and sync so array order is preserved:

```yaml
playlists:
  Star Wars Chronological:
    libraries: Movies, TV Shows
    sync_mode: sync
    text_file: https://raw.githubusercontent.com/rmnavz/media-catalog/main/playlists/star-wars-chronological.playlist.json
```

## Playlist row shapes

Every playlist row has `name`, `year`, and `kind` (`movie` or `series`). The **match key** Kometa uses depends on the row shape. Put only one match shape on a row.

### Movie

```json
{
  "name": "Example Movie",
  "year": 1977,
  "kind": "movie",
  "imdb_id": "tt0000000",
  "tmdb_id": 11
}
```

Match with `imdb_id` and/or `tmdb_id`. Do not set `season`, `episode`, `tvdb_season`, or `tvdb_episode`.

### Whole series

```json
{
  "name": "Example Series",
  "year": 2019,
  "kind": "series",
  "imdb_id": "tt0000000",
  "tmdb_id": 82856,
  "tvdb_id": 12345
}
```

Match with `imdb_id`, `tmdb_id`, and/or `tvdb_id`. Means the entire show as one playlist item. Do not set part fields.

### Series season

Use when order is `movie → S01 → movie → S02`. Repeat the series once per season block.

```json
{
  "name": "Example Series",
  "year": 2019,
  "kind": "series",
  "tvdb_id": 12345,
  "season": 1,
  "tvdb_season": "12345_1"
}
```

Required:

- `tvdb_id`
- `season` (integer, 1-based)
- `tvdb_season` as `"<tvdb_id>_<season>"` (Kometa match key)

Do **not** put `imdb_id` or `tmdb_id` on season rows. Those resolve the whole show and break season order.

### Series episode

Use for arc-level guides, and for **parallel / crossover timelines** where shows overlap (for example series A `S01E04`, then series B `S03E03`, then back to A).

```json
{
  "name": "Example Series",
  "year": 2019,
  "kind": "series",
  "tvdb_id": 12345,
  "season": 1,
  "episode": 2,
  "tvdb_episode": {
    "tvdb_id": 12345,
    "season": 1,
    "episode": 2
  }
}
```

Required:

- `tvdb_id`, `season`, `episode`
- `tvdb_episode` object (Kometa match key)

Do **not** put `imdb_id` or `tmdb_id` on episode rows.

There is no special “parallel” field. If two series share a timeline, list their episode rows in the watch sequence you want. Kometa/Plex only see a flat ordered playlist.

### Interleave example (movies + seasons)

```json
[
  {
    "name": "Example Movie",
    "year": 1977,
    "kind": "movie",
    "imdb_id": "tt0000000",
    "tmdb_id": 11
  },
  {
    "name": "Example Series",
    "year": 2019,
    "kind": "series",
    "tvdb_id": 12345,
    "season": 1,
    "tvdb_season": "12345_1"
  },
  {
    "name": "Example Movie 2",
    "year": 1980,
    "kind": "movie",
    "imdb_id": "tt0000001",
    "tmdb_id": 12
  },
  {
    "name": "Example Series",
    "year": 2019,
    "kind": "series",
    "tvdb_id": 12345,
    "season": 2,
    "tvdb_season": "12345_2"
  }
]
```

### Parallel timeline example (episodes across series)

```json
[
  {
    "name": "Series A",
    "year": 2014,
    "kind": "series",
    "tvdb_id": 111,
    "season": 1,
    "episode": 4,
    "tvdb_episode": { "tvdb_id": 111, "season": 1, "episode": 4 }
  },
  {
    "name": "Series B",
    "year": 2022,
    "kind": "series",
    "tvdb_id": 222,
    "season": 3,
    "episode": 3,
    "tvdb_episode": { "tvdb_id": 222, "season": 3, "episode": 3 }
  },
  {
    "name": "Series A",
    "year": 2014,
    "kind": "series",
    "tvdb_id": 111,
    "season": 1,
    "episode": 5,
    "tvdb_episode": { "tvdb_id": 111, "season": 1, "episode": 5 }
  }
]
```

Mix movie, season, and episode rows in the same playlist when needed. Granularity can change mid-list (whole movie, then one episode, then a full season) as long as each row uses the correct match shape.

## List quality

Shared:

- `name`, `year`, `kind` on every row
- Do not use `type` or `source` for kind. Kometa treats those with `id` as an id instruction.
- Keep slugs stable once wired into Kometa

Collections:

- At least one of `imdb_id`, `tmdb_id`, or `tvdb_id`
- No duplicate title id in the same file
- Default order: movies by release year, then series by first-air year

Playlists:

- Array order is the watch order; never re-sort by year
- Whole-title rows: same id rules as collections
- Season/episode rows: `tvdb_id` + part fields + `tvdb_season` / `tvdb_episode` only (no `imdb_id` / `tmdb_id`)
- Same series may repeat when `season` / `episode` differs; do not repeat the same part target twice
- Season splits are allowed on `-chronological`, `-release`, and `-recommended` when series interleave with other titles (e.g. Agents of S.H.I.E.L.D. in MCU chronological order)
- Episode splits are only allowed on `-recommended` (filler cuts, arc guides, parallel/crossover timelines)
- Prefer whole-title rows when a series can sit as one block

## Metadata and ids

Include every id you know on **collection** rows and **whole-title playlist** rows; omit keys you do not have.

```json
{
  "name": "The Mandalorian",
  "year": 2019,
  "kind": "series",
  "imdb_id": "tt8111088",
  "tmdb_id": 82856,
  "tvdb_id": 361753,
  "anidb_id": 230,
  "anilist_id": 527,
  "mal_id": 249
}
```

Prefer filling all three Kometa ids when available. Series should include `tvdb_id` whenever possible. Anime rows should also include `anidb_id`, `anilist_id`, and `mal_id` for other tools.

Season/episode playlist rows only need `tvdb_id` plus the part match key above. Keep `name` / `year` aligned with the franchise collection entry for that series.

## Validation

```text
python tools/validate_catalog.py --report
```

Writes a readable Markdown summary to [`reports/validation.md`](reports/validation.md) (errors, warnings, and intentional chronological coverage gaps). Use `--quiet` to hide info lines in the console while still writing the full report.

Live id checks (`--live`) need TMDB / TVDb keys in `.env` — see [`.env.example`](.env.example). Secrets stay local; they are not part of this repo.

## License

This repository is released under [CC0 1.0 Universal](LICENSE). To the extent possible under law, the contents are dedicated to the public domain. No attribution is required.
