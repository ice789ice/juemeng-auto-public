from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any

from .production_brief import ASSET_CLASSIFICATIONS, ASSET_KINDS
from .project_bible import ProjectBible


GROUP_BY_KIND = {
    "character": "characters",
    "location": "locations",
    "wardrobe": "wardrobe",
    "prop": "props",
}
CLASSIFICATION_RISK = {
    "confirmed_existing": 0,
    "possible_reuse": 1,
    "possible_new_or_changed": 2,
    "uncertain": 3,
}


def normalize_asset_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


@dataclass(frozen=True, slots=True)
class CatalogRecord:
    kind: str
    data: dict[str, Any]

    @property
    def id(self) -> str:
        return self.data["id"]


class AssetMatcher:
    """Conservative, exact-only Core Assets matching for human review hints."""

    def __init__(self, bible: ProjectBible | None) -> None:
        self.records: dict[str, CatalogRecord] = {}
        self.canonical: dict[tuple[str, str], set[str]] = {}
        self.aliases: dict[tuple[str, str], set[str]] = {}
        self.asset_names: dict[tuple[str, str], set[str]] = {}
        if bible is None:
            return
        for kind, group in GROUP_BY_KIND.items():
            for item in bible.data[group]:
                record = CatalogRecord(kind, item)
                self.records[record.id] = record
                self._add(self.canonical, kind, item["canonical_name"], record.id)
                for alias in item["aliases"]:
                    self._add(self.aliases, kind, alias, record.id)
                if item["asset_name"]:
                    self._add(self.asset_names, kind, item["asset_name"], record.id)

    @staticmethod
    def _add(
        index: dict[tuple[str, str], set[str]], kind: str, value: str, asset_id: str
    ) -> None:
        normalized = normalize_asset_text(value)
        if normalized:
            index.setdefault((kind, normalized), set()).add(asset_id)

    def _exact_candidates(self, item: dict[str, str]) -> set[str]:
        kind = item["kind"]
        candidates: set[str] = set()
        for value in (item["name"], item["canonical_name_hint"]):
            normalized = normalize_asset_text(value)
            if not normalized:
                continue
            for index in (self.canonical, self.aliases, self.asset_names):
                candidates.update(index.get((kind, normalized), set()))
        proposed = item["candidate_asset_id"].strip()
        if proposed:
            record = self.records.get(proposed)
            if record is not None and record.kind == kind:
                # A model-proposed ID is only accepted when its names also match exactly.
                record_names = [record.data["canonical_name"], *record.data["aliases"]]
                if record.data["asset_name"]:
                    record_names.append(record.data["asset_name"])
                source_names = {normalize_asset_text(item["name"]),
                                normalize_asset_text(item["canonical_name_hint"])}
                if source_names.intersection(map(normalize_asset_text, record_names)):
                    candidates.add(proposed)
        return candidates

    def match(
        self, item: dict[str, str], episode: int, script: str
    ) -> dict[str, Any]:
        if item["kind"] not in ASSET_KINDS:
            raise ValueError(f"不支持的资产类型：{item['kind']}")
        candidates = sorted(self._exact_candidates(item))
        evidence = item["evidence"].strip()
        evidence_valid = bool(evidence and evidence in script)
        change_note = item["change_note"].strip()
        human_question = item["human_question"].strip()
        proposed = item["candidate_asset_id"].strip()

        classification = "uncertain"
        matched: CatalogRecord | None = None
        reason = "信息不足，需要人工确认"
        if len(candidates) > 1:
            reason = "同一名称匹配到多个 Core Assets 候选"
        elif len(candidates) == 1:
            matched = self.records[candidates[0]]
            record = matched.data
            if proposed and proposed != matched.id:
                reason = "LLM 提出的 asset id 与确定性名称匹配结果冲突"
            elif not evidence_valid:
                reason = "资产名称可匹配，但当前 Episode 证据无法核验"
            elif human_question:
                reason = "当前 Episode 明确要求人工判断资产是否适用"
            elif change_note:
                classification = "possible_new_or_changed"
                reason = "匹配到基础资产，但 Episode 明确提示变化"
            elif record["status"] == "confirmed" and record["asset_name"].strip():
                if matched.kind == "wardrobe":
                    episodes = record.get("episodes", [])
                    if episodes and episode not in episodes:
                        classification = "possible_reuse"
                        reason = "服装资产已确认，但适用 Episode 范围不包含本集"
                    else:
                        classification = "confirmed_existing"
                        reason = "唯一精确匹配 confirmed 且存在 asset_name 的资产"
                else:
                    classification = "confirmed_existing"
                    reason = "唯一精确匹配 confirmed 且存在 asset_name 的资产"
            elif record["status"] == "suggested" or not record["asset_name"].strip():
                classification = "possible_reuse"
                reason = "存在唯一 Core Assets 候选，但尚未满足 confirmed_existing 条件"
            else:
                reason = "Core Assets 状态为 unknown"
        elif evidence_valid and not human_question:
            classification = "possible_new_or_changed"
            reason = "Episode 有明确证据，但 Core Assets 中没有精确匹配"
        elif proposed and proposed not in self.records:
            reason = "LLM 提出的 asset id 不存在"
        elif evidence_valid:
            reason = "Episode 有相关证据，但是否需要独立资产仍不确定"

        assert classification in ASSET_CLASSIFICATIONS
        canonical = (
            matched.data["canonical_name"]
            if matched is not None
            else item["canonical_name_hint"].strip() or item["name"].strip()
        )
        result = {
            "kind": item["kind"],
            "source_name": item["name"].strip(),
            "canonical_name": canonical,
            "classification": classification,
            "matched_asset_id": matched.id if matched is not None else "",
            "asset_name": matched.data["asset_name"].strip() if matched else "",
            "change_note": change_note,
            "evidence": evidence if evidence_valid else "",
            "possible_matches": candidates,
            "human_question": human_question,
            "match_reason": reason,
        }
        if item["kind"] == "wardrobe":
            result.update(
                wardrobe_key=item.get("wardrobe_key", ""),
                wardrobe_state=item.get("wardrobe_state", ""),
                suggested_asset_name=item.get("suggested_asset_name", ""),
            )
        return result

    def reconcile(
        self, requirements: list[dict[str, str]], episode: int, script: str
    ) -> list[dict[str, Any]]:
        merged: dict[tuple[str, str, str], dict[str, Any]] = {}
        for requirement in requirements:
            current = self.match(requirement, episode, script)
            identity = current["matched_asset_id"] or normalize_asset_text(
                current["canonical_name"] or current["source_name"]
            )
            key = (
                current["kind"],
                identity,
                normalize_asset_text(current["change_note"]),
            )
            if key not in merged:
                merged[key] = current
                continue
            target = merged[key]
            if CLASSIFICATION_RISK[current["classification"]] > CLASSIFICATION_RISK[
                target["classification"]
            ]:
                target["classification"] = current["classification"]
                target["match_reason"] = current["match_reason"]
            for candidate in current["possible_matches"]:
                if candidate not in target["possible_matches"]:
                    target["possible_matches"].append(candidate)
            if not target["evidence"] and current["evidence"]:
                target["evidence"] = current["evidence"]
            if not target["human_question"] and current["human_question"]:
                target["human_question"] = current["human_question"]

        results = list(merged.values())
        for index, item in enumerate(results, 1):
            item["requirement_id"] = f"EP{episode:02d}-ASSET-{index:03d}"
        return results
