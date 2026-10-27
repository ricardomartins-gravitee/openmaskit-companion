import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "coverage_gate", ROOT / "scripts/check_coverage.py"
)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def report():
    counts = {
        "covered_lines": 95,
        "num_statements": 100,
        "covered_branches": 95,
        "num_branches": 100,
    }
    return {"files": {"module.py": {"summary": counts}}, "totals": dict(counts)}


def test_exact_floor_and_modules_without_branches_are_accepted():
    value = report()
    assert not gate.check(value, {"module.py"})[1]
    value["files"]["module.py"]["summary"].update(covered_branches=0, num_branches=0)
    assert not gate.check(value, {"module.py"})[1]


def test_overall_coverage_cannot_hide_a_weak_module_or_branch_gap():
    for field, value in [("covered_lines", 94), ("covered_branches", 89)]:
        data = report()
        data["files"]["module.py"]["summary"][field] = value
        assert gate.check(data, {"module.py"})[1]


def test_missing_modules_and_a_low_total_fail_closed():
    assert gate.check(report(), {"new_module.py"})[1]
    data = copy.deepcopy(report())
    data["totals"]["covered_lines"] = 94
    assert gate.check(data, {"module.py"})[1]


@pytest.mark.parametrize(
    "covered,total", [(-1, 10), (11, 10), (1, -1), ("95", 100), (1, None), (True, 1)]
)
def test_malformed_counters_are_rejected(covered, total):
    with pytest.raises(ValueError):
        gate.percentage(covered, total)
