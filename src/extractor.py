"""yt-dlp 元数据 & 字幕提取"""

import json
import re
import subprocess
import tempfile
from pathlib import Path


def _cookies_args() -> list[str]:
    """返回 cookies 和 EJS 参数"""
    args = ["--remote-components", "ejs:github"]
    cookies_path = Path(__file__).parent.parent / "cookies.txt"
    if cookies_path.exists():
        args.extend(["--cookies", str(cookies_path)])
    return args


def get_video_metadata(url: str) -> dict:
    """调用 yt-dlp 提取视频元数据（不下载视频）"""
    print("📥 提取视频元数据...")
    try:
        result = subprocess.run(
            ["yt-dlp", "--dump-json", "--no-download", "--no-playlist", *_cookies_args(), url],
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
                    *_cookies_args(),
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


def get_playlist_metadata(url: str, last: int | None = None) -> dict:
    """调用 yt-dlp 提取播放列表元数据（不下载视频）

    Args:
        url: YouTube 播放列表 URL
        last: 只取最后 N 个视频，None 表示全部

    Returns:
        dict with keys: playlist_id, playlist_title, channel, entries
        每个 entry 包含: video_id, title, url, duration
    """
    print("📥 提取播放列表元数据...")
    try:
        result = subprocess.run(
            ["yt-dlp", "--dump-json", "--flat-playlist", *_cookies_args(), url],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(f"yt-dlp 错误: {result.stderr.strip()}")

        # yt-dlp --flat-playlist outputs one JSON object per line
        lines = [line for line in result.stdout.strip().splitlines() if line.strip()]
        if not lines:
            raise RuntimeError("播放列表为空或无法解析")

        entries = []
        playlist_id = ""
        playlist_title = ""
        channel = ""

        for line in lines:
            data = json.loads(line)
            if not playlist_id:
                playlist_id = data.get("playlist_id", "")
                playlist_title = data.get("playlist_title", "")
                channel = data.get("playlist_channel", data.get("channel", ""))

            video_id = data.get("id", "")
            video_url = data.get("url", "")
            # flat-playlist 的 url 可能是相对路径，需要补全
            if video_url and not video_url.startswith("http"):
                video_url = f"https://www.youtube.com/watch?v={video_id}"

            entries.append({
                "video_id": video_id,
                "title": data.get("title", ""),
                "url": video_url,
                "duration": data.get("duration", 0),
            })

        # --last 切片
        if last is not None and last > 0:
            entries = entries[-last:]

        print(f"✅ 播放列表: {playlist_title} ({len(entries)} 个视频)")
        return {
            "playlist_id": playlist_id,
            "playlist_title": playlist_title,
            "channel": channel,
            "entries": entries,
        }
    except subprocess.TimeoutExpired:
        raise RuntimeError("yt-dlp 超时（120秒）")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"yt-dlp 输出解析失败: {e}")
