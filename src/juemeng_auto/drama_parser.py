from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


EPISODE_HEADING = re.compile(
    r"^[ \t]*(?:#{1,6}[ \t]+)?(?:Episode|Chapter)[ \t]+([0-9]+)"
    r"(?:[ \t]+.*|[ \t]*[:：—-].*)?$", re.IGNORECASE
)
HEADING_CANDIDATE = re.compile(r"^[ \t]*(?:#{1,6}[ \t]+)?(?:Episode|Chapter)\b", re.IGNORECASE)


class DramaParseError(RuntimeError):
    pass


def resolve_drama_path(drama: Path, project_root: Path) -> Path:
    """Resolve a CLI drama value without changing episode-loading behavior.

    DOCX imports live under ``data/dramas``.  A repository-root drama directory
    remains a supported fallback for older projects.
    """

    supplied = Path(drama)
    root = Path(project_root).resolve()
    if supplied.is_absolute():
        candidates = [supplied.resolve()]
    else:
        candidates = [
            (root / "data" / "dramas" / supplied).resolve(),
            (root / supplied).resolve(),
        ]

    checked: list[Path] = []
    existing_directories: list[Path] = []
    for candidate in candidates:
        if candidate in checked:
            continue
        checked.append(candidate)
        if (candidate / "episodes.json").is_file():
            return candidate
        if candidate.is_dir():
            existing_directories.append(candidate)

    # Preserve the old contract for callers that prepare or mock the directory
    # before the manifest exists.  The existing loader remains responsible for
    # reporting a missing episodes.json inside a real drama directory.
    if existing_directories:
        return existing_directories[0]

    locations = "、".join(str(path / "episodes.json") for path in checked)
    raise DramaParseError(f"找不到分集清单：已检查 {locations}")


@dataclass(frozen=True, slots=True)
class EpisodeEntry:
    id: int
    order: int
    source_episode: int
    file: str
    status: str = "pending"
    title: str = ""

    def as_dict(self) -> dict[str, int | str]:
        return {
            "id": self.id,
            "order": self.order,
            "source_episode": self.source_episode,
            "file": self.file,
            "status": self.status,
            "title": self.title,
        }


@dataclass(frozen=True, slots=True)
class ParseResult:
    output_dir: Path
    episodes: tuple[EpisodeEntry, ...]
    preface_file: str | None = None


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def _atomic_write_text(path: Path, content: str) -> None:
    _atomic_write_bytes(path, content.encode("utf-8"))


