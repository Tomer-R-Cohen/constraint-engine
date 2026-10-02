"""Every user-facing string the engine produces, in one place.

English only for now. A locale is added by giving this module a sibling with
the same names, not by editing call sites.
"""

from __future__ import annotations

# ---- optimizer ----
NUM_SLOTS_TOO_SMALL = "The number of slots must be at least 1."
SLOT_DOES_NOT_EXIST = "Slot {slot} does not exist (slots are 1..{num_slots})."
FIXED_TO_MISSING_SLOT = "Entity {entity} is fixed to slot {slot}, which does not exist (slots are 1..{num_slots})."
UNKNOWN_RULE_TYPE = "Unknown rule type: {type}"
NO_SOLUTION = "No assignment meets every mandatory rule, or the time limit ran out before one was found."

# ---- feasibility ----
FEAS_NO_SLOTS = "Number of slots"
FEAS_FEWER_ENTITIES_THAN_SLOTS_RULE = "Entities vs. slots"
FEAS_FEWER_ENTITIES_THAN_SLOTS = "There are only {n} entities for {k} slots, so some slots must stay empty."
FEAS_GROUP_TOTAL = "{total} in the group in total."
FEAS_NEED_AT_LEAST = "At least {needed} needed ({lo} x {k} slots)."
FEAS_ROOM_FOR_AT_MOST = "Room for at most {capacity} ({hi} x {k} slots)."

# ---- verifier ----
INTEGRITY_LABEL = "Complete assignment"
INTEGRITY_OK = "Every entity is assigned once, to a slot that exists."
INTEGRITY_MISSING = "{count} entities are not assigned"
INTEGRITY_UNKNOWN = "{count} assigned ids are not in the data"
INTEGRITY_OUT_OF_RANGE = "{count} entities are assigned to a slot that does not exist"
CAPACITY_OK = "Every slot is within the range."
CAPACITY_BAD = "{count} slots are outside the range."
PAIR_OK = "The rule holds for both entities."
PAIR_BAD = "The rule does not hold for these two entities."
PAIR_SAME = "same slot"
PAIR_DIFFERENT = "different slots"
AT_LEAST_ONE_OK = "At least one entity from the list shares the slot."
AT_LEAST_ONE_BAD = "No entity from the list shares the slot."
AT_LEAST_ONE_EXPECTED = "at least 1"
FIXED_OK = "The fixed placement is kept."
FIXED_BAD = "The entity is not in the slot it is fixed to."
BALANCE_OK = "The group is spread evenly."
BALANCE_BAD = "The largest gap between slots is {gap}."
BALANCE_EXPECTED = "gap 0"
REQUESTS_NONE = "No requests were entered; this rule was not measured."
REQUESTS_OK = "Every request checked was met."
REQUESTS_BAD = "{count} entities have a request that was not met."
NO_CHECKER = "There is no independent check for rule type '{type}'."
VERIFY_VALID = "The assignment is valid: all {ok} mandatory checks passed."
VERIFY_INVALID = "The assignment is not valid: {bad} mandatory checks failed; {ok} passed."

# ---- options ----
STRATEGY_TITLES = {
    "balanced": "Current priorities",
    "preferences": "Favor requests",
    "balance": "Favor even slots",
}
REFINE_STEP_LABELS = ["Small change", "Medium change", "Free change"]
COMPROMISE_SINGLE = "Exception to: {label}"
COMPROMISE_MULTI = "Smallest exception"
TITLE_JOIN = " · "
SLOT_COUNT = "slot {slot}: {count}"
EXCEPTION_DETAIL = "{label} — {parts} (rule: {range})"
EXCEPTION_SUMMARY = "{label} — {summary}"
RANGE_UP_TO = "up to {hi}"
RANGE_AT_LEAST = "at least {lo}"
TRADEOFF_BEST = "{label}: {value} — best of the options"
TRADEOFF_WORST = "{label}: {value} — weakest of the options"
METRIC_SLOT_SIZE_SPREAD = "Gap between slot sizes"
METRIC_MOVED = "Entities moved from the base"
METRIC_RULE_SHORTFALL = "{label} (shortfall)"
QUESTION_ALL_VALID = "What matters more here: meeting more requests, or more even slots?"
QUESTION_ALL_VALID_REASON = "Every option meets every mandatory rule, and each favors a different goal."
QUESTION_COMPROMISE = "Which exception is easier to accept?"
QUESTION_COMPROMISE_REASON = (
    "No assignment meets every mandatory rule together; each option bends a different rule "
    "by the smallest amount found."
)

# ---- loading ----
FILE_NOT_FOUND = "File not found: {path}"
FILE_OPEN_ERROR = "Could not open {path}: {error}"
SHEET_NOT_FOUND = "Sheet '{sheet}' was not found. Available sheets: {sheets}"
SHEET_READ_ERROR = "Could not read sheet '{sheet}': {error}"
ID_COLUMN_NOT_UNIQUE = "The id column '{column}' must have a unique value in every row."
REMOVED_BLANK_ROWS = "Removed {count} completely blank rows."
REMOVED_ROWS_WITHOUT_ID = "Removed {count} rows with no value in '{column}'."
REMOVED_EMPTY_COLUMNS = "Removed empty columns: {columns}"
