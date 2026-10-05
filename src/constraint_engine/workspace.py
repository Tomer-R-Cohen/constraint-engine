"""The working state behind the tools: problems built up step by step.

A problem starts from a data file (one row per item), gets its slots, then
its rules one at a time -- each checked against the data and read back --
and is solved in rounds of options. Every round is stored, so an answer is
looked up, never re-solved, and carries the fingerprints of what made it.

Given a store folder, every problem is saved there after each change (a
copy of its data file plus problem.json) and loaded back on start, so work
survives a restart.

Nothing here knows about any particular agent, client or transport; the
MCP server (server.py) is a thin layer over these methods, and any other
front end can use them the same way.
"""

from __future__ import annotations

import itertools
import json
import os
import shutil
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd
from pydantic import TypeAdapter

from constraint_engine import text
from constraint_engine.compiler import SpecError, check_spec, compile_spec, entity_table, solve_spec
from constraint_engine.dataset_schema import describe_columns, guess_id_column
from constraint_engine.excel_loader import load_workbook
from constraint_engine.readback import describe_rule, describe_settings
from constraint_engine.spec import EntitiesSource, ProblemSpec, Rule, Settings, Slot, Vocabulary, dump_spec, load_spec


class WorkspaceError(Exception):
    """A request that cannot be carried out; the message says why."""


@dataclass
class Problem:
    id: str
    raw: pd.DataFrame
    name: str = ""
    source: str = ""
    # How the data file was read, so a stored copy reads back the same.
    sheet: Optional[str] = None
    header_row: int = 1
    id_column: Optional[str] = None
    vocabulary: Vocabulary = field(default_factory=Vocabulary)
    slots: list[Slot] = field(default_factory=list)
    settings: Settings = field(default_factory=Settings)
    rules: list = field(default_factory=list)
    rounds: list[dict] = field(default_factory=list)

    def spec(self, rules: Optional[list] = None) -> ProblemSpec:
        if not self.slots:
            raise WorkspaceError(text.WS_NO_SLOTS)
        return ProblemSpec(
            name=self.name, vocabulary=self.vocabulary,
            entities=EntitiesSource(source=self.source or None, id_column=self.id_column),
            slots=self.slots, settings=self.settings, rules=self.rules if rules is None else rules,
        )

    def items(self) -> pd.DataFrame:
        """The item table: one row per item, indexed by its id."""
        # Only the id column matters for building it.
        id_only = ProblemSpec(entities=EntitiesSource(id_column=self.id_column), slots=[Slot(id="-")])
        try:
            return entity_table(self.raw, id_only)
        except SpecError as error:
            raise WorkspaceError("\n".join(error.problems)) from error
        except ValueError as error:
            raise WorkspaceError(str(error)) from error


def _jsonable(value: Any) -> Any:
    """Tool results go over JSON: numpy scalars, tuples and non-string keys
    become plain values."""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    if isinstance(value, float) and value != value:
        return None
    return value


def _cell(text_value: str) -> str:
    return str(text_value).replace("|", "\\|")


