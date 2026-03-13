"""Markdown 生成 + Obsidian 写入"""

import re
from datetime import datetime
from pathlib import Path


def escape_yaml(value: str) -> str:
    """转义 YAML 字符串中的特殊字符"""
    if any(c in value for c in ':{}[]&*?|>!%@`#,'):
        return f'"{value.replace(chr(34), chr(92) + chr(34))}"'
    if value.startswith(("'", '"')) or value.strip() != value:
        return f'"{value.replace(chr(34), chr(92) + chr(34))}"'
    return f'"{value}"'


def sanitize_filename(title: str) -> str:
    """清理文件名，移除不安全字符"""
    # 移除或替换文件系统不允许的字符
    sanitized = re.sub(r'[<>:"/\\|?*]', '', title)
    # 替换连续空白为单个空格
    sanitized = re.sub(r'\s+', ' ', sanitized).strip()
    # 限制长度
    if len(sanitized) > 100:
        sanitized = sanitized[:100].strip()
    return sanitized or "untitled"


def format_yaml_tags(tags: list[str]) -> str:
    """格式化标签列表为 YAML 数组"""
    if not tags:
        return "[]"
    lines = []
    for tag in tags:
        # 标签清理：移除特殊字符，转小写
        clean = re.sub(r'[^\w\u4e00-\u9fff\-]', '', tag).strip()
        if clean:
            lines.append(f"  - {clean}")
    return "\n" + "\n".join(lines) if lines else "[]"


def _format_date(date_str: str) -> str:
    """将 yt-dlp 的日期格式 (YYYYMMDD) 转换为 YYYY-MM-DD"""
    if len(date_str) == 8 and date_str.isdigit():
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    return date_str


def _parse_content_type(core_answer: str) -> str:
    """从核心分析中解析 content_type"""
    valid_types = {"tech_tutorial", "podcast", "knowledge", "business"}
    match = re.search(r"##\s*内容类型\s*\n+\s*(\w+)", core_answer)
    if match and match.group(1) in valid_types:
        return match.group(1)
    for t in valid_types:
        if t in core_answer:
            return t
    return ""


def _parse_one_line_summary(core_answer: str) -> str:
    """从核心分析中解析一句话总结"""
    match = re.search(r"##\s*一句话总结\s*\n+\s*(.+)", core_answer)
    if match:
        return match.group(1).strip()
    return ""


def _parse_ratings(core_answer: str) -> dict:
    """从核心分析中解析评分"""
    ratings = {}
    for dimension in ["信息密度", "实用性", "新颖性"]:
        match = re.search(rf"{dimension}\s*[:：]\s*(\d)\s*/\s*5", core_answer)
        if match:
            ratings[dimension] = int(match.group(1))
    return ratings


def _compute_overall_rating(ratings: dict) -> int | None:
    """计算总评分（取平均值四舍五入）"""
    if not ratings:
        return None
    return round(sum(ratings.values()) / len(ratings))


def _parse_concepts(concepts_answer: str | None) -> list[str]:
    """从概念分析结果中提取 [[概念]] 列表"""
    if not concepts_answer:
        return []
    # 提取所有 [[xxx]] 中的内容，去重保序
    matches = re.findall(r'\[\[([^\]]+)\]\]', concepts_answer)
    seen = set()
    result = []
    for m in matches:
        normalized = re.sub(r"\s+", " ", m).strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _has_actions(actions_answer: str | None) -> bool:
    """检测行动项分析中是否包含 checkbox"""
    if not actions_answer:
        return False
    matches = re.findall(r"^\s*-\s\[\s\]\s*(.+)$", actions_answer, flags=re.MULTILINE)
    for item in matches:
        if item.strip() != "未明确提及":
            return True
    return False


