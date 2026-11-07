from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from .cache import IdCache
from .discover import FileKind, discover, repo_root_from
from .live import LiveVerifier
from .membership import group_loaded, validate_membership
from .report import Report, Severity
from .static import validate_file, validate_naming_coverage, validate_path_naming_rejects

DEFAULT_REPORT = Path("reports/validation.md")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="validate_catalog",
        description=(
            "Validate media-catalog collections and playlists "
            "(https://github.com/rmnavz/media-catalog, CC0 1.0)."
        ),
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=None,
        help="Repo root (default: auto-detect from cwd)",
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=None,
        help="Validate a single collections/*.json or playlists/*.json file",
    )
    parser.add_argument(
        "--slug",
        type=str,
        default=None,
        help="Validate one franchise/thematic slug (collection + playlists)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Verify ids against TMDB / TVDb (requires .env credentials)",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Ignore cached live-ID results and re-fetch",
    )
    parser.add_argument(
        "--cache-file",
        type=Path,
        default=None,
        help="Live-ID cache path (default: <repo>/.cache/id-validation.json)",
    )
    parser.add_argument(
        "--ttl-days",
        type=int,
        default=30,
        help="Live-ID cache TTL in days (default: 30)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only print errors/warnings (hide info); still include info in --report",
    )
    parser.add_argument(
        "--report",
        nargs="?",
        const=DEFAULT_REPORT,
        default=None,
        type=Path,
        help=(
            "Write a Markdown validation report "
            f"(default path when flag is set: {DEFAULT_REPORT.as_posix()})"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo = (args.repo or repo_root_from()).resolve()

    load_dotenv(repo / ".env")

    report = Report()
    try:
        files = discover(repo, path=args.path, slug=args.slug)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not files:
        print("ERROR: no catalog files matched", file=sys.stderr)
        return 2

    # Naming coverage / stray filenames when scanning broadly.
    if args.path is None:
        validate_path_naming_rejects(repo, report)
        validate_naming_coverage(repo, files, report)

    loaded: dict[Path, list] = {}
    checked = 0
    for meta in files:
        if meta.kind == FileKind.TEMPLATE:
            continue
        rel = meta.path.relative_to(repo)
        rows = validate_file(meta, report)
        loaded[meta.path] = rows
        checked += 1
        print(f"checked {rel.as_posix()} ({len(rows)} rows)")

    collections, playlists = group_loaded(files, loaded)
    validate_membership(
        repo=repo, collections=collections, playlists=playlists, report=report
    )

    if args.live:
        cache_path = args.cache_file or (repo / ".cache" / "id-validation.json")
        cache = IdCache(cache_path, ttl_days=args.ttl_days)
        with LiveVerifier(cache=cache, refresh=args.refresh_cache) as verifier:
            if verifier.ensure_credentials(report):
                for meta in files:
                    if meta.kind == FileKind.TEMPLATE:
                        continue
                    rows = loaded.get(meta.path, [])
                    verifier.verify_rows(rows, path=meta.path, report=report)

    # Normalize finding paths to repo-relative for console + report.
    for finding in report.findings:
        if finding.path is not None:
            try:
                finding.path = finding.path.resolve().relative_to(repo)
            except ValueError:
                pass

    console = Report()
    console.findings = list(report.findings)
    if args.quiet:
        console.findings = [f for f in console.findings if f.severity != Severity.INFO]

    if console.findings:
        print()
    console.print()

    errors = report.error_count
    warnings = report.warning_count
    infos = report.info_count
    print(f"\n{errors} error(s), {warnings} warning(s), {infos} info")

    if args.report is not None:
        report_path = args.report if args.report.is_absolute() else (repo / args.report)
        report.write_markdown(report_path, repo=repo, checked=checked)
        print(f"wrote {report_path.relative_to(repo).as_posix()}")

    if errors:
        return 1
    if args.strict and warnings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
