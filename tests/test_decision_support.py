import pandas as pd

from constraint_engine.decision_support import assignment_distance, describe_exceptions, generate_portfolio, verify_assignment
from constraint_engine.optimizer import SolverConfig
from constraint_engine.rules import apart, fixed, flag, per_item, per_slot, share, spread, together, with_one_of


def test_verifier_reports_every_rule_and_assignment_integrity_independently():
    df = pd.DataFrame({"support": [True, True, False, False]}, index=[1, 2, 3, 4])
    constraints = [
        per_slot("group size", min=2, max=2),
        apart(1, 2, "separate"),
        together(3, 4, "prefer together", hard=False, weight=2),
        spread("balance support", items=flag("support")),
    ]

    report = verify_assignment(df, {1: [0], 2: [0], 3: [1]}, constraints, 2)

    assert report.is_valid is False
    assert report.hard_rules_violated == 3  # integrity, size, separation
    assert {check.constraint_id for check in report.checks} == {"assignment_integrity", *(c.id for c in constraints)}
    integrity = next(check for check in report.checks if check.constraint_id == "assignment_integrity")
    assert integrity.affected_entities == [4]
    separation = next(check for check in report.checks if check.label == "separate")
    assert separation.affected_entities == [1, 2]
    assert separation.affected_slots == []


def test_count_checks_name_the_cells_outside_the_range():
    df = pd.DataFrame(index=[1, 2, 3])
    rule = per_slot("at most 1 each", max=1)
    report = verify_assignment(df, {1: [0], 2: [0], 3: [1]}, [rule], 2, slot_names=["7A", "7B"])
    check = report.checks[-1]
    assert (check.status, check.shortfall, check.actual, check.affected_slots) == ("violated", 1, {"7A": 2}, ["7A"])
    assert describe_exceptions(report)[0]["text"] == "at most 1 each — 7A: 2 (rule: up to 1)"


def test_per_item_counts_are_checked_per_group_of_slots():
    # Slots 0-1 are day one, 2-3 day two. Entity 1 works twice on day one.
    df = pd.DataFrame(index=[1, 2])
    rule = per_item("one a day", slot_groups=[[0, 1], [2, 3]], slot_group_labels=["day 1", "day 2"], max=1)
    check = verify_assignment(df, {1: [0, 1], 2: [2]}, [rule], 4, (0, 4)).checks[-1]
    assert (check.status, check.actual, check.affected_entities) == ("violated", {"1 · day 1": 2}, [1])


def test_verifier_covers_share_and_fixed_rules_and_ignores_met_soft_ones():
    df = pd.DataFrame(index=[1, 2, 3])
    assignment = {1: [0], 2: [0], 3: [1]}
    constraints = [
        apart(1, 2, "apart"),
        together(1, 3, "together"),
        with_one_of(3, [1, 2], "with a partner"),
        fixed(3, 0, "fixed"),
        together(1, 2, "preference only", hard=False),
    ]

    report = verify_assignment(df, assignment, constraints, 2)

    violated = {check.label for check in report.checks if check.status == "violated"}
    assert violated == {"apart", "together", "with a partner", "fixed"}
    assert report.hard_rules_violated == 4
    assert report.soft_rules_satisfied == 1


def test_share_shortfall_counts_missing_partners():
    df = pd.DataFrame(index=[1, 2, 3, 4])
    rule = share(1, [2, 3, 4], "1 with at least two", min=2, hard=False)
    met = verify_assignment(df, {1: [0], 2: [0], 3: [0], 4: [1]}, [rule], 2).checks[-1]
    unmet = verify_assignment(df, {1: [0], 2: [1], 3: [1], 4: [1]}, [rule], 2).checks[-1]
    assert (met.status, met.shortfall) == ("satisfied", 0)
    assert (unmet.status, unmet.shortfall) == ("violated", 2)


def test_slot_label_swaps_are_not_counted_as_meaningful_alternatives():
    first = {1: [0], 2: [0], 3: [1], 4: [1]}
    relabeled = {1: [1], 2: [1], 3: [0], 4: [0]}
    changed = {1: [0], 2: [1], 3: [0], 4: [1]}

    assert assignment_distance(first, relabeled, 2) == 0
    assert assignment_distance(first, changed, 2) == 2


def test_equal_objectives_still_return_three_distinct_partitions():
    df = pd.DataFrame(index=[1, 2, 3, 4])
    options, _ = generate_portfolio(df, SolverConfig(num_slots=2, time_limit_seconds=2),
                                    [per_slot("size", min=2, max=2)], max_options=3)
    assert len(options) == 3  # The three possible pairings, not renamed slots.
    assert all(option.verification.is_valid for option in options)
    assert all(assignment_distance(a.assignment, b.assignment, 2) == 2
               for i, a in enumerate(options) for b in options[i + 1:])