def generate_obsidian_note(metadata: dict, analysis: dict, config: dict) -> Path:
    """生成 Obsidian Markdown 笔记并写入 Vault"""
    print("📝 生成 Obsidian 笔记...")

    now = datetime.now()
    title = metadata.get("title", "Untitled")
    vault_path = Path(config["obsidian"]["vault_path"])
    inbox = config["obsidian"].get("inbox_folder", "0-收集箱")
    output_dir = vault_path / inbox
    output_dir.mkdir(parents=True, exist_ok=True)

    core_answer = analysis.get("core", "")

    # 解析扩展 frontmatter 字段
    content_type = _parse_content_type(core_answer)
    one_line_summary = _parse_one_line_summary(core_answer)
    ratings = _parse_ratings(core_answer)
    overall_rating = _compute_overall_rating(ratings)
    concepts = _parse_concepts(analysis.get("concepts"))
    has_actions = _has_actions(analysis.get("actions"))

    # 构建 frontmatter
    tags_yaml = format_yaml_tags(metadata.get("tags", []))
    date_published = _format_date(metadata.get("upload_date", ""))

    frontmatter_lines = [
        "---",
        "type: youtube",
        f"title: {escape_yaml(title)}",
        f'channel: "[[{metadata.get("channel") or "Unknown"}]]"',
        f"url: {metadata.get('url', '')}",
        f"video_id: {metadata.get('video_id', '')}",
        f"date_watched: {now.strftime('%Y-%m-%d')}",
        f"date_published: {date_published}",
        f'duration: "{metadata.get("duration_string", "")}"',
    ]

    if content_type:
        frontmatter_lines.append(f"content_type: {content_type}")
    if one_line_summary:
        frontmatter_lines.append(f"one_line_summary: {escape_yaml(one_line_summary)}")
    if overall_rating is not None:
        frontmatter_lines.append(f"rating: {overall_rating}")
    if ratings:
        frontmatter_lines.append("rating_detail:")
        for k, v in ratings.items():
            frontmatter_lines.append(f"  {k}: {v}")
    if concepts:
        frontmatter_lines.append("related_concepts:")
        for c in concepts:
            frontmatter_lines.append(f'  - "[[{c}]]"')
    if has_actions:
        frontmatter_lines.append("has_actions: true")

    frontmatter_lines.append(f"tags:{tags_yaml}")
    frontmatter_lines.append("---")

    frontmatter = "\n".join(frontmatter_lines)

    # 构建正文
    sections = [f"# {title}", "", core_answer]

    # 类型专属分析
    type_specific = analysis.get("type_specific")
    if type_specific:
        sections.append("")
        sections.append(type_specific)

    # 概念链接
    concepts_text = analysis.get("concepts")
    if concepts_text:
        sections.append("")
        sections.append(concepts_text)

    # 行动项
    actions_text = analysis.get("actions")
    if actions_text:
        sections.append("")
        sections.append(actions_text)

    # Artifacts 链接
    artifacts = analysis.get("artifacts", {})
    if artifacts:
        links = []
        for kind, path in artifacts.items():
            rel = Path(path).relative_to(vault_path)
            label = {"mind_map": "思维导图", "quiz": "测验", "study_guide": "学习指南", "audio": "音频概述"}.get(kind, kind)
            links.append(f"- {label}：[[{rel}]]")
        if links:
            sections.append("")
            sections.append("## 附件")
            sections.append("")
            sections.append("\n".join(links))

    footer = f"*自动生成于 {now.strftime('%Y-%m-%d %H:%M')} | [原始视频]({metadata.get('url', '')})*"
    sections.append("")
    sections.append("---")
    sections.append(footer)

    content = frontmatter + "\n\n" + "\n".join(sections) + "\n"

    # 写入文件
    filename = sanitize_filename(title) + ".md"
    filepath = output_dir / filename
    filepath.write_text(content, encoding="utf-8")

    print(f"✅ 笔记已写入: {filepath}")
    return filepath


def generate_playlist_note(
    playlist_meta: dict, entries_meta: list[dict], analysis: dict, config: dict
) -> Path:
    """生成播放列表综合分析的 Obsidian 笔记并写入 Vault"""
    print("📝 生成播放列表笔记...")

    now = datetime.now()
    title = playlist_meta.get("playlist_title", "Untitled Playlist")
    vault_path = Path(config["obsidian"]["vault_path"])
    inbox = config["obsidian"].get("inbox_folder", "0-收集箱")
    output_dir = vault_path / inbox
    output_dir.mkdir(parents=True, exist_ok=True)

    # Frontmatter
    frontmatter_lines = [
        "---",
        "type: youtube-playlist",
        f"title: {escape_yaml(title)}",
        f"playlist_id: {playlist_meta.get('playlist_id', '')}",
        f'channel: "[[{playlist_meta.get("channel") or "Unknown"}]]"',
        f"url: {playlist_meta.get('url', '')}",
        f"video_count: {len(entries_meta)}",
        f"date_watched: {now.strftime('%Y-%m-%d')}",
        "tags:\n  - playlist",
        "---",
    ]
    frontmatter = "\n".join(frontmatter_lines)

    # Video table
    table_lines = [
        "## 视频列表",
        "| # | 标题 | 时长 |",
        "|---|------|------|",
    ]
    for i, entry in enumerate(entries_meta, 1):
        entry_title = entry.get("title", "Unknown")
        duration = entry.get("duration_string", "")
        table_lines.append(f"| {i} | {entry_title} | {duration} |")

    # Body
    core_answer = analysis.get("core", "")
    sections = [
        f"# {title}",
        "",
        "\n".join(table_lines),
        "",
        core_answer,
    ]

    type_specific = analysis.get("type_specific")
    if type_specific:
        sections.extend(["", type_specific])

    concepts_text = analysis.get("concepts")
    if concepts_text:
        sections.extend(["", concepts_text])

    actions_text = analysis.get("actions")
    if actions_text:
        sections.extend(["", actions_text])

    sections.extend([
        "",
        "---",
        f"*自动生成于 {now.strftime('%Y-%m-%d %H:%M')} | [原始播放列表]({playlist_meta.get('url', '')})*",
    ])

    content = frontmatter + "\n\n" + "\n".join(sections) + "\n"

    filename = sanitize_filename(title) + ".md"
    filepath = output_dir / filename
    filepath.write_text(content, encoding="utf-8")

    print(f"✅ 播放列表笔记已写入: {filepath}")
    return filepath
