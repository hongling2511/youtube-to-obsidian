"""流程编排 + SQLite 去重"""

import asyncio
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from notebooklm import NotebookLMClient

from src.analyzer import _load_prompt, _parse_content_type, analyze_video
from src.extractor import extract_transcript, get_playlist_metadata, get_video_metadata
from src.generator import generate_obsidian_note, generate_playlist_note


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

    async def process_playlist_individual(
        self, url: str, last: int | None, delay: int, force: bool
    ):
        """逐个处理播放列表中的视频"""
        playlist = get_playlist_metadata(url, last=last)
        entries = playlist["entries"]
        total = len(entries)

        print(f"📋 播放列表: {playlist['playlist_title']} ({total} 个视频，逐个分析模式)")

        success = 0
        skipped = 0
        failed = 0

        for i, entry in enumerate(entries, 1):
            print(f"\n[{i}/{total}] 处理中: {entry['title']}")
            try:
                await self.process(entry["url"], force=force)
                success += 1
            except Exception as e:
                print(f"❌ [{i}/{total}] 失败: {e}")
                failed += 1

            # 非最后一个视频时等待
            if i < total and delay > 0:
                await asyncio.sleep(delay)

        print(f"\n📊 播放列表处理完成: ✅ {success} 成功 / ⏭️ {skipped} 跳过 / ❌ {failed} 失败")

    async def process_playlist_combined(
        self, url: str, last: int | None, force: bool
    ):
        """合并分析播放列表：所有视频作为 source 加到一个 Notebook"""
        playlist = get_playlist_metadata(url, last=last)
        if not playlist.get("url"):
            playlist = {**playlist, "url": url}
        entries = playlist["entries"]
        playlist_id = playlist["playlist_id"]

        # 去重检查
        if not force and self.is_playlist_processed(playlist_id):
            print(f"⏭️ 播放列表已处理过: {playlist['playlist_title']}（使用 --force 强制重新处理）")
            return

        # 数量限制
        if len(entries) > 50:
            raise ValueError(
                f"播放列表包含 {len(entries)} 个视频，超过 NotebookLM 50 source 上限。"
                f"请使用 --last 50 或更小的数字限制处理数量。"
            )

        print(f"📋 播放列表: {playlist['playlist_title']} ({len(entries)} 个视频，合并分析模式)")

        async with await NotebookLMClient.from_storage() as client:
            # 1. 创建 Notebook
            nb_title = f"PL: {playlist['playlist_title'][:80]}"
            nb = await client.notebooks.create(nb_title)
            print(f"🧠 Notebook 已创建: {nb_title}")

            # 2. 逐个添加视频为 source
            added = 0
            for i, entry in enumerate(entries, 1):
                print(f"  [{i}/{len(entries)}] 添加源: {entry['title']}")
                try:
                    await client.sources.add_url(nb.id, entry["url"])
                    added += 1
                except Exception as e:
                    # 路径 B 兜底
                    print(f"  ⚠️ URL 添加失败，尝试字幕: {e}")
                    try:
                        transcript = extract_transcript(entry["url"])
                        if transcript:
                            await client.sources.add_text(nb.id, transcript, title=entry["title"])
                            added += 1
                        else:
                            print(f"  ❌ 跳过: {entry['title']}（无法获取内容）")
                    except Exception as e2:
                        print(f"  ❌ 跳过: {entry['title']}（{e2}）")

            if added == 0:
                await client.notebooks.delete(nb.id)
                raise ValueError("无法添加任何视频源到 Notebook")

            print(f"✅ 已添加 {added}/{len(entries)} 个视频源")

            # 3. 核心分析
            print("🧠 正在综合分析...")
            prompt = _load_prompt("core_playlist")
            result = await client.chat.ask(nb.id, prompt)
            core = result.answer

            analysis = {"core": core}
            analysis.update(await _chat_multi_prompts_for_playlist(client, nb.id, core, self.config))

            # 4. 清理 Notebook
            if self.config.get("notebooklm", {}).get("cleanup_notebook", True):
                try:
                    await client.notebooks.delete(nb.id)
                    print("🧠 Notebook 已清理")
                except Exception:
                    pass

        # 5. 获取每个视频的详细元数据（用于笔记中的视频列表表格）
        entries_meta = []
        for entry in entries:
            try:
                meta = get_video_metadata(entry["url"])
                entries_meta.append(meta)
            except Exception:
                entries_meta.append({
                    "video_id": entry["video_id"],
                    "title": entry["title"],
                    "duration_string": "",
                    "url": entry["url"],
                })

        # 6. 生成笔记
        filepath = generate_playlist_note(playlist, entries_meta, analysis, self.config)

        # 7. 记录成功
        self._record_playlist(playlist_id, playlist["playlist_title"], url, len(entries), "success")
        print(f"✅ 完成: {playlist['playlist_title']} → {filepath}")

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


async def _chat_multi_prompts_for_playlist(client, nb_id: str, core_answer: str, config: dict) -> dict:
    """为播放列表综合分析追加类型专项、概念和行动项分析。"""
    nlm_config = config.get("notebooklm", {})
    results = {}

    if nlm_config.get("analyze_type_specific", True):
        content_type = _parse_content_type(core_answer)
        if content_type:
            type_prompt_name = f"type_{content_type}"
            try:
                print(f"🧠 发送播放列表类型分析 prompt: {content_type}...")
                result = await client.chat.ask(nb_id, _load_prompt(type_prompt_name))
                if result.answer and len(result.answer) > 50:
                    results["type_specific"] = result.answer
                    print(f"✅ 播放列表类型分析完成: {content_type}")
            except Exception as e:
                print(f"⚠️ 播放列表类型分析失败: {e}")

    if nlm_config.get("analyze_concepts", True):
        try:
            print("🧠 发送播放列表概念提取 prompt...")
            result = await client.chat.ask(nb_id, _load_prompt("concepts"))
            if result.answer and len(result.answer) > 50:
                results["concepts"] = result.answer
                print("✅ 播放列表概念提取完成")
        except Exception as e:
            print(f"⚠️ 播放列表概念提取失败: {e}")

    if nlm_config.get("analyze_actions", True):
        try:
            print("🧠 发送播放列表行动项提取 prompt...")
            result = await client.chat.ask(nb_id, _load_prompt("actions"))
            if result.answer and len(result.answer) > 50:
                results["actions"] = result.answer
                print("✅ 播放列表行动项提取完成")
        except Exception as e:
            print(f"⚠️ 播放列表行动项提取失败: {e}")

    return results
