"""Every user-facing string the engine produces, in one place.

English only for now. A locale is added by giving this module a sibling with
the same names, not by editing call sites.
"""

from __future__ import annotations

# ---- optimizer ----
NUM_SLOTS_TOO_SMALL = "The number of slots must be at least 1."
BAD_SLOTS_PER_ENTITY = "Slots per entity must be a range with 0 <= min <= max (got {min}-{max})."
INTERCHANGEABLE_NEEDS_SINGLE_SLOT = "Slots can only be interchangeable when each entity holds exactly one slot."
RULE_NAMES_MISSING_SLOT = "Rule '{label}' names slot {slot}, which does not exist (slots are 1..{num_slots})."
SLOT_DOES_NOT_EXIST = "Slot {slot} does not exist (slots are 1..{num_slots})."
UNKNOWN_RULE_TYPE = "Unknown rule type: {type}"
NO_SOLUTION = "No assignment meets every mandatory rule, or the time limit ran out before one was found."

# ---- feasibility ----
FEAS_NO_SLOTS = "Number of slots"
FEAS_FEWER_ENTITIES_THAN_SLOTS_RULE = "Entities vs. slots"
FEAS_FEWER_ENTITIES_THAN_SLOTS = "There are only {n} entities for {k} slots, so some slots must stay empty."
FEAS_GROUP_TOTAL = "{total} in the group in total."
FEAS_GROUP_PLACES = "The group can fill between {fewest} and {most} places in these {count} slots."
FEAS_LOAD_OK = "Every member can hold this many slots."
FEAS_LOAD_MIN_UNREACHABLE = "Needs at least {lo} slots each, but some members can hold at most {most}."
FEAS_LOAD_MAX_UNREACHABLE = "Allows at most {hi} slots each, but some members must hold at least {fewest}."
FEAS_NEED_AT_LEAST = "At least {needed} needed ({lo} x {k} groups)."
FEAS_ROOM_FOR_AT_MOST = "Room for at most {capacity} ({hi} x {k} groups)."

# ---- verifier ----
INTEGRITY_LABEL = "Complete assignment"
INTEGRITY_OK = "Every entity holds an allowed number of slots, all of which exist."
INTEGRITY_MISSING = "{count} entities are not assigned"
INTEGRITY_WRONG_COUNT = "{count} entities hold a number of slots outside {min}-{max}"
INTEGRITY_UNKNOWN = "{count} assigned ids are not in the data"
INTEGRITY_OUT_OF_RANGE = "{count} entities hold a slot that does not exist, or the same slot twice"
COUNT_OK = "Every group is within the rule."
COUNT_OUTSIDE = "{count} groups are outside the range"
COUNT_UNEVEN = "the largest gap between groups is {gap}"
TOTAL = "total"
CELL_VALUE = "{cell}: {value}"
SHARE_OK = "Every item shares a slot as required."
SHARE_BAD = "{count} items do not share a slot as required."
STRETCH_OK = "Every stretch is within the allowed length."
STRETCH_BAD = "{count} stretches are too long or too short."
TRANSITION_OK = "No forbidden sequence occurs."
TRANSITION_BAD = "The forbidden sequence occurs {count} times."
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
EXCEPTION_DETAIL = "{label} — {parts} (rule: {range})"
EXCEPTION_SUMMARY = "{label} — {summary}"
RANGE_UP_TO = "up to {hi}"
RANGE_AT_LEAST = "at least {lo}"
TRADEOFF_BEST = "{label}: {value} — best of the options"
TRADEOFF_WORST = "{label}: {value} — weakest of the options"
TRADEOFF_BEST_RULE = "{label} — off by {value} (best of the options)"
TRADEOFF_WORST_RULE = "{label} — off by {value} (weakest of the options)"
METRIC_SLOT_SIZE_SPREAD = "Gap between slot sizes"
METRIC_LOAD_SPREAD = "Gap between the most and fewest slots per entity"
METRIC_MOVED = "Entities moved from the base"
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

