"""Prism of distinctions: bounded local models, rules, snapshots and history."""
from __future__ import annotations

import hashlib
import copy
import json
import os
import tempfile
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from obsidian_core import VERSION, VaultConflict, VaultError, safe_path

SCHEMA = "c-obsidian.prism/v1"
ENGINE = "c-obsidian.prism-rules/v1"
KINDS = {
    "subject", "question", "condition", "observation", "evidence", "feature",
    "criterion", "rule", "test", "judgment", "unknown", "alternative",
}
KNOWLEDGE = {"unknown", "asserted", "established", "disputed", "refuted", "not_applicable"}
ORIGINS = {"observation", "statement", "assumption", "derived"}
PROVENANCE = {"observation", "assertion", "assumption", "computed"}  # legacy alias retained for v1 clients
APPLICABILITY = {"applicable", "not_applicable", "unknown"}
PERSPECTIVES = {"PROCESS", "USER", "ARCH", "AI"}
EDGE_KINDS = {
    "supports", "contradicts", "depends_on", "tests", "defines",
    "derived_from", "applies_when", "alternative_to", "scopes",
}
CASE_ID = re.compile(r"^prm-[a-z0-9][a-z0-9-]{2,63}$")
NODE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$")
MAX_MODEL = 2 * 1024 * 1024


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def text(value, name, limit=4000, required=False) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()) or len(value) > limit:
        raise VaultError("invalid_" + name)
    return value.strip()


def string_list(value, allowed=None, limit=20):
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > limit or any(not isinstance(item, str) for item in value):
        raise VaultError("invalid_list")
    result = []
    for item in value:
        item = item.strip()
        if not item or (allowed is not None and item not in allowed):
            raise VaultError("invalid_list")
        if item not in result:
            result.append(item)
    return result


def validate_expr(expr, depth=0):
    if depth > 16 or not isinstance(expr, dict):
        raise VaultError("invalid_rule")
    op = expr.get("op")
    if op in {"and", "or"}:
        args = expr.get("args")
        if not isinstance(args, list) or not 1 <= len(args) <= 64:
            raise VaultError("invalid_rule")
        for arg in args:
            validate_expr(arg, depth + 1)
        return
    if op == "not":
        validate_expr(expr.get("arg"), depth + 1)
        return
    if op is not None:
        raise VaultError("invalid_rule")
    fact = expr.get("fact")
    if not isinstance(fact, str) or not NODE_ID.fullmatch(fact):
        raise VaultError("invalid_rule")
    choices = [key for key in ("equals", "in", "exists") if key in expr]
    if len(choices) != 1:
        raise VaultError("invalid_rule")
    if "in" in expr and (not isinstance(expr["in"], list) or len(expr["in"]) > 100):
        raise VaultError("invalid_rule")
    if "exists" in expr and expr["exists"] is not True:
        raise VaultError("invalid_rule")


def expression_facts(expr):
    if expr.get("op") in {"and", "or"}:
        return {fact for arg in expr["args"] for fact in expression_facts(arg)}
    if expr.get("op") == "not":
        return expression_facts(expr["arg"])
    return {expr["fact"]}


def validate_scope(scope):
    if not isinstance(scope, dict):
        raise VaultError("fact_scope_required")
    canonical_keys = ("configuration_ref", "criterion_ref", "temporal_context")
    legacy_keys = ("subject", "feature_definition", "state_period", "criterion_version")
    if any(key in scope for key in canonical_keys):
        for key in canonical_keys:
            text(scope.get(key), "fact_scope", 1000, True)
        conditions = scope.get("condition_refs")
    else:
        for key in legacy_keys:
            text(scope.get(key), "fact_scope", 1000, True)
        conditions = scope.get("essential_conditions")
    if not isinstance(conditions, list) or len(conditions) > 50 or any(not isinstance(item, str) or not item.strip() for item in conditions):
        raise VaultError("invalid_fact_scope")


def validate_provenance(node):
    origin = node.get("origin")
    if origin is not None and origin not in ORIGINS:
        raise VaultError("invalid_origin")
    legacy = node.get("provenance_mode")
    if legacy is not None and legacy not in PROVENANCE:
        raise VaultError("invalid_provenance_mode")
    if origin is None and legacy is None:
        raise VaultError("invalid_origin")
    provenance = node.get("provenance", {})
    if not isinstance(provenance, dict):
        raise VaultError("invalid_provenance")
    if "actor" in provenance:
        text(provenance.get("actor"), "provenance_actor", 120, True)
    if "recorded_at" in provenance:
        text(provenance.get("recorded_at"), "provenance_recorded_at", 80, True)


def validate_refs(node):
    for key in ("basis_refs", "test_refs", "objection_refs"):
        value = node.get(key, [])
        if not isinstance(value, list) or len(value) > 100 or any(not isinstance(item, str) or not NODE_ID.fullmatch(item) for item in value):
            raise VaultError("invalid_refs")


