"""流程编排 + SQLite 去重"""

import re
import sqlite3
from datetime import datetime
from pathlib import Path

from src.analyzer import analyze_video
from src.extractor import get_video_metadata
from src.generator import generate_obsidian_note


class Pipeline:
    """YouTube → NotebookLM → Obsidian 处理管道"""

    def __init__(self, config: dict):
        self.config = config
        db_path = Path(config.get("db_path", "./processed.db"))
        self.db = sqlite3.connect(str(db_path))
        self._init_db()

    def _init_db(self):
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS processed (
                video_id TEXT PRIMARY KEY,
                title TEXT,
                url TEXT,
                processed_at TEXT,
                status TEXT
            )
        """)
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS playlists (
                playlist_id TEXT PRIMARY KEY,
                title TEXT,
                url TEXT,
                video_count INTEGER,
                processed_at TEXT,
                status TEXT
            )
        """)
        self.db.commit()

    def is_processed(self, video_id: str) -> bool:
        """检查视频是否已处理"""
        row = self.db.execute(
            "SELECT 1 FROM processed WHERE video_id = ? AND status = 'success'", (video_id,)
        ).fetchone()
        return row is not None

    def _record(self, video_id: str, title: str, url: str, status: str):
        """记录处理结果"""
        self.db.execute(
            "INSERT OR REPLACE INTO processed (video_id, title, url, processed_at, status) VALUES (?, ?, ?, ?, ?)",
            (video_id, title, url, datetime.now().isoformat(), status),
        )
        self.db.commit()

    def is_playlist_processed(self, playlist_id: str) -> bool:
        """检查播放列表是否已处理"""
        row = self.db.execute(
            "SELECT 1 FROM playlists WHERE playlist_id = ? AND status = 'success'",
            (playlist_id,),
        ).fetchone()
        return row is not None

    def _record_playlist(self, playlist_id: str, title: str, url: str, video_count: int, status: str):
        """记录播放列表处理结果"""
        self.db.execute(
            "INSERT OR REPLACE INTO playlists (playlist_id, title, url, video_count, processed_at, status) VALUES (?, ?, ?, ?, ?, ?)",
            (playlist_id, title, url, video_count, datetime.now().isoformat(), status),
        )
        self.db.commit()

    async def process(self, url: str, force: bool = False):
        """处理单个 YouTube 视频的完整流程"""
        # 1. 提取元数据
        try:
            metadata = get_video_metadata(url)
        except Exception as e:
            print(f"❌ 元数据提取失败: {e}")
            raise

        video_id = metadata["video_id"]
        title = metadata["title"]

        # 2. 去重检查
        if not force and self.is_processed(video_id):
            print(f"⏭️ 视频已处理过: {title}（使用 --force 强制重新处理）")
            return

        print(f"📥 开始处理: {title}")

        # 3. NotebookLM 分析
        try:
            analysis = await analyze_video(url, metadata, self.config)
        except Exception as e:
            self._record(video_id, title, url, "failed")
            print(f"❌ 分析失败: {e}")
            raise

        # 4. 生成 Obsidian 笔记
        try:
            filepath = generate_obsidian_note(metadata, analysis, self.config)
        except Exception as e:
            self._record(video_id, title, url, "failed")
            print(f"❌ 笔记生成失败: {e}")
            raise

        # 5. 记录成功
        self._record(video_id, title, url, "success")
        print(f"✅ 完成: {title} → {filepath}")


def extract_video_id(url: str) -> str | None:
    """从 YouTube URL 中提取 video_id"""
    patterns = [
        r'(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'(?:embed/)([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None