# ---- rule read-backs ----
# A read-back is assembled from these pieces by readback.py; nothing in it
# is free text written by the agent.
AND = "and"
OR = "or"
YES = "yes"
NO = "no"
BAND_EXACTLY = "exactly {n}"
BAND_BETWEEN = "between {lo} and {hi}"
BAND_AT_LEAST = "at least {n}"
BAND_AT_MOST = "at most {n}"
BAND_NONE = "no"
FILTER_FLAG = " marked {column}"
FILTER_VALUE = " whose {column} is {value}"
FILTER_MEMBERS = " among {members}"
SLOT_FILTER_WHERE = " where {conditions}"
SLOT_CONDITION = "{attribute} is {values}"
SLOT_FILTER_IDS = " among {ids}"
SUBJECT_EVERY_SLOT = "every {slot}{filter}"
SUBJECT_ONE_SLOT = "{slot} {id}"
SUBJECT_EACH_OF_SLOTS = "each of the {slots} {ids}"
SUBJECT_EACH_ENTITY = "each {entity}{filter}"
SUBJECT_EACH_COLUMN = "each {column}"
SUBJECT_EACH_OF_COLUMNS = "each of {columns}"
SUBJECT_EVERY_GROUP = "every {attribute}"
SCOPE_EVERY_SLOT = "in every {slot}{filter}"
PER = " per {attribute}"
ACROSS = " across the {slots}{filter}"
COUNTING_ITEMS = ", counting {entities}{filter}"
RB_COUNT_HAS = "{subject} has {band} {noun}{tail}."
RB_COUNT_SCOPED = "{scope}, {subject} has {band} {noun}{tail}."
RB_COUNT_TOTAL = "In total, there are {band} {noun}{tail}."
RB_COUNT_NONE = "No {entity}{filter} has a {slot}{slot_filter}."
RB_FIXED_ONE = "{entity} is in {slot} {id}."
RB_FIXED_MANY = "{entity} has {slot} {id}."
RB_NEVER_ONE = "{entity} is never in {slot} {id}."
RB_NEVER_MANY = "{entity} never has {slot} {id}."
RB_EVEN_SPREAD = "Spread {what} evenly across {across}{gap}."
RB_EVEN_SIMILAR = "Give {who} a similar {amount}{scope}{gap}."
EVEN_ACROSS_SLOTS = "the {slots}{filter}"
EVEN_ACROSS_GROUPS = "the {units}"
IN_EVERY_SLOT = " in every {slot}"
EVEN_OF_EACH = "the {what} of each {column}"
EVEN_ITEMS_SLOTS = "each {entity}{filter}'s {slots}"
AMOUNT_NUMBER = "number of {noun}"
AMOUNT_SUM = "amount of {noun}"
GAP = " (at most {gap} apart)"
RB_SHARE_TOGETHER_ONE = "{a} and {b} are in the same {slot}."
RB_SHARE_TOGETHER_MANY = "{a} and {b} share at least one {slot}."
RB_SHARE_APART_ONE = "{a} and {b} are never in the same {slot}."
RB_SHARE_APART_MANY = "{a} and {b} never share a {slot}."
RB_SHARE_LIST_ONE = "{entity} is in the same {slot} as {band} of {others}."
RB_SHARE_LIST_MANY = "{entity} shares a {slot} with {band} of {others}."
RB_SHARE_COLUMN_ONE = "{subject} is in the same {slot} as {band} of the {entities} named in {column}."
RB_SHARE_COLUMN_MANY = "{subject} shares a {slot} with {band} of the {entities} named in {column}."
RB_STRETCH_WORK = "{subject} works stretches of {band} {unit}{within}{counting}{edge}."
RB_STRETCH_OFF = "{subject} has {units} off in stretches of {band} {unit}{within}{counting}{edge}."
STRETCH_WITHIN = " within each {attribute}"
RB_STRETCH_NO_GAPS = "{subject} has no gaps between {units}{within}{counting}."
RB_STRETCH_GAPS = "{subject} has gaps of at most {n} {unit} between {units}{within}{counting}."
STRETCH_COUNTING = ", counting only {slots}{filter}"
STRETCH_EDGE = " (a stretch at the start or end may be shorter)"
STRETCH_IGNORE_EDGES = " (stretches at the start or end are not counted)"
RB_TRANSITION = "After a {slot}{after}, {subject} has no {slot}{forbid} {window}."
WINDOW_NEXT = "the next {unit}"
WINDOW_NEXT_N = "in the next {n} {units}"
RB_SLOTS_PER_ENTITY = "Each {entity} has {band} {what}."
RB_HARD = "Mandatory."
RB_SOFT = "Preference, {level} priority."
RB_INACTIVE = "Switched off."
PRIORITY_NAMES = {"low": "low", "medium": "medium", "high": "high"}