def validate_sources(sources):
    if not isinstance(sources, list) or len(sources) > 1000:
        raise VaultError("invalid_source_refs")
    for source in sources:
        if not isinstance(source, dict):
            raise VaultError("invalid_source_ref")
        text(source.get("id"), "source_id", 200, True)
        text(source.get("path"), "source_path", 1000, True)
        if not isinstance(source.get("sha256"), str) or not re.fullmatch(r"[0-9a-fA-F]{64}", source["sha256"]):
            raise VaultError("invalid_source_hash")
        if "excerpt" in source:
            text(source.get("excerpt"), "source_excerpt", 12000)
        if "scope" in source:
            text(source.get("scope"), "source_scope", 2000)


def validate_objections(objections):
    if objections is None:
        return
    if not isinstance(objections, list) or len(objections) > 100:
        raise VaultError("invalid_objections")
    seen = set()
    for objection in objections:
        if not isinstance(objection, dict) or not isinstance(objection.get("id"), str) or not NODE_ID.fullmatch(objection["id"]) or objection["id"] in seen:
            raise VaultError("invalid_objection")
        seen.add(objection["id"])
        text(objection.get("text"), "objection", 4000, True)
        if objection.get("target") not in {"statement", "basis", "test", "edge"} or objection.get("status", "open") not in {"open", "resolved", "rejected"}:
            raise VaultError("invalid_objection")


def validate_model(model, expected_id=None):
    if not isinstance(model, dict) or model.get("schema") != SCHEMA:
        raise VaultError("invalid_prism_schema")
    case_id = model.get("id")
    if not isinstance(case_id, str) or not CASE_ID.fullmatch(case_id) or (expected_id and case_id != expected_id):
        raise VaultError("invalid_prism_id")
    text(model.get("title"), "title", 240, True)
    text(model.get("question"), "question", 2000, True)
    text(model.get("domain", ""), "domain", 240)
    text(model.get("context", ""), "context", 8000)
    revision = model.get("revision")
    if type(revision) is not int or revision < 1:
        raise VaultError("invalid_revision")
    string_list(model.get("perspectives", []), PERSPECTIVES, 4)
    nodes = model.get("nodes", [])
    edges = model.get("edges", [])
    rules = model.get("rules", [])
    if not isinstance(nodes, list) or len(nodes) > 1000 or not isinstance(edges, list) or len(edges) > 2000 or not isinstance(rules, list) or len(rules) > 500:
        raise VaultError("prism_limit")
    assertions = model.get("assertions", [])
    if not isinstance(assertions, list) or len(assertions) > 2000:
        raise VaultError("invalid_assertions")
    ids = set()
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("id"), str) or not NODE_ID.fullmatch(node["id"]) or node["id"] in ids:
            raise VaultError("invalid_node")
        ids.add(node["id"])
        if node.get("kind") not in KINDS:
            raise VaultError("invalid_node_kind")
        text(node.get("title"), "node_title", 500, True)
        text(node.get("description", ""), "node_description", 8000)
        text(node.get("basis", ""), "basis", 8000)
        knowledge = node.get("knowledge_status", "unknown")
        if knowledge not in KNOWLEDGE:
            raise VaultError("invalid_knowledge_status")
        if knowledge == "unknown" and "value" in node:
            raise VaultError("unknown_value_must_be_absent")
        validate_provenance(node)
        validate_refs(node)
        applicability = node.get("applicability", "applicable")
        if applicability not in APPLICABILITY:
            raise VaultError("invalid_applicability")
        validate_objections(node.get("objections", []))
        string_list(node.get("perspectives", []), PERSPECTIVES, 4)
    for assertion in assertions:
        if not isinstance(assertion, dict) or not isinstance(assertion.get("id"), str) or not NODE_ID.fullmatch(assertion["id"]):
            raise VaultError("invalid_assertion")
        for key in ("subject_id", "feature_id"):
            if assertion.get(key) not in ids:
                raise VaultError("invalid_assertion_ref")
        if assertion.get("origin") not in ORIGINS or assertion.get("knowledge_status") not in {"unknown", "asserted", "established", "refuted"} or assertion.get("applicability", "unknown") not in APPLICABILITY:
            raise VaultError("invalid_assertion")
        if assertion.get("knowledge_status") == "unknown" and "value" in assertion:
            raise VaultError("unknown_value_must_be_absent")
        validate_refs(assertion)
    for edge in edges:
        if not isinstance(edge, dict) or edge.get("type") not in EDGE_KINDS or edge.get("source") not in ids or edge.get("target") not in ids:
            raise VaultError("invalid_edge")
        if edge.get("status", "established") not in {"hypothesis", "established", "disputed", "refuted"}:
            raise VaultError("invalid_edge")
        if edge.get("status", "established") != "hypothesis" and not text(edge.get("basis", ""), "edge_basis", 4000):
            raise VaultError("edge_basis_required")
    rule_ids = set()
    referenced_facts = set()
    for rule in rules:
        if not isinstance(rule, dict) or not isinstance(rule.get("id"), str) or not NODE_ID.fullmatch(rule["id"]) or rule["id"] in rule_ids:
            raise VaultError("invalid_rule")
        rule_ids.add(rule["id"])
        text(rule.get("scope"), "rule_scope", 1000, True)
        validate_expr(rule.get("when"))
        referenced_facts.update(expression_facts(rule["when"]))
        then = rule.get("then")
        if not isinstance(then, dict) or then.get("judgment") not in ids:
            raise VaultError("invalid_rule")
    for node in nodes:
        if node["id"] in referenced_facts:
            validate_scope(node.get("scope"))
    if not referenced_facts.issubset(ids):
        raise VaultError("invalid_rule_fact")
    policy = model.get("status_policy")
    if not isinstance(policy, dict) or policy.get("statement_objection") not in {"conflicted", "report_only"} or any(policy.get(key) != "report_only" for key in ("basis_objection", "test_objection", "edge_objection")):
        raise VaultError("invalid_status_policy")
    for scenario in model.get("scenarios", []):
        validate_scenario(scenario, ids)
    for key in ("scenarios", "models", "results", "source_refs"):
        if not isinstance(model.get(key, []), list):
            raise VaultError("invalid_" + key)
    validate_sources(model.get("source_refs", []))
    if len(canonical(model)) > MAX_MODEL:
        raise VaultError("prism_model_too_large")
    return model


