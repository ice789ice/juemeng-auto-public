from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path

from .drama_parser import load_episode_entries
from .script.validator import validate_storyboard_file


BUDGET_VERSION = "0.1"
RUNTIME_PACING_METADATA_FIELDS = (
    "budget_version",
    "source_sha256",
    "source_dialogue_words",
    "source_vo_words",
    "source_spoken_words",
    "speech_seconds_at_3_0_wps",
    "speech_seconds_at_2_5_wps",
    "speech_seconds_at_2_0_wps",
)
WORD_PATTERN = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?")
HEADING_PATTERN = re.compile(r"^\s{0,3}#{1,6}\s+")
SPEAKER_PREFIX_PATTERN = re.compile(
    r"^(?P<label>[^:：\n]{1,80})[:：]\s*(?P<body>.+)$"
)
VOICE_OVER_LABEL_PATTERN = re.compile(r"(?:\bVO\b|旁白|NARRAT)", re.IGNORECASE)
EPISODE_ID_PATTERN = re.compile(r"^episode_([0-9]+)$")


class RuntimeBudgetError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SourceWordCounts:
    dialogue_words: int
    vo_words: int

    @property
    def spoken_words(self) -> int:
        return self.dialogue_words + self.vo_words


@dataclass(frozen=True, slots=True)
class RuntimeBudget:
    budget_version: str
    episode_id: str
    source_sha256: str
    source_dialogue_words: int
    source_vo_words: int
    source_spoken_words: int
    speech_seconds_at_3_0_wps: float
    speech_seconds_at_2_5_wps: float
    speech_seconds_at_2_0_wps: float
    preferred_runtime_low: float | None
    preferred_runtime_mid: float | None
    preferred_runtime_high: float | None
    preferred_runtime_status: str
    storyboard_sha256: str | None = None
    storyboard_runtime_seconds: float | None = None
    storyboard_runtime_to_2_5_reference: float | None = None

    def as_dict(self) -> dict[str, str | int | float | None]:
        return asdict(self)


def build_runtime_pacing_reference(budget: RuntimeBudget) -> str:
    """Build the optional prompt section from current-source fields only."""

    return (
        "[RUNTIME PACING REFERENCE]\n"
        f"Source spoken words: {budget.source_spoken_words}\n\n"
        "Speech pacing references:\n\n"
        f"- 3.0 words/s: {budget.speech_seconds_at_3_0_wps}s\n"
        f"- 2.5 words/s: {budget.speech_seconds_at_2_5_wps}s\n"
        f"- 2.0 words/s: {budget.speech_seconds_at_2_0_wps}s\n\n"
        "Guidance:\n\n"
        "- These values are pacing references, not hard runtime targets.\n"
        "- Source density may legitimately make one Episode longer or shorter than another.\n"
        "- Do not force the Episode toward one specific runtime.\n"
        "- Shot splitting redistributes existing narrative time; it must not automatically "
        "create new runtime.\n"
        "- When one narrative beat is divided into multiple Shots, do not give each new Shot "
        "a fresh full reaction/action/dialogue buffer.\n"
        "- Dialogue, VO, reaction and visible action may overlap naturally when the source "
        "permits it.\n"
        "- Preserve natural dialogue delivery and performance. Do not mechanically shorten "
        "Shots only to match a reference number.\n"
        "- Existing Segment <=30s contract still applies."
    )


def runtime_pacing_metadata(
    budget: RuntimeBudget | None,
) -> dict[str, bool | str | int | float]:
    """Return stable run metadata without storyboard or preferred-runtime fields."""

    if budget is None:
        return {"runtime_pacing_enabled": False}
    values = budget.as_dict()
    return {
        "runtime_pacing_enabled": True,
        **{field: values[field] for field in RUNTIME_PACING_METADATA_FIELDS},
    }


def _content_line(raw_line: str) -> str | None:
    line = raw_line.lstrip("\ufeff").strip()
    if not line or HEADING_PATTERN.match(line):
        return None
    line = line.replace("\\", "").strip()
    while line.startswith(">"):
        line = line[1:].lstrip()
    if re.match(r"^(?:[-+*]|[0-9]+[.)])\s+", line):
        line = re.sub(r"^(?:[-+*]|[0-9]+[.)])\s+", "", line, count=1)
    return line.strip()


