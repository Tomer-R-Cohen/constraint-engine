import pandas as pd

from constraint_engine.constraints import Constraint
from constraint_engine.decision_support import assignment_distance, generate_portfolio, verify_assignment
from constraint_engine.optimizer import SolverConfig


def test_verifier_reports_every_rule_and_assignment_integrity_independently():
    df = pd.DataFrame({"support": [True, True, False, False]}, index=[1, 2, 3, 4])
    constraints = [
        Constraint(type="capacity", hard=True, args={"group": {"kind": "all"}, "min": 2, "max": 2}, label="group size"),
        Constraint(type="separate", hard=True, args={"entity_a": 1, "entity_b": 2}, label="separate"),
        Constraint(type="together", hard=False, args={"entity_a": 3, "entity_b": 4, "weight": 2}, label="prefer together"),
        Constraint(type="balance", hard=False, args={"group": {"kind": "column", "column": "support"}, "weight": 1}, label="balance support"),
    ]

    report = verify_assignment(df, {1: [0], 2: [0], 3: [1]}, constraints, 2)

    assert report.is_valid is False
    assert report.hard_rules_violated == 3  # integrity, capacity, separation
    assert {check.constraint_id for check in report.checks} == {"assignment_integrity", *(c.id for c in constraints)}
    integrity = next(check for check in report.checks if check.constraint_id == "assignment_integrity")
    assert integrity.affected_entities == [4]
    separation = next(check for check in report.checks if check.label == "separate")
    assert separation.affected_entities == [1, 2]
    assert separation.affected_slots == []


def test_slot_label_swaps_are_not_counted_as_meaningful_alternatives():
    first = {1: [0], 2: [0], 3: [1], 4: [1]}
    relabeled = {1: [1], 2: [1], 3: [0], 4: [0]}
    changed = {1: [0], 2: [1], 3: [0], 4: [1]}

    assert assignment_distance(first, relabeled, 2) == 0
    assert assignment_distance(first, changed, 2) == 2


def test_equal_objectives_still_return_three_distinct_partitions():
    df = pd.DataFrame(index=[1, 2, 3, 4])
    size = Constraint(type="capacity", hard=True, label="size",
                      args={"group": {"kind": "all"}, "min": 2, "max": 2})
    options, _ = generate_portfolio(df, SolverConfig(num_slots=2, time_limit_seconds=2), [size], max_options=3)
    assert len(options) == 3  # The three possible pairings, not renamed slots.
    assert all(option.verification.is_valid for option in options)
    assert all(assignment_distance(a.assignment, b.assignment, 2) == 2
               for i, a in enumerate(options) for b in options[i + 1:])


def test_unique_partition_is_reported_once_without_fake_alternatives():
    df = pd.DataFrame(index=[1, 2, 3, 4])
    constraints = [
        Constraint(type="capacity", hard=True, args={"group": {"kind": "all"}, "min": 2, "max": 2}, label="size"),
        Constraint(type="together", hard=True, args={"entity_a": 1, "entity_b": 2}, label="pair"),
    ]
    options, _ = generate_portfolio(df, SolverConfig(num_slots=2, time_limit_seconds=2), constraints)
    assert len(options) == 1
    assert options[0].verification.is_valid



def test_one_possible_relaxation_still_compares_multiple_groupings():
    df = pd.DataFrame(index=range(1, 9))
    impossible = Constraint(type="capacity", hard=True, label="too few seats",
                            args={"group": {"kind": "all"}, "max": 3})
    options, _ = generate_portfolio(df, SolverConfig(num_slots=2, time_limit_seconds=2), [impossible], max_options=3)
    assert len(options) == 3
    assert all(option.relaxed_constraint_ids == [impossible.id] for option in options)
    assert all(not option.verification.is_valid for option in options)
    assert all(assignment_distance(a.assignment, b.assignment, 2) > 0
               for i, a in enumerate(options) for b in options[i + 1:])