def _tables(problem: Problem, assignment: dict) -> dict:
    """The schedule as Markdown tables, built by code so it can be shown
    exactly as solved -- a model retyping a schedule drops names.

    By slot: a grid when the slots are every combination of two attributes
    (day x shift), else one row per slot. By item: one row per item."""
    holders = {s.id: [e for e, slots in assignment.items() if s.id in slots] for s in problem.slots}
    names = list(problem.slots[0].attributes) if problem.slots else []
    grid = len(names) == 2 and all(list(s.attributes) == names for s in problem.slots)
    if grid:
        rows = list(dict.fromkeys(s.attributes[names[0]] for s in problem.slots))
        columns = list(dict.fromkeys(s.attributes[names[1]] for s in problem.slots))
        grid = len(rows) * len(columns) == len(problem.slots)
    if grid:
        where = {(s.attributes[names[0]], s.attributes[names[1]]): s.id for s in problem.slots}
        lines = ["| " + " | ".join([_cell(names[0])] + [_cell(c) for c in columns]) + " |",
                 "|" + "---|" * (len(columns) + 1)]
        for row in rows:
            cells = [", ".join(map(_cell, holders[where[row, column]])) or text.TABLE_EMPTY for column in columns]
            lines.append("| " + " | ".join([_cell(row)] + cells) + " |")
    else:
        lines = [f"| {text.EXPORT_SLOT} | {text.EXPORT_COUNT} | {text.EXPORT_ITEMS} |", "|---|---|---|"]
        lines += [f"| {_cell(slot)} | {len(items)} | {', '.join(map(_cell, items)) or text.TABLE_EMPTY} |"
                  for slot, items in holders.items()]
    by_item = [f"| {text.TABLE_ITEM} | {text.TABLE_SLOTS} |", "|---|---|"]
    by_item += [f"| {_cell(e)} | {', '.join(map(_cell, slots)) or text.TABLE_EMPTY} |" for e, slots in assignment.items()]
    return {"table_by_slot": "\n".join(lines), "table_by_item": "\n".join(by_item)}


def read_table(path: str, sheet: Optional[str] = None, header_row: int = 1) -> pd.DataFrame:
    """A data file as a raw table: .csv, or a sheet of .xlsx/.xlsm."""
    if not os.path.exists(path):
        raise WorkspaceError(text.FILE_NOT_FOUND.format(path=path))
    extension = os.path.splitext(path)[1].lower()
    if extension == ".csv":
        raw = pd.read_csv(path, skiprows=header_row - 1).dropna(how="all")
        return raw.reset_index(drop=True)
    if extension in (".xlsx", ".xlsm"):
        return load_workbook(path, sheet_name=sheet, header_row_1indexed=header_row).raw_df
    raise WorkspaceError(text.WS_UNSUPPORTED_FILE.format(extension=extension or "(none)"))


_RULES = TypeAdapter(list[Rule])
_PROBLEM_FILE = "problem.json"


