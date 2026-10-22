"""Deterministic selection of the rule triggered by a copied table."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .config import Rule
from .engine import ExecutionResult, RuleEngine


@dataclass(frozen=True)
class ProcessOutcome:
    matched_rule: Rule | None
    execution: ExecutionResult | None

    @property
    def executed(self) -> bool:
        return self.execution is not None


class RuleDispatcher:
    """Run only the highest-priority enabled matching rule.

    If priorities tie, rule names and source paths provide a stable order. This
    avoids surprising duplicate network calls when several rules have the same
    trigger shape.
    """

    def __init__(self, engine: RuleEngine) -> None:
        self.engine = engine

    @staticmethod
    def select_rule(table: Sequence[Sequence[object]], rules: Sequence[Rule]) -> Rule | None:
        matching = [rule for rule in rules if rule.enabled and rule.matches(table)]
        if not matching:
            return None
        return min(
            matching,
            key=lambda rule: (
                -rule.priority,
                rule.name.casefold(),
                str(rule.source or ""),
            ),
        )

    def process(self, table: Sequence[Sequence[object]], rules: Sequence[Rule]) -> ProcessOutcome:
        rule = self.select_rule(table, rules)
        if rule is None:
            return ProcessOutcome(matched_rule=None, execution=None)
        return ProcessOutcome(
            matched_rule=rule,
            execution=self.engine.execute(rule, table),
        )
