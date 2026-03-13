"""yt-dlp 元数据 & 字幕提取"""

import json
import re
import subprocess
import tempfile
from pathlib import Path


def get_video_metadata(url: str) -> dict:
    """调用 yt-dlp 提取视频元数据（不下载视频）"""
    print("📥 提取视频元数据...")
    try:
        result = subprocess.run(
            ["yt-dlp", "--dump-json", "--no-download", "--no-playlist", url],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"yt-dlp 错误: {result.stderr.strip()}")

        data = json.loads(result.stdout)

        return {
            "video_id": data.get("id", ""),
            "title": data.get("title", ""),
            "channel": data.get("channel", data.get("uploader", "")),
            "channel_url": data.get("channel_url", data.get("uploader_url", "")),
            "upload_date": data.get("upload_date", ""),
            "duration": data.get("duration", 0),
            "duration_string": data.get("duration_string", ""),
            "description": data.get("description", ""),
            "tags": data.get("tags", []) or [],
            "categories": data.get("categories", []) or [],
            "language": data.get("language", ""),
            "chapters": data.get("chapters", []) or [],
            "thumbnail": data.get("thumbnail", ""),
            "view_count": data.get("view_count", 0),
            "url": url,
        }
    except subprocess.TimeoutExpired:
        raise RuntimeError("yt-dlp 超时（60秒）")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"yt-dlp 输出解析失败: {e}")


def extract_transcript(url: str, langs: list[str] | None = None) -> str | None:
    """提取字幕文本（路径 B 兜底方案）

    优先人工字幕 > 自动字幕，返回纯文本或 None。
    """
    if langs is None:
        langs = ["zh", "en"]

    print("📥 提取字幕文本...")
    lang_str = ",".join(langs)

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            result = subprocess.run(
                [
                    "yt-dlp",
                    "--write-sub",
                    "--write-auto-sub",
                    "--sub-lang", lang_str,
                    "--sub-format", "vtt",
                    "--skip-download",
                    "-o", f"{tmpdir}/%(id)s.%(ext)s",
                    url,
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            print("❌ 字幕提取超时")
            return None

        if result.returncode != 0:
            print(f"❌ 字幕提取失败: {result.stderr.strip()}")
            return None

        # 查找下载的 VTT 文件，优先人工字幕
        vtt_files = list(Path(tmpdir).glob("*.vtt"))
        if not vtt_files:
            print("❌ 未找到字幕文件")
            return None

        # 排序：人工字幕（不含 auto）优先
        vtt_files.sort(key=lambda f: "auto" in f.name.lower())
        vtt_path = vtt_files[0]

        text = _parse_vtt_to_text(vtt_path.read_text(encoding="utf-8"))
        if not text.strip():
            return None

        print(f"✅ 字幕提取成功（{len(text)} 字符）")
        return text


def _parse_vtt_to_text(vtt_content: str) -> str:
    """解析 VTT 字幕为纯文本，去重复行、去 HTML 标签"""
    lines = []
    seen = set()

    for line in vtt_content.splitlines():
        # 跳过 VTT 头部、时间戳、空行
        if line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:"):
            continue
        if re.match(r"^\d{2}:\d{2}:\d{2}\.\d{3}\s*-->", line):
            continue
        if re.match(r"^\d+$", line.strip()):
            continue
        if not line.strip():
            continue

        # 去 HTML 标签
        clean = re.sub(r"<[^>]+>", "", line).strip()
        if not clean:
            continue

        # 去重复行
        if clean not in seen:
            seen.add(clean)
            lines.append(clean)

    return "\n".join(lines)