def test_unique_partition_is_reported_once_without_fake_alternatives():
    df = pd.DataFrame(index=[1, 2, 3, 4])
    options, _ = generate_portfolio(df, SolverConfig(num_slots=2, time_limit_seconds=2),
                                    [per_slot("size", min=2, max=2), together(1, 2)])
    assert len(options) == 1
    assert options[0].verification.is_valid


def test_one_possible_relaxation_still_compares_multiple_groupings():
    df = pd.DataFrame(index=range(1, 9))
    impossible = per_slot("too few seats", max=3)
    options, _ = generate_portfolio(df, SolverConfig(num_slots=2, time_limit_seconds=2), [impossible], max_options=3)
    assert len(options) == 3
    assert all(option.relaxed_constraint_ids == [impossible.id] for option in options)
    assert all(not option.verification.is_valid for option in options)
    assert all(assignment_distance(a.assignment, b.assignment, 2) > 0
               for i, a in enumerate(options) for b in options[i + 1:])


def test_impossible_case_yields_explicit_single_rule_compromises():
    df = pd.DataFrame(index=[1, 2, 3, 4])
    with_ = together(1, 2, "keep 1 and 2 together")
    without = apart(1, 2, "keep 1 and 2 apart")
    size = per_slot("two per group", min=2, max=2)

    options, conflicts = generate_portfolio(df, SolverConfig(num_slots=2, time_limit_seconds=5), [size, with_, without],
                                            max_options=4)

    assert {with_.id, without.id}.issubset(set(conflicts))
    assert len(options) >= 2
    assert all(not option.verification.is_valid for option in options)
    assert all(len(option.relaxed_constraint_ids) == 1 for option in options)
    assert all(option.verification.hard_rules_violated == 1 for option in options)
    assert all(option.compromises for option in options)


def test_tight_count_portfolio_produces_distinct_verified_options():
    df = pd.DataFrame({"flag": [True, True, True, True, False, False, False, False]}, index=range(1, 9))
    constraints = [
        per_slot("exact size", min=4, max=4),
        spread("balance flag", items=flag("flag")),
        together(1, 2, "prefer pair", hard=False, weight=3),
    ]

    options, _ = generate_portfolio(df, SolverConfig(num_slots=2, time_limit_seconds=5), constraints, max_options=3)

    assert len(options) >= 2
    assert all(option.verification.is_valid for option in options)
    for index, option in enumerate(options):
        for other in options[index + 1:]:
            assert assignment_distance(option.assignment, other.assignment, 2) > 0


def test_tradeoffs_compare_soft_rules_by_shortfall():
    df = pd.DataFrame({"flag": [True, True, False, False]}, index=[1, 2, 3, 4])
    constraints = [per_slot("two per slot", min=2, max=2), together(1, 2, "1 with 2", hard=False)]
    options, _ = generate_portfolio(df, SolverConfig(num_slots=2, time_limit_seconds=2), constraints, max_options=3)
    assert len(options) == 3
    together_id = constraints[1].id
    shortfalls = sorted(option.scores[together_id]["value"] for option in options)
    assert shortfalls == [0, 1, 1]
    best = next(option for option in options if option.scores[together_id]["rank"] == "best")
    assert any("1 with 2" in gain for gain in best.gains)


def test_options_differ_by_the_minimum_distance_when_slots_are_distinct():
    # One slot each, slots NOT interchangeable (a timetable): later options
    # must still be genuinely different, by at least the minimum distance.
    # (Regression: the exclusion once constrained only the last item.)
    df = pd.DataFrame(index=[f"lesson{i}" for i in range(6)])
    cfg = SolverConfig(num_slots=6, slots_interchangeable=False, time_limit_seconds=5)
    options, _ = generate_portfolio(df, cfg, [per_slot("one per period", max=1)], max_options=3)
    assert len(options) == 3
    for i, a in enumerate(options):
        for b in options[i + 1:]:
            assert assignment_distance(a.assignment, b.assignment, 6, interchangeable=False) >= 1


def test_excluded_answer_is_never_returned_again():
    from constraint_engine.optimizer import optimize
    df = pd.DataFrame(index=["a", "b", "c", "d"])
    cfg = SolverConfig(num_slots=4, slots_interchangeable=False, time_limit_seconds=5)
    rules = [per_slot("one each", max=1)]
    first = optimize(df, cfg, rules)
    second = optimize(df, cfg, rules, excluded_assignments=[first.assignment], min_assignment_distance=3)
    moved = sum(first.assignment[e] != second.assignment[e] for e in df.index)
    assert moved >= 3
