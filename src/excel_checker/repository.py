"""Directory-backed rule repository with hot reload and last-known-good rules."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from threading import RLock
from typing import TYPE_CHECKING

from .config import Rule, rule_from_dict
from .errors import ConfigError

if TYPE_CHECKING:
    from .registry import ActionRegistry


class RuleRepository:
    """Load, add, edit, and remove JSON rules from one watched directory.

    Invalid edits are reported while the last valid version of the same file
    remains active. New invalid files are ignored; deleting a file removes its
    rule on the next reload.
    """

    def __init__(self, directory: str | Path, *, registry: ActionRegistry | None = None) -> None:
        self.directory = Path(directory)
        self.registry = registry
        self.directory.mkdir(parents=True, exist_ok=True)
        self._rules_by_path: dict[Path, Rule] = {}
        self._fingerprint: tuple[tuple[str, str], ...] | None = None
        self._errors: dict[Path, str] = {}
        self._lock = RLock()
        self.reload_if_changed(force=True)

    @property
    def rules(self) -> tuple[Rule, ...]:
        with self._lock:
            rules = tuple(self._rules_by_path.values())
        return tuple(
            sorted(
                rules,
                key=lambda rule: (-rule.priority, rule.name.casefold(), str(rule.source or "")),
            )
        )

    @property
    def errors(self) -> dict[Path, str]:
        with self._lock:
            return dict(self._errors)

    def reload_if_changed(self, *, force: bool = False) -> bool:
        """Refresh the active snapshot; return True if files changed."""
        contents: dict[Path, bytes | None] = {}
        digest_entries: list[tuple[str, str]] = []
        read_failed = False
        for path in sorted(self.directory.glob("*.json"), key=lambda item: item.name.casefold()):
            try:
                raw = path.read_bytes()
                contents[path] = raw
                digest = hashlib.sha256(raw).hexdigest()
            except OSError as exc:
                contents[path] = None
                digest = f"READ_ERROR:{exc}"
                read_failed = True
            digest_entries.append((path.name, digest))
        fingerprint = tuple(digest_entries)

        with self._lock:
            if not force and not read_failed and fingerprint == self._fingerprint:
                return False
            old_by_path = dict(self._rules_by_path)

        candidates: dict[Path, Rule] = {}
        errors: dict[Path, str] = {}
        for path, raw in contents.items():
            if raw is None:
                if path in old_by_path:
                    candidates[path] = old_by_path[path]
                errors[path] = "读取失败，继续使用上次有效配置"
                continue
            try:
                document = json.loads(raw.decode("utf-8-sig"))
                candidates[path] = rule_from_dict(document, source=path, registry=self.registry)
            except (UnicodeDecodeError, json.JSONDecodeError, ConfigError) as exc:
                errors[path] = str(exc)
                if path in old_by_path:
                    candidates[path] = old_by_path[path]

        # A duplicated name makes directory dispatch ambiguous. Keep the first
        # file in lexical path order and surface an actionable repository error.
        seen_names: dict[str, Path] = {}
        unique_candidates: dict[Path, Rule] = {}
        for path in sorted(candidates, key=lambda item: item.name.casefold()):
            rule = candidates[path]
            previous = seen_names.get(rule.name.casefold())
            if previous is not None:
                errors[path] = f"配置名称 {rule.name!r} 与 {previous.name} 重复；此文件未启用"
                continue
            seen_names[rule.name.casefold()] = path
            unique_candidates[path] = rule

        with self._lock:
            self._rules_by_path = unique_candidates
            self._errors = errors
            # A transient read failure is retried on the next poll.
            self._fingerprint = None if read_failed else fingerprint
        return True

    def reload(self) -> tuple[Rule, ...]:
        self.reload_if_changed(force=True)
        return self.rules