def validate_scenario(scenario, node_ids):
    if not isinstance(scenario, dict) or not isinstance(scenario.get("id"), str) or not NODE_ID.fullmatch(scenario["id"]):
        raise VaultError("invalid_scenario")
    text(scenario.get("title"), "scenario_title", 240, True)
    if not isinstance(scenario.get("base_revision"), int) or scenario["base_revision"] < 1:
        raise VaultError("invalid_scenario")
    overrides = scenario.get("overrides")
    if not isinstance(overrides, list) or len(overrides) > 500:
        raise VaultError("invalid_scenario")
    seen = set()
    for override in overrides:
        if not isinstance(override, dict) or override.get("node_id") not in node_ids or override["node_id"] in seen:
            raise VaultError("invalid_scenario_override")
        seen.add(override["node_id"])
        if (override.get("origin") or override.get("provenance_mode")) not in {"assumption"}:
            raise VaultError("invalid_scenario_override")
        if override.get("knowledge_status") not in KNOWLEDGE:
            raise VaultError("invalid_scenario_override")
        if override["knowledge_status"] == "unknown" and "value" in override:
            raise VaultError("unknown_value_must_be_absent")


def evaluate_expr(expr, facts, policy):
    op = expr.get("op")
    if op in {"and", "or"}:
        children = [evaluate_expr(arg, facts, policy) for arg in expr["args"]]
        statuses = [child["status"] for child in children]
        if op == "and":
            status = "not_satisfied" if "not_satisfied" in statuses else "conflicted" if "conflicted" in statuses else "unknown" if "unknown" in statuses else "not_applicable" if "not_applicable" in statuses else "satisfied"
        else:
            status = "satisfied" if "satisfied" in statuses else "conflicted" if "conflicted" in statuses else "unknown" if "unknown" in statuses else "not_applicable" if statuses and all(s == "not_applicable" for s in statuses) else "not_satisfied"
        return {"op": op, "status": status, "children": children}
    if op == "not":
        child = evaluate_expr(expr["arg"], facts, policy)
        status = {"satisfied": "not_satisfied", "not_satisfied": "satisfied", "conflicted": "not_satisfied"}.get(child["status"], child["status"])
        return {"op": "not", "status": status, "children": [child]}
    node = facts.get(expr["fact"])
    if node is None:
        return {"fact": expr["fact"], "status": "unknown", "reason": "fact_missing"}
    applicability = node.get("applicability", "applicable")
    if applicability == "not_applicable":
        return {"fact": expr["fact"], "status": "not_applicable", "applicability": applicability}
    if applicability == "unknown":
        return {"fact": expr["fact"], "status": "unknown", "applicability": applicability, "reason": "applicability_unknown"}
    knowledge = node.get("knowledge_status", "unknown")
    if knowledge == "not_applicable":
        return {"fact": expr["fact"], "status": "not_applicable", "knowledge_status": knowledge}
    statement_objections = [item for item in node.get("objections", []) if item.get("target") == "statement" and item.get("status", "open") == "open"]
    if knowledge in {"disputed", "refuted"} or (statement_objections and policy["statement_objection"] == "conflicted"):
        return {"fact": expr["fact"], "status": "conflicted", "knowledge_status": knowledge, "objections": statement_objections}
    if knowledge != "established":
        return {"fact": expr["fact"], "status": "unknown", "knowledge_status": knowledge}
    value = node.get("value")
    if "equals" in expr:
        ok = value == expr["equals"]
    elif "in" in expr:
        ok = value in expr["in"]
    else:
        ok = value is not None
    return {"fact": expr["fact"], "status": "satisfied" if ok else "not_satisfied", "value": value, "basis": node.get("basis", ""), "scope": node.get("scope"), "origin": node.get("origin") or {"observation": "observation", "assertion": "statement", "assumption": "assumption", "computed": "derived"}.get(node.get("provenance_mode")), "objections": node.get("objections", [])}