def test_impossible_case_yields_explicit_single_rule_compromises():
    df = pd.DataFrame(index=[1, 2, 3, 4])
    together = Constraint(type="together", hard=True, args={"entity_a": 1, "entity_b": 2}, label="keep 1 and 2 together")
    separate = Constraint(type="separate", hard=True, args={"entity_a": 1, "entity_b": 2}, label="keep 1 and 2 separate")
    size = Constraint(type="capacity", hard=True, args={"group": {"kind": "all"}, "min": 2, "max": 2}, label="two per group")

    options, conflicts = generate_portfolio(
        df,
        SolverConfig(num_slots=2, time_limit_seconds=5),
        [size, together, separate],
        max_options=4,
    )

    assert {together.id, separate.id}.issubset(set(conflicts))
    assert len(options) >= 2
    assert all(not option.verification.is_valid for option in options)
    assert all(len(option.relaxed_constraint_ids) == 1 for option in options)
    assert all(option.verification.hard_rules_violated == 1 for option in options)
    assert all(option.compromises for option in options)


def test_tight_capacity_portfolio_produces_distinct_verified_options():
    df = pd.DataFrame({"flag": [True, True, True, True, False, False, False, False]}, index=range(1, 9))
    constraints = [
        Constraint(type="capacity", hard=True, args={"group": {"kind": "all"}, "min": 4, "max": 4}, label="exact size"),
        Constraint(type="balance", hard=False, args={"group": {"kind": "column", "column": "flag"}, "weight": 1}, label="balance flag"),
        Constraint(type="together", hard=False, args={"entity_a": 1, "entity_b": 2, "weight": 3}, label="prefer pair"),
    ]

    options, _ = generate_portfolio(df, SolverConfig(num_slots=2, time_limit_seconds=5), constraints, max_options=3)

    assert len(options) >= 2
    assert all(option.verification.is_valid for option in options)
    for index, option in enumerate(options):
        for other in options[index + 1:]:
            assert assignment_distance(option.assignment, other.assignment, 2) > 0


def test_verifier_covers_relationship_and_fixed_rules_and_ignores_met_soft_ones():
    df = pd.DataFrame(index=[1, 2, 3])
    assignment = {1: [0], 2: [0], 3: [1]}
    constraints = [
        Constraint(type="separate", hard=True, args={"entity_a": 1, "entity_b": 2}, label="apart"),
        Constraint(type="together", hard=True, args={"entity_a": 1, "entity_b": 3}, label="together"),
        Constraint(type="at_least_one_of", hard=True, args={"entity": 3, "candidates": [1, 2]}, label="with a partner"),
        Constraint(type="fixed", hard=True, args={"entity": 3, "slot": 0}, label="fixed"),
        Constraint(type="together", hard=False, args={"entity_a": 1, "entity_b": 2}, label="preference only"),
    ]

    report = verify_assignment(df, assignment, constraints, 2)

    violated = {check.label for check in report.checks if check.status == "violated"}
    assert violated == {"apart", "together", "with a partner", "fixed"}
    assert report.hard_rules_violated == 4
    assert report.soft_rules_satisfied == 1


def test_partner_requests_are_measured_per_requester():
    df = pd.DataFrame(index=[1, 2, 3])
    rule = Constraint(type="partner_requests", hard=False, label="requests", args={"requests": {1: [2, 3], 2: [1]}})
    met = verify_assignment(df, {1: [0], 2: [0], 3: [0]}, [rule], 2).checks[-1]
    unmet = verify_assignment(df, {1: [0], 2: [1], 3: [1]}, [rule], 2).checks[-1]
    assert (met.status, met.shortfall) == ("satisfied", 0)
    assert (unmet.status, unmet.shortfall, unmet.affected_entities) == ("violated", 2, [1, 2])


def test_tradeoffs_compare_soft_rules_by_shortfall():
    df = pd.DataFrame({"flag": [True, True, False, False]}, index=[1, 2, 3, 4])
    constraints = [
        Constraint(type="capacity", hard=True, args={"group": {"kind": "all"}, "min": 2, "max": 2}, label="two per slot"),
        Constraint(type="together", hard=False, args={"entity_a": 1, "entity_b": 2}, label="1 with 2"),
    ]
    options, _ = generate_portfolio(df, SolverConfig(num_slots=2, time_limit_seconds=2), constraints, max_options=3)
    assert len(options) == 3
    together_id = constraints[1].id
    shortfalls = sorted(option.scores[together_id]["value"] for option in options)
    assert shortfalls == [0, 1, 1]
    best = next(option for option in options if option.scores[together_id]["rank"] == "best")
    assert any("1 with 2" in gain for gain in best.gains)
