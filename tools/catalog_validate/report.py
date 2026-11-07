from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Finding:
    severity: Severity
    message: str
    path: Path | None = None
    index: int | None = None
    details: list[str] = field(default_factory=list)

    def location(self) -> str:
        if self.path is None:
            return ""
        loc = str(self.path).replace("\\", "/")
        if self.index is not None:
            loc = f"{loc}[{self.index}]"
        return loc

    def format_console(self) -> str:
        loc = self.location()
        label = f"{self.severity.value.upper():7}"
        if loc:
            head = f"{label} {loc}: {self.message}"
        else:
            head = f"{label} {self.message}"
        lines = [head]
        for item in self.details:
            lines.append(f"         - {item}")
        return "\n".join(lines)

    def format(self) -> str:
        """Backward-compatible single-line-ish format."""
        return self.format_console()


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    def add(
        self,
        severity: Severity,
        message: str,
        *,
        path: Path | None = None,
        index: int | None = None,
        details: list[str] | None = None,
    ) -> None:
        self.findings.append(
            Finding(
                severity=severity,
                message=message,
                path=path,
                index=index,
                details=list(details or []),
            )
        )

    def error(
        self,
        message: str,
        *,
        path: Path | None = None,
        index: int | None = None,
        details: list[str] | None = None,
    ) -> None:
        self.add(Severity.ERROR, message, path=path, index=index, details=details)

    def warning(
        self,
        message: str,
        *,
        path: Path | None = None,
        index: int | None = None,
        details: list[str] | None = None,
    ) -> None:
        self.add(Severity.WARNING, message, path=path, index=index, details=details)

    def info(
        self,
        message: str,
        *,
        path: Path | None = None,
        index: int | None = None,
        details: list[str] | None = None,
    ) -> None:
        self.add(Severity.INFO, message, path=path, index=index, details=details)

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.WARNING)

    @property
    def info_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.INFO)

    def extend(self, other: Report) -> None:
        self.findings.extend(other.findings)

    def sorted_findings(self) -> list[Finding]:
        order = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}
        return sorted(
            self.findings,
            key=lambda f: (order[f.severity], str(f.path or ""), f.index if f.index is not None else -1),
        )

    def print(self) -> None:
        by_sev: dict[Severity, list[Finding]] = {
            Severity.ERROR: [],
            Severity.WARNING: [],
            Severity.INFO: [],
        }
        for finding in self.sorted_findings():
            by_sev[finding.severity].append(finding)

        sections = [
            (Severity.ERROR, "Errors"),
            (Severity.WARNING, "Warnings"),
            (Severity.INFO, "Info"),
        ]
        first = True
        for sev, title in sections:
            items = by_sev[sev]
            if not items:
                continue
            if not first:
                print()
            first = False
            print(f"--- {title} ({len(items)}) ---")
            for finding in items:
                print(finding.format_console())

    def to_markdown(self, *, repo: Path | None = None, checked: int | None = None) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines: list[str] = [
            "# Catalog validation report",
            "",
            f"Generated `{now}` by `tools/validate_catalog.py`.",
            "",
            "## Summary",
            "",
            f"| Metric | Count |",
            f"| --- | ---: |",
            f"| Files checked | {checked if checked is not None else '—'} |",
            f"| Errors | {self.error_count} |",
            f"| Warnings | {self.warning_count} |",
            f"| Info | {self.info_count} |",
            "",
        ]

        by_sev: dict[Severity, list[Finding]] = {
            Severity.ERROR: [],
            Severity.WARNING: [],
            Severity.INFO: [],
        }
        for finding in self.sorted_findings():
            by_sev[finding.severity].append(finding)

        for sev, title in (
            (Severity.ERROR, "Errors"),
            (Severity.WARNING, "Warnings"),
            (Severity.INFO, "Info"),
        ):
            items = by_sev[sev]
            lines.append(f"## {title}")
            lines.append("")
            if not items:
                lines.append("_None._")
                lines.append("")
                continue
            for finding in items:
                loc = finding.location()
                if loc:
                    lines.append(f"- **`{loc}`** — {finding.message}")
                else:
                    lines.append(f"- {finding.message}")
                for detail in finding.details:
                    lines.append(f"  - {detail}")
            lines.append("")

        lines.append("## Notes")
        lines.append("")
        lines.append(
            "- **Collection** = franchise membership (all titles)."
        )
        lines.append(
            "- **`-release`** should usually include every collection title in premiere order."
        )
        lines.append(
            "- **`-chronological`** may omit non-canon / side / alternate-cut titles; those show up under Info."
        )
        lines.append(
            "- **`-recommended`** is an optional guided path (filler cuts, novel order, etc.)."
        )
        lines.append(
            "- Repo: https://github.com/rmnavz/media-catalog — licensed [CC0 1.0](../LICENSE)."
        )
        lines.append("")
        return "\n".join(lines)

    def write_markdown(self, path: Path, *, repo: Path | None = None, checked: int | None = None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            self.to_markdown(repo=repo, checked=checked),
            encoding="utf-8",
        )