def evaluate_model(model, scenario=None):
    validate_model(model, model.get("id"))
    facts = {node["id"]: json.loads(json.dumps(node)) for node in model["nodes"]}
    assumptions = []
    if scenario is not None:
        validate_scenario(scenario, set(facts))
        for override in scenario["overrides"]:
            node = facts[override["node_id"]]
            node.pop("value", None)
            if "value" in override:
                node["value"] = override["value"]
            node["knowledge_status"] = override["knowledge_status"]
            node["provenance_mode"] = "assumption"
            node["origin"] = "assumption"
            assumptions.append(override["node_id"])
    results = []
    used_facts = set()
    for rule in model["rules"]:
        explanation = evaluate_expr(rule["when"], facts, model["status_policy"])
        judgment = facts[rule["then"]["judgment"]]
        if judgment.get("applicability", "applicable") == "not_applicable":
            judgment_status = "not_applicable"
        elif explanation["status"] == "conflicted":
            judgment_status = "conflicted"
        elif explanation["status"] == "satisfied":
            judgment_status = "follows_under_assumptions" if assumptions else ("established_in_scope" if judgment.get("knowledge_status") == "established" else "not_established")
        elif explanation["status"] == "not_satisfied":
            judgment_status = "not_established"
        else:
            judgment_status = explanation["status"]
        used = expression_facts(rule["when"])
        used_facts.update(used)
        results.append({
            "rule": rule["id"], "judgment": judgment["id"], "title": judgment["title"],
            "status": explanation["status"], "scope": rule["scope"], "explanation": explanation,
            "used_facts": sorted(used), "assumptions_used": sorted(set(assumptions) & used),
            "judgment_status": judgment_status,
        })
    return {
        "schema": "c-obsidian.prism-evaluation/v1", "engine": ENGINE, "evaluator_version": VERSION, "dsl_version": ENGINE,
        "case_id": model["id"], "revision": model["revision"],
        "snapshot_sha256": digest(model), "calculated_at": now(), "results": results,
        "scenario_id": scenario.get("id") if scenario else None, "assumptions_used": sorted(assumptions),
        "unknown": sorted(node_id for node_id, node in facts.items() if node.get("knowledge_status", "unknown") == "unknown" or node.get("applicability", "applicable") == "unknown"),
        "conflicts": sorted(node_id for node_id, node in facts.items() if node.get("knowledge_status") in {"disputed", "refuted"} or any(item.get("target") == "statement" and item.get("status", "open") == "open" for item in node.get("objections", []))),
        "unused_facts": sorted(set(facts) - used_facts),
        "used_sources": model.get("source_refs", []),
        "notice": ("Расчёт при принятых допущениях. Допущения не стали установленными фактами. " if assumptions else "Расчёт по базовым сведениям. ") + "Не является приказом или доказательством сам по себе.",
    }