def count_source_words(source: str) -> SourceWordCounts:
    """Count readable English words using deterministic Markdown line rules."""

    dialogue_words = 0
    vo_words = 0
    for raw_line in source.splitlines():
        line = _content_line(raw_line)
        if line is None:
            continue

        visible = line.strip("*_ ")
        speaker = SPEAKER_PREFIX_PATTERN.match(visible)
        if speaker:
            label = speaker.group("label").strip("*_ ")
            body = speaker.group("body")
            count = len(WORD_PATTERN.findall(body))
            if VOICE_OVER_LABEL_PATTERN.search(label):
                vo_words += count
            else:
                dialogue_words += count
        elif visible.startswith(('"', "“")):
            dialogue_words += len(WORD_PATTERN.findall(visible))
        else:
            vo_words += len(WORD_PATTERN.findall(visible))

    return SourceWordCounts(dialogue_words, vo_words)


def _reference_seconds(words: int, words_per_second: float) -> float:
    return round(words / words_per_second, 3)


def calculate_runtime_budget(
    episode_id: str,
    source_bytes: bytes,
    *,
    storyboard_path: Path | None = None,
) -> RuntimeBudget:
    try:
        source = source_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise RuntimeBudgetError("Episode source 不是有效的 UTF-8 文件") from exc

    counts = count_source_words(source)
    normal_reference = _reference_seconds(counts.spoken_words, 2.5)
    storyboard_hash: str | None = None
    storyboard_runtime: float | None = None
    runtime_ratio: float | None = None

    if storyboard_path is not None:
        path = storyboard_path.resolve()
        if not path.is_file():
            raise RuntimeBudgetError(f"找不到 storyboard：{path}")
        storyboard, issues = validate_storyboard_file(path)
        if issues:
            details = "; ".join(str(issue) for issue in issues)
            raise RuntimeBudgetError(f"storyboard 未通过 Validator：{details}")
        assert storyboard is not None
        storyboard_runtime = round(
            sum(shot.duration for segment in storyboard.segments for shot in segment.shots),
            3,
        )
        storyboard_hash = sha256(path.read_bytes()).hexdigest()
        if normal_reference > 0:
            runtime_ratio = round(storyboard_runtime / normal_reference, 3)

    return RuntimeBudget(
        budget_version=BUDGET_VERSION,
        episode_id=episode_id,
        source_sha256=sha256(source_bytes).hexdigest(),
        source_dialogue_words=counts.dialogue_words,
        source_vo_words=counts.vo_words,
        source_spoken_words=counts.spoken_words,
        speech_seconds_at_3_0_wps=_reference_seconds(counts.spoken_words, 3.0),
        speech_seconds_at_2_5_wps=normal_reference,
        speech_seconds_at_2_0_wps=_reference_seconds(counts.spoken_words, 2.0),
        preferred_runtime_low=None,
        preferred_runtime_mid=None,
        preferred_runtime_high=None,
        preferred_runtime_status="not_established",
        storyboard_sha256=storyboard_hash,
        storyboard_runtime_seconds=storyboard_runtime,
        storyboard_runtime_to_2_5_reference=runtime_ratio,
    )


def write_runtime_budget(
    episode_id: str,
    source_path: Path,
    output_dir: Path,
    *,
    storyboard_path: Path | None = None,
) -> Path:
    source = source_path.resolve()
    if not source.is_file():
        raise RuntimeBudgetError(f"找不到 Episode source：{source}")
    budget = calculate_runtime_budget(
        episode_id,
        source.read_bytes(),
        storyboard_path=storyboard_path,
    )
    target_dir = output_dir.resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "runtime_budget.json"
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(budget.as_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)
    return target


def write_episode_runtime_budget(
    episode_id: str,
    drama_dir: Path,
    *,
    output_dir: Path | None = None,
    storyboard_path: Path | None = None,
) -> Path:
    match = EPISODE_ID_PATTERN.fullmatch(episode_id.strip().lower())
    if match is None:
        raise RuntimeBudgetError("集名称必须使用 episode_数字 格式，例如 episode_32")
    name = episode_id.strip().lower()
    drama = drama_dir.resolve()
    episode_number = int(match.group(1))
    entry = next(
        (item for item in load_episode_entries(drama) if item.source_episode == episode_number),
        None,
    )
    if entry is None:
        raise RuntimeBudgetError(f"整剧清单中找不到 {name}")
    source_path = (drama / entry.file).resolve()
    if not source_path.is_relative_to(drama):
        raise RuntimeBudgetError("Episode 文件必须位于 drama 目录内")

    selected_storyboard = storyboard_path.resolve() if storyboard_path else None
    default_storyboard = drama / "outputs" / name / "storyboard.json"
    if selected_storyboard is None and default_storyboard.is_file():
        selected_storyboard = default_storyboard.resolve()
    selected_output = (
        output_dir.resolve()
        if output_dir is not None
        else selected_storyboard.parent
        if selected_storyboard is not None
        else (drama / "outputs" / name).resolve()
    )
    return write_runtime_budget(
        name,
        source_path,
        selected_output,
        storyboard_path=selected_storyboard,
    )