# ---- spec checks ----
SPEC_SELECTOR_MEMBERS_OR_COLUMN = "An entity selector uses either 'members' or 'column' (with an optional 'value'), not both."
SPEC_VALUE_NEEDS_COLUMN = "'value' needs a 'column'."
SPEC_SLOTS_IDS_OR_WHERE = "A slot selector uses either 'ids' or 'where', not both."
SPEC_BAD_SLOTS_PER_ENTITY = "slots_per_entity must be [min, max] with 0 <= min <= max."
SPEC_PRIORITY_ON_HARD_RULE = "Only soft rules take a priority; a hard rule must always hold."
SPEC_BAND_EMPTY = "Give 'min', 'max' or both."
SPEC_BAND_REVERSED = "'min' cannot be larger than 'max'."
SPEC_PER_COLUMN_ONE_KIND = "Group items by either 'column' or 'flag_columns', not both."
SPEC_SUM_ONE_KIND = "Sum either an 'item_column' or a 'slot_attribute', not both."
SPEC_COUNT_NEEDS_TARGET = "Give 'min', 'max', or 'even'."
SPEC_GAP_NEEDS_EVEN = "'max_gap' only applies with 'even'."
SPEC_SHARE_ONE_FORM = "A share rule takes either 'item' with 'with', or 'with_column' (optionally with 'items')."
SPEC_NOT_NUMERIC = "column '{column}' must hold a non-negative number for every item counted ({bad})."
SPEC_SLOT_NOT_NUMERIC = "slot '{slot}' needs a non-negative number for '{attribute}'."
SPEC_DUPLICATE_IDS = "Duplicate {kind} ids: {ids}."
SPEC_PROBLEM = "Rule {rule}: {message}"
SPEC_UNKNOWN_ID_COLUMN = "The id column '{column}' is not in the sheet. Columns: {columns}."
SPEC_UNKNOWN_ENTITY = "there is no entity '{entity}' in the data."
SPEC_UNKNOWN_COLUMN = "there is no column '{column}'. Columns: {columns}."
SPEC_NOT_A_FLAG = "column '{column}' is not a yes/no column (it holds {values}); give a 'value' to pick rows."
SPEC_UNKNOWN_VALUE = "no row has {column} = {value}. Values in the data: {values}."
SPEC_UNKNOWN_SLOT = "there is no slot '{slot}'."
SPEC_UNKNOWN_ATTRIBUTE = "no slot has the attribute '{attribute}'. Slot attributes: {attributes}."
SPEC_NO_SLOTS_SELECTED = "the slot selection matches no slot."
SPEC_SLOT_MISSING_ATTRIBUTE = "slot '{slot}' has no '{attribute}' attribute."
SPEC_SAME_ENTITY_TWICE = "'{entity}' is named twice; the rule needs two different entities."
SPEC_DUPLICATE_ENTITIES = "The entity table has duplicate ids."
SPEC_TOO_MANY_SLOTS_PER_ENTITY = "slots_per_entity allows {max} slots each, but there are only {count} slots."

# ---- workspace ----
WS_NO_SLOTS = "This problem has no slots yet; set them first."
WS_UNSUPPORTED_FILE = "Unsupported file type '{extension}'. Use .csv or .xlsx."
WS_UNKNOWN_PROBLEM = "There is no problem '{problem}'. Problems: {known}."
WS_SLOTS_OR_GRID = "Give either 'slots' (a list) or 'grid' (attribute values to combine), not both."
WS_DUPLICATE_RULE = "There is already a rule '{rule}'."
WS_UNKNOWN_RULE = "There is no rule '{rule}'. Rules: {known}."
WS_UNKNOWN_OPTION = "There is no option '{option}'. Options: {known}."
EXPORT_ASSIGNED = "Assigned"
EXPORT_SLOT = "Slot"
EXPORT_COUNT = "Count"
EXPORT_ITEMS = "Items"
EXPORT_SHEET_ITEMS = "By item"
EXPORT_SHEET_SLOTS = "By slot"