def parse_drama_script(script_path: Path, dramas_root: Path) -> ParseResult:
    script_path = script_path.resolve()
    if not script_path.is_file():
        raise DramaParseError(f"找不到整剧剧本：{script_path}")
    if script_path.suffix.lower() != ".md":
        raise DramaParseError("整剧剧本必须是 .md 文件")

    source = script_path.read_bytes()
    try:
        source.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DramaParseError(f"剧本不是有效的 UTF-8 文件：{script_path}") from exc

    # Scan lines for boundaries, but slice only original bytes (including CRLF/BOM).
    boundaries: list[tuple[int, int, int, str]] = []
    offset = 3 if source.startswith(b"\xef\xbb\xbf") else 0
    fence: str | None = None
    for line_number, raw_line in enumerate(source[offset:].splitlines(keepends=True), 1):
        line = raw_line.decode("utf-8").rstrip("\r\n")
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            if fence is None:
                fence = marker
            elif marker == fence:
                fence = None
        elif fence is None and HEADING_CANDIDATE.match(line):
            match = EPISODE_HEADING.fullmatch(line)
            if match is None:
                raise DramaParseError(f"第{line_number}行 Episode/Chapter 标题无法识别，请使用阿拉伯数字编号")
            title = re.sub(r"^[ \t]*#{1,6}[ \t]+", "", line).strip()
            boundaries.append((offset, offset + len(raw_line), int(match.group(1)), title))
        offset += len(raw_line)
    if not boundaries:
        raise DramaParseError("没有找到可识别的 Episode/Chapter 数字标题")

    numbers = [boundary[2] for boundary in boundaries]
    duplicates = sorted({number for number in numbers if numbers.count(number) > 1})
    if duplicates:
        values = "、".join(str(number) for number in duplicates)
        raise DramaParseError(f"Episode 编号重复：{values}")
    if any(number < 1 for number in numbers):
        raise DramaParseError("Episode 编号必须大于0")
    if any(right <= left for left, right in zip(numbers, numbers[1:])):
        raise DramaParseError("Episode 顺序异常：编号必须按原文严格递增，不会自动重排")

    chunks: list[bytes] = []
    for index, (start, body_start, episode, _) in enumerate(boundaries):
        end = boundaries[index + 1][0] if index + 1 < len(boundaries) else len(source)
        if not source[body_start:end].decode("utf-8").strip():
            raise DramaParseError(f"空 Episode/Chapter：{episode}")
        chunks.append(source[start:end])
    preface = source[:boundaries[0][0]]
    if preface + b"".join(chunks) != source:
        raise DramaParseError("拆分完整性校验失败，未写入结果")

    output_dir = (dramas_root / script_path.stem).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    entries: list[EpisodeEntry] = []
    for index, boundary in enumerate(boundaries):
        episode = numbers[index]
        file_name = f"episode_{episode:02d}.md"
        _atomic_write_bytes(output_dir / file_name, chunks[index])
        task_id = index + 1
        entries.append(
            EpisodeEntry(
                id=task_id,
                order=task_id,
                source_episode=episode,
                file=file_name,
                title=boundary[3],
            )
        )

    preface_file = "preface.md" if preface else None
    if preface_file:
        _atomic_write_bytes(output_dir / preface_file, preface)
    rebuilt = (output_dir / preface_file).read_bytes() if preface_file else b""
    rebuilt += b"".join((output_dir / entry.file).read_bytes() for entry in entries)
    if rebuilt != source:
        raise DramaParseError("拆分文件完整性校验失败：重组后与原文不一致，未更新 episodes.json")
    manifest = json.dumps(
        [entry.as_dict() for entry in entries], ensure_ascii=False, indent=2
    )
    _atomic_write_text(output_dir / "episodes.json", f"{manifest}\n")
    return ParseResult(output_dir=output_dir, episodes=tuple(entries), preface_file=preface_file)


def load_episode_entries(drama_dir: Path) -> tuple[EpisodeEntry, ...]:
    manifest_path = drama_dir.resolve() / "episodes.json"
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise DramaParseError(f"找不到分集清单：{manifest_path}") from exc
    except json.JSONDecodeError as exc:
        raise DramaParseError(
            f"episodes.json 格式错误：第{exc.lineno}行第{exc.colno}列：{exc.msg}"
        ) from exc
    if not isinstance(data, list):
        raise DramaParseError("episodes.json 顶层必须是数组")

    entries: list[EpisodeEntry] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise DramaParseError(f"episodes.json[{index}] 必须是对象")
        # Read legacy manifests without conflating their old `episode` field.
        # Newly parsed manifests always write only id/order/source_episode.
        task_id = item.get("id", index + 1)
        order = item.get("order", item.get("target_episode_index", index + 1))
        source_episode = item.get("source_episode", item.get("episode"))
        file_name = item.get("file")
        status = item.get("status")
        if isinstance(task_id, bool) or not isinstance(task_id, int):
            raise DramaParseError(f"episodes.json[{index}].id 必须是整数")
        if isinstance(order, bool) or not isinstance(order, int):
            raise DramaParseError(f"episodes.json[{index}].order 必须是整数")
        if isinstance(source_episode, bool) or not isinstance(source_episode, int):
            raise DramaParseError(f"episodes.json[{index}].source_episode 必须是整数")
        if not isinstance(file_name, str) or not file_name:
            raise DramaParseError(f"episodes.json[{index}].file 必须是非空字符串")
        if not isinstance(status, str) or not status:
            raise DramaParseError(f"episodes.json[{index}].status 必须是非空字符串")
        title = item.get("title", "")
        if not isinstance(title, str):
            raise DramaParseError(f"episodes.json[{index}].title 必须是字符串")
        entries.append(EpisodeEntry(task_id, order, source_episode, file_name, status, title))

    expected = list(range(1, len(entries) + 1))
    if [entry.id for entry in entries] != expected:
        raise DramaParseError("episodes.json.id 必须从1开始连续递增")
    if [entry.order for entry in entries] != expected:
        raise DramaParseError("episodes.json.order 必须按原剧本出现顺序从1连续递增")
    return tuple(entries)