class PrismStore:
    def __init__(self, vault_root):
        self.root = Path(vault_root).resolve()
        self.base = safe_path(self.root, "Prism")

    def _case_dir(self, case_id):
        if not isinstance(case_id, str) or not CASE_ID.fullmatch(case_id):
            raise VaultError("invalid_prism_id")
        return safe_path(self.root, f"Prism/Data/{case_id}")

    def _model_path(self, case_id):
        return self._case_dir(case_id) / "model.json"

    def _read_json(self, path):
        if not path.is_file() or path.is_symlink():
            raise VaultError("prism_case_not_found")
        if path.stat().st_size > MAX_MODEL:
            raise VaultError("prism_model_too_large")
        return json.loads(path.read_text(encoding="utf-8"))

    def _atomic(self, path, raw):
        if len(raw) > MAX_MODEL:
            raise VaultError("prism_model_too_large")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='wb', dir=path.parent,
                                             prefix='.prism-', delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def _snapshot(self, model):
        raw = canonical(model)
        sha = hashlib.sha256(raw).hexdigest()
        target = self._case_dir(model["id"]) / "snapshots" / f'{model["revision"]}-{sha}.json'
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with target.open("xb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            if target.read_bytes() != raw:
                raise VaultError("snapshot_conflict")
        return sha

    def _event(self, case_id, event):
        path = self._case_dir(case_id) / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = canonical(event) + b"\n"
        with path.open("ab") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())

    def _transaction_path(self, case_id):
        return self._case_dir(case_id) / "transaction.json"

    def _begin_transaction(self, case_id, operation_id, base_revision, target_revision, change_type):
        path = self._transaction_path(case_id)
        raw = canonical({"operation_id": operation_id, "case_id": case_id, "base_revision": base_revision, "target_revision": target_revision, "change_type": change_type, "stage": "prepared", "at": now()})
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open('xb') as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError as exc:
            raise VaultConflict('transaction_pending') from exc
        current_revision = self.get(case_id)['revision'] if self._model_path(case_id).exists() else 0
        if current_revision != base_revision:
            path.unlink()
            raise VaultConflict('revision_conflict')

    def _finish_transaction(self, case_id):
        try:
            self._transaction_path(case_id).unlink()
        except FileNotFoundError:
            pass

    def recovery(self):
        pending = []
        data = self.base / "Data"
        if not data.is_dir() or data.is_symlink():
            return pending
        for marker in data.glob("*/transaction.json"):
            try:
                pending.append(json.loads(marker.read_text(encoding="utf-8")))
            except (OSError, UnicodeError, json.JSONDecodeError):
                pending.append({"stage": "corrupt", "path": marker.relative_to(self.root).as_posix()})
        return pending

    def _markdown(self, model, evaluation=None):
        evaluation = evaluation or evaluate_model(model)
        by_id = {node["id"]: node for node in model["nodes"]}
        def group(kind):
            items = [node for node in model["nodes"] if node["kind"] == kind]
            return "\n".join(f'- **{node["title"]}** — {node.get("description") or node.get("basis") or "не заполнено"}' for node in items) or "- Не заполнено"
        conclusions = "\n".join(f'- **{item["title"]}**: правило `{item["rule"]}` → `{item["status"]}`, суждение: `{item.get("judgment_status", "unknown")}`' for item in evaluation["results"]) or "- Не вычислено"
        unknown = [node for node in model["nodes"] if node.get("knowledge_status", "unknown") != "established"]
        unknown_text = "\n".join(f'- {node["title"]}: `{node.get("knowledge_status", "unknown")}`' for node in unknown) or "- Нет"
        rules = "\n".join(f'- `{rule["id"]}` — область: {rule["scope"]}' for rule in model["rules"]) or "- Не заполнено"
        sha = digest(model)
        return f'''---
type: prism-case
prism_id: {model["id"]}
prism_revision: {model["revision"]}
prism_model: Prism/Data/{model["id"]}/model.json
prism_snapshot: sha256:{sha}
---

# Опыт: {model["title"]}

## Вопрос

{model["question"]}

## Предмет и условия

{group("subject")}

{group("condition")}

## Признаки и критерии

{group("feature")}

{group("criterion")}

## Наблюдения и основания

{group("observation")}

{group("evidence")}

## Утверждения

{chr(10).join(f'- `{item["id"]}`: `{item["origin"]}` / `{item["knowledge_status"]}` / `{item.get("applicability", "unknown")}`' for item in model.get("assertions", [])) or "- Не заполнено"}

## Использованные правила

{rules}

## Полученный вывод

{conclusions}

> {evaluation["notice"]}

## Неизвестное

{unknown_text}

## Что изменилось при сравнении вариантов

- Смотрите историю revision и альтернативные модели в интерфейсе «Призма».
'''

    def _write_current(self, model):
        evaluation = evaluate_model(model)
        raw = json.dumps(model, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
        self._atomic(self._model_path(model["id"]), raw)
        md = safe_path(self.root, f'Prism/Cases/{model["id"]}.md')
        self._atomic(md, self._markdown(model, evaluation).encode("utf-8"))

    def list_cases(self):
        data = self.base / "Data"
        if not data.is_dir() or data.is_symlink():
            return []
        cases = []
        for directory in sorted(data.iterdir()):
            try:
                model = validate_model(self._read_json(directory / "model.json"), directory.name)
                cases.append({"id": model["id"], "title": model["title"], "question": model["question"], "revision": model["revision"], "updated_at": model.get("updated_at", "")})
            except (VaultError, OSError, UnicodeError, json.JSONDecodeError):
                continue
        return cases

    def get(self, case_id):
        return validate_model(self._read_json(self._model_path(case_id)), case_id)

    def create(self, payload, actor="user"):
        if not isinstance(payload, dict):
            raise VaultError("invalid_body")
        case_id = payload.get("id") or "prm-" + uuid.uuid4().hex[:16]
        if self._model_path(case_id).exists():
            raise VaultConflict("prism_case_exists")
        stamp = now()
        model = {
            "schema": SCHEMA, "id": case_id, "revision": 1,
            "title": text(payload.get("title"), "title", 240, True),
            "question": text(payload.get("question"), "question", 2000, True),
            "domain": text(payload.get("domain", ""), "domain", 240),
            "context": text(payload.get("context", ""), "context", 8000),
            "perspectives": string_list(payload.get("perspectives", ["PROCESS", "USER", "ARCH", "AI"]), PERSPECTIVES, 4),
            "status_policy": payload.get("status_policy", {"statement_objection": "conflicted", "basis_objection": "report_only", "test_objection": "report_only", "edge_objection": "report_only"}),
            "nodes": payload.get("nodes", []), "edges": payload.get("edges", []), "assertions": payload.get("assertions", []), "rules": payload.get("rules", []),
            "scenarios": payload.get("scenarios", []), "models": payload.get("models", []), "results": [], "source_refs": payload.get("source_refs", []),
            "created_at": stamp, "updated_at": stamp,
        }
        validate_model(model, case_id)
        operation_id = payload.get("operation_id") or "op-" + uuid.uuid4().hex
        self._begin_transaction(case_id, operation_id, 0, 1, "create")
        committed = False
        try:
            self._write_current(model)
            sha = self._snapshot(model)
            self._event(case_id, {"event": "created", "type": "create", "operation_id": operation_id, "actor": actor, "base_revision": 0, "revision": 1, "before_sha256": None, "sha256": sha, "transaction_id": operation_id, "at": stamp})
            committed = True
        finally:
            if committed:
                self._finish_transaction(case_id)
        return model

    def update(self, case_id, payload, expected_revision, actor="user", operation_id=None):
        current = self.get(case_id)
        if type(expected_revision) is not int or expected_revision != current["revision"]:
            raise VaultConflict("revision_conflict")
        if not isinstance(payload, dict):
            raise VaultError("invalid_body")
        model = dict(payload)
        model["schema"] = SCHEMA
        model["id"] = case_id
        model["revision"] = current["revision"] + 1
        model["created_at"] = current.get("created_at", now())
        model["updated_at"] = now()
        model["results"] = []
        validate_model(model, case_id)
        operation_id = operation_id or "op-" + uuid.uuid4().hex
        existing = next((event for event in self.history(case_id) if event.get("operation_id") == operation_id), None)
        if existing:
            return self.get(case_id)
        self._begin_transaction(case_id, operation_id, current["revision"], model["revision"], "update")
        committed = False
        try:
            before = self._snapshot(current)
            self._write_current(model)
            after = self._snapshot(model)
            self._event(case_id, {"event": "updated", "type": "update", "operation_id": operation_id, "actor": actor, "base_revision": current["revision"], "revision": model["revision"], "before_sha256": before, "sha256": after, "transaction_id": operation_id, "at": model["updated_at"]})
            committed = True
        finally:
            if committed:
                self._finish_transaction(case_id)
        return model

    def history(self, case_id):
        self.get(case_id)
        path = self._case_dir(case_id) / "events.jsonl"
        if not path.exists():
            return []
        if path.stat().st_size > MAX_MODEL:
            raise VaultError("prism_history_too_large")
        result = []
        for line in path.read_text(encoding="utf-8").splitlines()[-500:]:
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError:
                result.append({"event": "corrupt", "at": ""})
        return result

    def evaluate(self, case_id, scenario=None):
        model = self.get(case_id)
        if isinstance(scenario, str):
            scenario = next((item for item in model["scenarios"] if item["id"] == scenario), None)
            if scenario is None:
                raise VaultError("scenario_not_found")
        result = evaluate_model(model, scenario)
        result["snapshot"] = {"revision": model["revision"], "sha256": digest(model)}
        return result

    def read_snapshot(self, case_id, revision=None):
        current = self.get(case_id)
        revision = current['revision'] if revision is None else revision
        if type(revision) is not int or revision < 1:
            raise VaultError('invalid_revision')
        directory = self._case_dir(case_id) / 'snapshots'
        matches = sorted(directory.glob(f'{revision}-*.json'))
        if not matches:
            raise VaultError('snapshot_not_found')
        path = matches[-1]
        if path.is_symlink() or not re.fullmatch(r'[1-9][0-9]*-[0-9a-f]{64}\.json', path.name):
            raise VaultError('snapshot_conflict')
        model = validate_model(self._read_json(path), case_id)
        fingerprint = digest(model)
        if model['revision'] != revision or path.name != f'{revision}-{fingerprint}.json':
            raise VaultError('snapshot_conflict')
        return {'case_id': case_id, 'revision': revision, 'sha256': fingerprint, 'model': model}

    def snapshot(self, case_id, revision=None, actor="user", operation_id=None):
        model = self.get(case_id)
        target_revision = model["revision"] if revision is None else revision
        if target_revision != model["revision"]:
            directory = self._case_dir(case_id) / "snapshots"
            matches = sorted(directory.glob(f"{target_revision}-*.json"))
            if not matches:
                raise VaultError("snapshot_not_found")
            raw = matches[-1].read_bytes()
            return {"case_id": case_id, "revision": target_revision, "sha256": hashlib.sha256(raw).hexdigest(), "model": json.loads(raw.decode("utf-8"))}
        operation_id = operation_id or "op-" + uuid.uuid4().hex
        if not any(event.get("operation_id") == operation_id for event in self.history(case_id)):
            self._begin_transaction(case_id, operation_id, model["revision"], model["revision"], "snapshot")
            committed = False
            try:
                sha = self._snapshot(model)
                self._event(case_id, {"event": "snapshot", "type": "snapshot", "operation_id": operation_id, "actor": actor, "base_revision": model["revision"], "revision": model["revision"], "before_sha256": sha, "sha256": sha, "transaction_id": operation_id, "at": now()})
                committed = True
            finally:
                if committed:
                    self._finish_transaction(case_id)
        else:
            sha = self._snapshot(model)
        return {"case_id": case_id, "revision": model["revision"], "sha256": sha, "model": model}

    def compare(self, case_id, payload=None):
        model = self.get(case_id)
        payload = payload or {}
        scenario_ids = payload.get("scenario_ids", [])
        if not isinstance(scenario_ids, list) or len(scenario_ids) > 10:
            raise VaultError("invalid_compare")
        scenarios = [item for item in model["scenarios"] if item["id"] in scenario_ids]
        if len(scenarios) != len(set(scenario_ids)):
            raise VaultError("scenario_not_found")
        views = payload.get("perspectives", [])
        if not isinstance(views, list):
            raise VaultError("invalid_compare")
        differences = []
        for node in model["nodes"]:
            values = {"base": node.get("value")}
            for scenario in scenarios:
                override = next((item for item in scenario["overrides"] if item["node_id"] == node["id"]), None)
                values[scenario["id"]] = override.get("value") if override and "value" in override else node.get("value")
            if len({json.dumps(value, ensure_ascii=False, sort_keys=True) for value in values.values()}) > 1:
                differences.append({"node_id": node["id"], "title": node["title"], "values": values})
        return {"case_id": case_id, "revision": model["revision"], "perspectives": views, "scenario_ids": scenario_ids, "differences": differences}

    def export_case(self, case_id):
        model = self.get(case_id)
        protocol = (safe_path(self.root, f"Prism/Cases/{case_id}.md")).read_text(encoding="utf-8")
        package = {"schema": "c-obsidian.prism-export/v1", "model": model, "model_sha256": digest(model), "protocol": protocol, "protocol_sha256": hashlib.sha256(protocol.encode("utf-8")).hexdigest(), "source_refs": model.get("source_refs", []), "self_contained": not bool(model.get("source_refs")), "external_dependencies": bool(model.get("source_refs"))}
        package["package_sha256"] = digest(package)
        return package

    def validate_import(self, package):
        if not isinstance(package, dict) or package.get("schema") != "c-obsidian.prism-export/v1":
            raise VaultError("invalid_import_package")
        model = validate_model(package.get("model"), package["model"].get("id") if isinstance(package.get("model"), dict) else None)
        if package.get("model_sha256") != digest(model):
            raise VaultError("import_hash_mismatch")
        protocol = package.get('protocol')
        if not isinstance(protocol, str) or hashlib.sha256(protocol.encode('utf-8')).hexdigest() != package.get('protocol_sha256'):
            raise VaultError('import_hash_mismatch')
        package_digest = digest({key:value for key,value in package.items() if key != 'package_sha256'})
        if package.get('package_sha256') != package_digest:
            raise VaultError('import_hash_mismatch')
        return {"valid": True, "package_sha256": digest({key: value for key, value in package.items() if key != "package_sha256"}), "case_id": model["id"], "revision": model["revision"]}

    def commit_import(self, package, expected_package_sha256, actor="user", operation_id=None):
        checked = self.validate_import(package)
        if checked["package_sha256"] != expected_package_sha256:
            raise VaultConflict("import_hash_mismatch")
        case_id = checked["case_id"]
        if self._model_path(case_id).exists():
            raise VaultConflict("prism_case_exists")
        payload = copy.deepcopy(package["model"])
        payload["operation_id"] = operation_id or "op-" + uuid.uuid4().hex
        return self.create(payload, actor)

    def challenge(self, case_id, payload, expected_revision, actor="user"):
        model = self.get(case_id)
        title = text((payload or {}).get("title"), "challenge_title", 240, True)
        change = text((payload or {}).get("change"), "challenge_change", 4000, True)
        branch = {"id": "model-" + uuid.uuid4().hex[:12], "title": title, "change": change, "base_revision": model["revision"], "created_at": now()}
        model = json.loads(json.dumps(model))
        model["models"].append(branch)
        updated = self.update(case_id, model, expected_revision, actor)
        return {"model": updated, "branch": branch}

    def create_example(self):
        case_id = "prm-reversibility"
        try:
            return self.get(case_id)
        except VaultError as exc:
            if str(exc) != "prism_case_not_found":
                raise
        fact_scope = {"configuration_ref": "vault конкретной проверки", "criterion_ref": "reversibility-v1", "condition_refs": ["одна конфигурация", "одна версия критерия"], "temporal_context": "зафиксированный запуск проверки"}
        nodes = [
            {"id": "subject_agent_links", "kind": "subject", "title": "ИИ-агент изменяет связи", "description": "Массовое изменение ссылок и содержимого Markdown-файлов.", "knowledge_status": "established", "provenance_mode": "assertion", "objections": [], "perspectives": ["PROCESS", "AI"], "basis": "Граница выбранного опыта."},
            {"id": "saved_state_exists", "kind": "condition", "title": "Сохранённое состояние существует", "description": "Есть версия файлов до операции.", "value": True, "knowledge_status": "established", "provenance_mode": "observation", "scope": fact_scope, "objections": [], "perspectives": ["PROCESS", "ARCH"], "basis": "Снимок создан до изменения."},
            {"id": "restore_method_tested", "kind": "test", "title": "Способ восстановления проверен", "description": "Выполнено пробное восстановление.", "value": True, "knowledge_status": "established", "provenance_mode": "observation", "scope": fact_scope, "objections": [], "perspectives": ["PROCESS", "ARCH"], "basis": "Результат пробного восстановления."},
            {"id": "declared_elements_restored", "kind": "observation", "title": "Оговорённые элементы восстановлены", "description": "Восстановлены текст и ссылки.", "value": True, "knowledge_status": "established", "provenance_mode": "observation", "scope": fact_scope, "objections": [], "perspectives": ["USER", "ARCH"], "basis": "Сравнение со снимком."},
            {"id": "reversibility", "kind": "feature", "title": "Обратимость", "description": "Можно ли восстановить прежнее состояние в условиях опыта.", "knowledge_status": "asserted", "provenance_mode": "assertion", "objections": [], "perspectives": ["PROCESS", "USER", "ARCH", "AI"], "basis": "Значение определяется правилом опыта."},
            {"id": "criterion_reversible", "kind": "criterion", "title": "Критерий обратимости", "description": "Состояние сохранено, метод проверен, оговорённые элементы восстановлены.", "knowledge_status": "established", "provenance_mode": "assertion", "objections": [], "perspectives": ["USER", "ARCH"], "basis": "Принято для этого опыта, не универсальное определение."},
            {"id": "judgment_reversible", "kind": "judgment", "title": "Критерий обратимости выполнен", "description": "Вывод относится только к зафиксированным условиям.", "knowledge_status": "unknown", "provenance_mode": "computed", "objections": [], "perspectives": ["PROCESS", "USER", "ARCH", "AI"], "basis": "Вычисляется из явного правила."},
        ]
        for node in nodes:
            node["origin"] = {"observation": "observation", "assertion": "statement", "assumption": "assumption", "computed": "derived"}[node["provenance_mode"]]
            node["applicability"] = "applicable"
            node["provenance"] = {"actor": "user", "recorded_at": now()}
        assertions = [{"id": "assertion_reversibility", "subject_id": "subject_agent_links", "feature_id": "reversibility", "origin": "derived", "knowledge_status": "unknown", "applicability": "applicable", "scope": fact_scope, "basis_refs": ["saved_state_exists", "restore_method_tested", "declared_elements_restored"], "test_refs": ["restore_method_tested"], "objection_refs": []}]
        edges = [
            {"source": "saved_state_exists", "target": "criterion_reversible", "type": "supports", "status": "established", "basis": "Сохранённая версия даёт исходное состояние."},
            {"source": "restore_method_tested", "target": "criterion_reversible", "type": "tests", "status": "established", "basis": "Проверка подтверждает применимость способа."},
            {"source": "declared_elements_restored", "target": "criterion_reversible", "type": "supports", "status": "established", "basis": "Сравнение охватывает оговорённый результат."},
            {"source": "criterion_reversible", "target": "judgment_reversible", "type": "defines", "status": "established", "basis": "Суждение использует критерий этого опыта."},
        ]
        rules = [{"id": "rule_reversible_v1", "scope": "Только этот опыт и указанный состав восстанавливаемого состояния.", "when": {"op": "and", "args": [{"fact": "saved_state_exists", "equals": True}, {"fact": "restore_method_tested", "equals": True}, {"fact": "declared_elements_restored", "equals": True}]}, "then": {"judgment": "judgment_reversible"}}]
        return self.create({"id": case_id, "title": "Обратимость изменения связей", "question": "Можно ли восстановить прежнее состояние связей после выполнения?", "domain": "vault-maintenance", "context": "ИИ-агент изменяет связи в хранилище заметок.", "perspectives": ["PROCESS", "USER", "ARCH", "AI"], "nodes": nodes, "edges": edges, "assertions": assertions, "rules": rules})