class Workspace:
    def __init__(self, store: Optional[str] = None):
        self.store = store
        self.problems: dict[str, Problem] = {}
        if store:
            os.makedirs(store, exist_ok=True)
            for problem_id in sorted(os.listdir(store)):
                if os.path.exists(os.path.join(store, problem_id, _PROBLEM_FILE)):
                    self.problems[problem_id] = self._load(problem_id)

    # ---- storage ----

    def _folder(self, problem_id: str) -> str:
        return os.path.join(self.store, problem_id)

    def _data_file(self, problem: Problem) -> str:
        return os.path.join(self._folder(problem.id), "data" + os.path.splitext(problem.source)[1].lower())

    def _save(self, problem: Problem) -> None:
        if not self.store:
            return
        record = {
            "id": problem.id, "name": problem.name, "source": problem.source, "sheet": problem.sheet,
            "header_row": problem.header_row, "id_column": problem.id_column,
            "vocabulary": problem.vocabulary.model_dump(mode="json"),
            "slots": [slot.model_dump(mode="json") for slot in problem.slots],
            "settings": problem.settings.model_dump(mode="json"),
            "rules": _RULES.dump_python(problem.rules, mode="json"),
            "rounds": problem.rounds,
        }
        path = os.path.join(self._folder(problem.id), _PROBLEM_FILE)
        # Write then rename, so a crash mid-write never leaves half a file.
        with open(path + ".tmp", "w", encoding="utf-8") as out:
            json.dump(record, out, ensure_ascii=False, indent=1)
        os.replace(path + ".tmp", path)

    def _load(self, problem_id: str) -> Problem:
        with open(os.path.join(self._folder(problem_id), _PROBLEM_FILE), encoding="utf-8") as stored:
            record = json.load(stored)
        problem = Problem(
            id=record["id"], raw=pd.DataFrame(), name=record["name"], source=record["source"],
            sheet=record["sheet"], header_row=record["header_row"], id_column=record["id_column"],
            vocabulary=Vocabulary.model_validate(record["vocabulary"]),
            slots=[Slot.model_validate(slot) for slot in record["slots"]],
            settings=Settings.model_validate(record["settings"]),
            rules=_RULES.validate_python(record["rules"]), rounds=record["rounds"],
        )
        problem.raw = read_table(self._data_file(problem), problem.sheet, problem.header_row)
        return problem

    def problem(self, problem_id: str) -> Problem:
        if problem_id not in self.problems:
            raise WorkspaceError(text.WS_UNKNOWN_PROBLEM.format(problem=problem_id, known=", ".join(self.problems) or "-"))
        return self.problems[problem_id]

    # ---- data ----

    def load_data(self, path: str, sheet: Optional[str] = None, header_row: int = 1,
                  id_column: Optional[str] = None, name: str = "") -> dict:
        raw = read_table(path, sheet, header_row)
        if id_column is not None and id_column not in raw.columns:
            raise WorkspaceError(text.SPEC_UNKNOWN_ID_COLUMN.format(column=id_column, columns=", ".join(map(str, raw.columns))))
        guessed = id_column is None
        problem = Problem(id=uuid.uuid4().hex[:6], raw=raw, name=name, source=os.path.basename(path),
                          sheet=sheet, header_row=header_row,
                          id_column=id_column if id_column is not None else guess_id_column(raw))
        problem.items()  # refuses duplicate or missing ids now, not at solve time
        if self.store:
            os.makedirs(self._folder(problem.id), exist_ok=True)
            shutil.copyfile(path, self._data_file(problem))
        self.problems[problem.id] = problem
        self._save(problem)
        return {"problem_id": problem.id, **self.describe_data(problem.id), "id_column_guessed": guessed}

    def describe_data(self, problem_id: str) -> dict:
        problem = self.problem(problem_id)
        skip = {problem.id_column} if problem.id_column else set()
        columns = [
            {"name": c.name, "kind": c.kind, "values": c.values, "flagged": c.true_count if c.kind == "flag" else None,
             "filled": c.filled_count}
            for c in describe_columns(problem.raw, skip=skip).columns
        ]
        other = [str(c) for c in problem.raw.columns if c not in skip and c not in {col["name"] for col in columns}]
        items = problem.items().index.tolist()
        return _jsonable({
            "items": len(items), "id_column": problem.id_column, "first_ids": items[:10],
            "columns": columns, "other_columns": other,
        })

    # ---- slots and settings ----

    def set_slots(self, problem_id: str, slots: Optional[list[Slot]] = None, grid: Optional[dict[str, list]] = None,
                  vocabulary: Optional[Vocabulary] = None, slots_per_item: Optional[tuple[int, int]] = None,
                  slots_interchangeable: Optional[bool] = None) -> dict:
        problem = self.problem(problem_id)
        if (slots is None) == (grid is None):
            raise WorkspaceError(text.WS_SLOTS_OR_GRID)
        if grid is not None:
            names = list(grid)
            slots = [Slot(id="-".join(str(v) for v in combo), attributes=dict(zip(names, combo)))
                     for combo in itertools.product(*grid.values())]
        settings = problem.settings.model_copy(update={
            key: value for key, value in (("slots_per_entity", slots_per_item),
                                          ("slots_interchangeable", slots_interchangeable)) if value is not None
        })
        candidate = Problem(**{**problem.__dict__, "slots": list(slots), "settings": Settings.model_validate(
            settings.model_dump()), "vocabulary": Vocabulary.model_validate(vocabulary or problem.vocabulary)})
        self._check(candidate)
        problem.slots, problem.settings, problem.vocabulary = candidate.slots, candidate.settings, candidate.vocabulary
        self._save(problem)
        return {"slots": len(problem.slots), "first_slots": [s.model_dump() for s in problem.slots[:10]],
                "read_back": describe_settings(problem.spec())}

    # ---- rules ----

    def _check(self, problem: Problem, rules: Optional[list] = None) -> None:
        problems = check_spec(problem.spec(rules), problem.items())
        if problems:
            raise WorkspaceError("\n".join(problems))

    def add_rule(self, problem_id: str, rule: Rule) -> dict:
        problem = self.problem(problem_id)
        if any(r.id == rule.id for r in problem.rules):
            raise WorkspaceError(text.WS_DUPLICATE_RULE.format(rule=rule.id))
        self._check(problem, problem.rules + [rule])
        problem.rules.append(rule)
        self._save(problem)
        return {"rule_id": rule.id, "read_back": describe_rule(rule, problem.spec())}

    def remove_rule(self, problem_id: str, rule_id: str) -> dict:
        problem = self.problem(problem_id)
        rule = self._rule(problem, rule_id)
        problem.rules.remove(rule)
        self._save(problem)
        return {"removed": rule_id, "read_back": describe_rule(rule, problem.spec())}

    def set_rule_active(self, problem_id: str, rule_id: str, active: bool) -> dict:
        problem = self.problem(problem_id)
        rule = self._rule(problem, rule_id)
        updated = rule.model_copy(update={"active": active})
        problem.rules[problem.rules.index(rule)] = updated
        self._save(problem)
        return {"rule_id": rule_id, "read_back": describe_rule(updated, problem.spec())}

    def list_rules(self, problem_id: str) -> dict:
        problem = self.problem(problem_id)
        spec = problem.spec()
        return {
            "settings": describe_settings(spec),
            "rules": [{"rule_id": r.id, "read_back": describe_rule(r, spec)} for r in problem.rules],
        }

    @staticmethod
    def _rule(problem: Problem, rule_id: str):
        for rule in problem.rules:
            if rule.id == rule_id:
                return rule
        raise WorkspaceError(text.WS_UNKNOWN_RULE.format(rule=rule_id, known=", ".join(r.id for r in problem.rules) or "-"))

    # ---- spec ----

    def get_spec(self, problem_id: str) -> str:
        return dump_spec(self.problem(problem_id).spec())

    def set_spec(self, problem_id: str, spec_json: str) -> dict:
        """Replace slots, settings and rules with a saved spec, checked
        against this problem's data."""
        problem = self.problem(problem_id)
        try:
            spec = load_spec(spec_json)
        except ValueError as error:
            raise WorkspaceError(str(error)) from error
        candidate = Problem(**{**problem.__dict__, "name": spec.name, "vocabulary": spec.vocabulary,
                               "slots": list(spec.slots), "settings": spec.settings, "rules": list(spec.rules),
                               "id_column": spec.entities.id_column or problem.id_column, "rounds": []})
        self._check(candidate)
        self.problems[problem_id] = candidate
        self._save(candidate)
        return self.list_rules(problem_id)

    # ---- solving ----

    def solve(self, problem_id: str, time_budget_seconds: Optional[float] = None,
              refine_option: Optional[str] = None, emphasis: str = "balanced") -> dict:
        problem = self.problem(problem_id)
        spec, df = problem.spec(), problem.items()
        anchor = None
        if refine_option:
            # Stored results key items by text; map back to the real ids.
            stored = self._option(problem, refine_option)["assignment"]
            anchor = {e: stored[str(e)] for e in df.index if str(e) in stored}
        try:
            result = solve_spec(spec, df, time_budget_seconds=time_budget_seconds, anchor=anchor, emphasis=emphasis)
        except SpecError as error:
            raise WorkspaceError("\n".join(error.problems)) from error
        round_id = f"round-{len(problem.rounds) + 1}"
        result = _jsonable({**result, "round_id": round_id})
        for option in result["options"]:
            option["option_id"] = f"{round_id}/{option['id']}"
        problem.rounds.append(result)
        self._save(problem)
        return self._round_summary(problem, spec, result)

    @staticmethod
    def _round_summary(problem: Problem, spec: ProblemSpec, result: dict) -> dict:
        rules = {r.id: describe_rule(r, spec) for r in spec.rules}
        options = []
        for option in result["options"]:
            sizes = dict(zip([s.id for s in spec.slots], option["metrics"]["slot_sizes"]))
            options.append({
                "option_id": option["option_id"], "title": option["title"],
                "meets_every_mandatory_rule": option["verification"]["is_valid"],
                "mandatory_rules_broken": option["verification"]["hard_rules_violated"],
                "preferences_unmet": option["verification"]["soft_rules_violated"],
                "exceptions": [item["text"] for item in option["exceptions"]],
                "better_than_the_others": option["gains"], "worse_than_the_others": option["losses"],
                "items_per_slot": sizes,
                "items_moved_from_base": option["moved_from_reference"],
            })
        return {
            "round_id": result["round_id"], "mode": result["mode"],
            "conflicting_rules": [{"rule_id": rid, "read_back": rules.get(rid, rid)} for rid in result["conflicting_rule_ids"]],
            "question": result["question"], "options": options,
            "record": {key: result[key] for key in ("spec_hash", "data_hash", "engine_version", "seed", "created_at")},
        }

    @staticmethod
    def _option(problem: Problem, option_id: str) -> dict:
        for round_ in problem.rounds:
            for option in round_["options"]:
                if option["option_id"] == option_id:
                    return option
        known = [o["option_id"] for r in problem.rounds for o in r["options"]]
        raise WorkspaceError(text.WS_UNKNOWN_OPTION.format(option=option_id, known=", ".join(known) or "-"))

    def get_option(self, problem_id: str, option_id: str, item: Optional[str] = None,
                   slot: Optional[str] = None) -> dict:
        """The whole assignment, or one item's slots and the rules that
        involve it, or who is in one slot."""
        problem = self.problem(problem_id)
        option = self._option(problem, option_id)
        assignment = option["assignment"]
        if item is not None:
            key = next((k for k in assignment if str(k) == str(item)), None)
            if key is None:
                raise WorkspaceError(text.SPEC_UNKNOWN_ENTITY.format(entity=item))
            involved = [
                {"rule_id": check["constraint_id"], "rule": check["label"], "status": check["status"],
                 "summary": check["summary"]}
                for check in option["verification"]["checks"]
                if any(str(e) == str(item) for e in check["affected_entities"])
            ]
            return {"item": key, "slots": assignment[key], "rules_involving_it": involved}
        if slot is not None:
            if slot not in {s.id for s in problem.slots}:
                raise WorkspaceError(text.SPEC_UNKNOWN_SLOT.format(slot=slot))
            return {"slot": slot, "items": [e for e, slots in assignment.items() if slot in slots]}
        return {"option_id": option_id, "assignment": assignment, **_tables(problem, assignment)}

    def export_option(self, problem_id: str, option_id: str, path: str) -> dict:
        """Write an option next to the original data: .xlsx (one sheet by
        item, one by slot) or .csv (by item)."""
        problem = self.problem(problem_id)
        option = self._option(problem, option_id)
        items = problem.items()
        assignment = option["assignment"]
        by_item = problem.raw.copy()
        by_item[text.EXPORT_ASSIGNED] = [", ".join(assignment.get(str(e), assignment.get(e, []))) for e in items.index]
        rows = []
        for slot in problem.slots:
            members = [e for e, slots in assignment.items() if slot.id in slots]
            rows.append({text.EXPORT_SLOT: slot.id, **slot.attributes, text.EXPORT_COUNT: len(members),
                         text.EXPORT_ITEMS: ", ".join(map(str, members))})
        by_slot = pd.DataFrame(rows)
        extension = os.path.splitext(path)[1].lower()
        if extension == ".csv":
            by_item.to_csv(path, index=False)
        elif extension == ".xlsx":
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                by_item.to_excel(writer, sheet_name=text.EXPORT_SHEET_ITEMS, index=False)
                by_slot.to_excel(writer, sheet_name=text.EXPORT_SHEET_SLOTS, index=False)
        else:
            raise WorkspaceError(text.WS_UNSUPPORTED_FILE.format(extension=extension or "(none)"))
        return {"written": os.path.abspath(path), "option_id": option_id}