# ---- MCP server (read by any MCP client and any model) ----
SERVER_NAME = "constraint-engine"
SERVER_INSTRUCTIONS = """\
An assignment solver: it places items (the rows of a data file: students,
employees, lessons...) into slots (classes, shifts, time+room cells...)
under rules, and returns three verified options per solve.

Workflow: load_data -> set_slots -> add_rule (one per rule the user states)
-> list_rules -> solve -> get_option / export_option.

How to work with the user:
- Act on what the user asked; do not ask permission first. Load data, set
  slots and add rules as soon as they are stated, and solve when asked.
  Adding a rule is checked by the engine and undone with remove_rule, so
  confirmation happens after, not before.
- Turn each rule the user states into one add_rule call (several rules in
  one message = several calls). Then list every returned read_back word for
  word and invite corrections. The read_back is the only description of a
  rule: never write your own version of what a rule means.
- If add_rule rejects a rule, fix the call and retry; ask the user only when
  their meaning is genuinely unclear.
- Never invent numbers or facts about a solution: quote tool results only.
- To show a schedule, call get_option and paste its table_by_slot or
  table_by_item exactly as returned. Never retype or rebuild a schedule
  yourself: a retyped schedule can silently drop or swap names.
- Every limit the user states is a rule (add_rule), including how many
  slots each item gets ("2 to 4 shifts each"). set_slots' slots_per_item is
  only the outer bound; a limit kept there cannot be named when rules
  conflict or bent in a compromise.
- The rules belong to the user. Never add, change, relax, switch off or drop
  a rule unless the user asks for that change.
- When rules cannot all hold, say which rules conflict (conflicting_rules)
  and what each option breaks (exceptions), and let the user choose. Do not
  recommend changing a rule.
- Present every option of a round, with what each does better and worse.
"""
TOOL_LOAD_DATA = (
    "Load a data file (.csv or .xlsx) whose rows are the items to place. Returns a problem_id, the item count, "
    "the id column (guessed when not given) and each usable column with its kind (flag = yes/no, category, "
    "number) and values. header_row is the 1-based row holding the column names."
)
TOOL_DESCRIBE_DATA = "Describe a loaded problem's items and columns again."
TOOL_SET_SLOTS = (
    "Define the slots items are placed into. Either 'slots' (a list of {id, attributes}) or 'grid' (attribute "
    "-> list of values; every combination becomes a slot, e.g. {\"day\": [\"Mon\", \"Tue\"], \"shift\": "
    "[\"morning\", \"night\"]} gives Mon-morning, Mon-night, ...). List slots in time order: rules over time "
    "follow it. slots_per_item is only the outer bound on slots per item: [1, 1] = each item in exactly one slot "
    "(the default, placement); a roster uses [0, number of slots]. Put any limit the user states, like '2 to 4 "
    "shifts each', in add_rule instead (count, per_item each, per_slot all). vocabulary sets the words read-backs use (employee/shift, "
    "student/class)."
)
TOOL_ADD_RULE = (
    "Add one rule. It is checked against the data (columns, values, item ids, slot ids and attributes) and "
    "returned as a plain-English read_back to show the user. Every rule is mandatory (mode 'hard') or a "
    "preference (mode 'soft' with priority low/medium/high). Four rule types:\n"
    "- count: count placements per group and keep each within min..max, or 'even'. per_item: 'all', 'each', "
    "{column} (one group per value) or {flag_columns}; per_slot: 'all', 'each' or {attribute} (e.g. per day). "
    "Optional 'sum' adds up an item column or slot attribute (hours, size) instead of counting. Examples: "
    "class size 25-28 = per_item all, per_slot each, min 25, max 28; 3-6 shifts each = per_item each, "
    "per_slot all; one shift a day = per_item each, per_slot {attribute: day}, max 1; Ana fixed to mon-am = "
    "items {members: [Ana]}, slots {ids: [mon-am]}, per_item each, per_slot all, min 1; no teacher in two "
    "places = per_item {column: Teacher}, per_slot {attribute: time}, max 1; spread schools evenly = "
    "per_item {column: School}, per_slot each, even 'slots'; fair shifts = per_item each, per_slot all, "
    "even 'items'.\n"
    "- share: an item shares a slot with min..max of a list ('item' + 'with'), or every item with the items "
    "named in a column ('with_column'). Together = min 1; apart = max 0.\n"
    "- stretch: lengths of worked (of 'work') or free (of 'off') stretches of time units made by the slot "
    "attribute 'per' (e.g. at most 5 days in a row; days off at least 2 together). within_each restarts per "
    "value (periods within each day); ignore_edges skips time before the first and after the last (gaps).\n"
    "- transition: after a slot matching 'after', no slot matching 'not_followed_by' in the next 'next' units "
    "of 'per' (no morning after a night).\n"
    "Selectors: items {} | {column} (flag is yes) | {column, value} | {members}; slots {} | {ids} | "
    "{where: {attribute: value or [values]}}."
)
TOOL_REMOVE_RULE = "Remove a rule (only when the user asks). Returns the read-back of what was removed."
TOOL_SET_RULE_ACTIVE = "Switch a rule off or back on without deleting it (only when the user asks)."
TOOL_LIST_RULES = "Every rule of the problem with its id and read-back, plus the slots-per-item setting."
TOOL_SOLVE = (
    "Solve: returns a round of up to 3 genuinely different options. mode 'perfect' = every option meets every "
    "mandatory rule; 'compromise' = they cannot all hold, conflicting_rules says which clash and each option's "
    "exceptions say exactly what it breaks. Each option lists what it does better and worse than the others. "
    "refine_option re-solves near an earlier option (the three results change little, more, freely); emphasis "
    "'preferences' or 'balance' tilts the soft rules."
)
TOOL_GET_OPTION = (
    "An option's assignment, with table_by_slot and table_by_item: the schedule as ready-made tables to show "
    "the user exactly as returned. With 'item': that item's slots and every rule involving it (why it is where "
    "it is). With 'slot': the items in that slot."
)
TOOL_EXPORT_OPTION = "Write an option to a file: .xlsx (sheets by item and by slot) or .csv (by item)."
TOOL_GET_SPEC = "The problem as a versioned JSON spec (slots, settings, rules), to save or reuse."
TOOL_SET_SPEC = "Replace slots, settings and rules with a saved JSON spec, checked against this problem's data."
TABLE_EMPTY = "—"
TABLE_ITEM = "Item"
TABLE_SLOTS = "Slots"
