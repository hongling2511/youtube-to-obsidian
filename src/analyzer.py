"""notebooklm-py 分析引擎"""

import re
from pathlib import Path

from notebooklm import NotebookLMClient

from src.extractor import extract_transcript


def _load_prompt(name: str) -> str:
    """加载 prompts/ 目录下的 prompt 文件"""
    prompt_path = Path(__file__).parent.parent / "prompts" / f"{name}.txt"
    return prompt_path.read_text(encoding="utf-8").strip()


def _is_analysis_valid(answer: str) -> bool:
    """检测分析结果是否有效（NotebookLM 有时能添加 URL 但无法读取实际内容）"""
    if not answer or len(answer) < 100:
        return False
    fail_indicators = ["缺乏", "无法为您", "没有包含实际", "无法进行", "不包含"]
    return not any(indicator in answer for indicator in fail_indicators)


def _parse_content_type(core_answer: str) -> str | None:
    """从核心分析结果中解析 content_type"""
    valid_types = {"tech_tutorial", "podcast", "knowledge", "business"}
    # 查找 ## 内容类型 后面的值
    match = re.search(r"##\s*内容类型\s*\n+\s*(\w+)", core_answer)
    if match and match.group(1) in valid_types:
        return match.group(1)
    # 兜底：在全文中搜索
    for t in valid_types:
        if t in core_answer:
            return t
    return None


async def _add_source(client, nb_id: str, url: str, metadata: dict, config: dict) -> bool:
    """添加视频源到 Notebook，路径 A 优先，失败回退路径 B

    Returns:
        True if source was added successfully.
    """
    langs = config.get("youtube", {}).get("preferred_languages", ["zh", "en"])

    # 路径 A：直接添加 YouTube URL
    try:
        await client.sources.add_url(nb_id, url)
        print("🧠 路径 A：YouTube URL 已添加")
        return True
    except Exception as e:
        print(f"⚠️ 路径 A 失败 ({e})，尝试路径 B...")

    # 路径 B：提取字幕后上传
    transcript = extract_transcript(url, langs)
    if not transcript:
        return False

    await client.sources.add_text(nb_id, transcript, title=metadata["title"])
    print(f"🧠 路径 B：字幕文本已上传（{len(transcript)} 字符）")
    return True


async def _chat_analysis(client, nb_id: str) -> str | None:
    """使用 chat 进行核心分析，检测结果有效性"""
    prompt = _load_prompt("core")
    result = await client.chat.ask(nb_id, prompt)

    if _is_analysis_valid(result.answer):
        return result.answer
    return None


async def _chat_multi_prompts(client, nb_id: str, core_answer: str, config: dict) -> dict:
    """根据核心分析结果，发送额外的 prompt 进行多维度分析

    Returns:
        dict with keys: type_specific, concepts, actions (each str or None)
    """
    nlm_config = config.get("notebooklm", {})
    results = {}

    # 按内容类型发送对应的 type prompt
    if nlm_config.get("analyze_type_specific", True):
        content_type = _parse_content_type(core_answer)
        if content_type:
            type_prompt_name = f"type_{content_type}"
            prompt_path = Path(__file__).parent.parent / "prompts" / f"{type_prompt_name}.txt"
            if prompt_path.exists():
                try:
                    prompt = _load_prompt(type_prompt_name)
                    print(f"🧠 发送类型分析 prompt: {content_type}...")
                    result = await client.chat.ask(nb_id, prompt)
                    if result.answer and len(result.answer) > 50:
                        results["type_specific"] = result.answer
                        print(f"✅ 类型分析完成: {content_type}")
                except Exception as e:
                    print(f"⚠️ 类型分析失败: {e}")

    # 概念提取
    if nlm_config.get("analyze_concepts", True):
        try:
            prompt = _load_prompt("concepts")
            print("🧠 发送概念提取 prompt...")
            result = await client.chat.ask(nb_id, prompt)
            if result.answer and len(result.answer) > 50:
                results["concepts"] = result.answer
                print("✅ 概念提取完成")
        except Exception as e:
            print(f"⚠️ 概念提取失败: {e}")

    # 行动项提取
    if nlm_config.get("analyze_actions", True):
        try:
            prompt = _load_prompt("actions")
            print("🧠 发送行动项提取 prompt...")
            result = await client.chat.ask(nb_id, prompt)
            if result.answer and len(result.answer) > 50:
                results["actions"] = result.answer
                print("✅ 行动项提取完成")
        except Exception as e:
            print(f"⚠️ 行动项提取失败: {e}")

    return results


async def _generate_artifacts(client, nb_id: str, metadata: dict, config: dict) -> dict:
    """根据配置生成 NotebookLM 原生 artifacts（mind_map, quiz, study_guide, audio）"""
    nlm_config = config.get("notebooklm", {})
    duration = metadata.get("duration", 0)
    artifacts = {}

    # Mind Map
    if nlm_config.get("generate_mind_map", False):
        try:
            print("🧠 生成思维导图...")
            result = await client.artifacts.generate_mind_map(nb_id)
            artifacts["mind_map"] = result
            print("✅ 思维导图已生成")
        except Exception as e:
            print(f"⚠️ 思维导图生成失败: {e}")

    # Quiz（仅当视频时长超过阈值）
    min_duration = nlm_config.get("quiz_min_duration", 600)
    if nlm_config.get("generate_quiz", False) and duration >= min_duration:
        try:
            print("🧠 生成测验...")
            status = await client.artifacts.generate_quiz(nb_id)
            status = await client.artifacts.wait_for_completion(nb_id, status.artifact_id)
            artifacts["quiz_id"] = status.artifact_id
            print("✅ 测验已生成")
        except Exception as e:
            print(f"⚠️ 测验生成失败: {e}")

    # Study Guide
    if nlm_config.get("generate_study_guide", False):
        try:
            print("🧠 生成学习指南...")
            status = await client.artifacts.generate_study_guide(nb_id)
            status = await client.artifacts.wait_for_completion(nb_id, status.artifact_id)
            artifacts["study_guide_id"] = status.artifact_id
            print("✅ 学习指南已生成")
        except Exception as e:
            print(f"⚠️ 学习指南生成失败: {e}")

    # Audio Overview
    if nlm_config.get("generate_audio", False):
        try:
            lang = nlm_config.get("audio_language", "en")
            print("🧠 生成音频概述...")
            status = await client.artifacts.generate_audio(nb_id, language=lang)
            status = await client.artifacts.wait_for_completion(
                nb_id, status.artifact_id, timeout=600.0
            )
            artifacts["audio_id"] = status.artifact_id
            print("✅ 音频概述已生成")
        except Exception as e:
            print(f"⚠️ 音频概述生成失败: {e}")

    return artifacts


async def _download_artifacts(client, nb_id: str, metadata: dict, config: dict, artifacts: dict):
    """下载已生成的 artifacts 到 Obsidian vault"""
    vault_path = Path(config["obsidian"]["vault_path"])
    video_id = metadata.get("video_id", "unknown")
    downloaded = {}

    # Mind Map → JSON
    if "mind_map" in artifacts:
        try:
            output = vault_path / "_附件" / "mindmaps" / f"{video_id}.json"
            output.parent.mkdir(parents=True, exist_ok=True)
            await client.artifacts.download_mind_map(nb_id, str(output))
            downloaded["mind_map"] = str(output)
            print(f"📥 思维导图已下载: {output}")
        except Exception as e:
            print(f"⚠️ 思维导图下载失败: {e}")

    # Quiz → Markdown
    if "quiz_id" in artifacts:
        try:
            output = vault_path / "_附件" / "quizzes" / f"{video_id}.md"
            output.parent.mkdir(parents=True, exist_ok=True)
            await client.artifacts.download_quiz(
                nb_id, str(output), artifact_id=artifacts["quiz_id"], output_format="markdown"
            )
            downloaded["quiz"] = str(output)
            print(f"📥 测验已下载: {output}")
        except Exception as e:
            print(f"⚠️ 测验下载失败: {e}")

    # Study Guide → Markdown
    if "study_guide_id" in artifacts:
        try:
            output = vault_path / "_附件" / f"{video_id}_study_guide.md"
            output.parent.mkdir(parents=True, exist_ok=True)
            await client.artifacts.download_report(
                nb_id, str(output), artifact_id=artifacts["study_guide_id"]
            )
            downloaded["study_guide"] = str(output)
            print(f"📥 学习指南已下载: {output}")
        except Exception as e:
            print(f"⚠️ 学习指南下载失败: {e}")

    # Audio → MP3
    if "audio_id" in artifacts:
        try:
            output = vault_path / "_附件" / f"{video_id}_audio.mp3"
            output.parent.mkdir(parents=True, exist_ok=True)
            await client.artifacts.download_audio(nb_id, str(output))
            downloaded["audio"] = str(output)
            print(f"📥 音频已下载: {output}")
        except Exception as e:
            print(f"⚠️ 音频下载失败: {e}")

    return downloaded


async def analyze_video(url: str, metadata: dict, config: dict) -> dict:
    """使用 NotebookLM 分析视频内容

    1. 添加源（路径 A/B）
    2. Chat 核心分析（无效时用路径 B 重试）
    3. 多 prompt 分析（类型专属、概念提取、行动项）
    4. 按配置生成 artifacts（mind_map, quiz, study_guide, audio）
    5. 下载 artifacts 到 Obsidian vault
    """
    print("🧠 开始 NotebookLM 分析...")

    async with await NotebookLMClient.from_storage() as client:
        # 1. 创建 Notebook + 添加源
        title = f"YT: {metadata['title'][:80]}"
        nb = await client.notebooks.create(title)
        print(f"🧠 Notebook 已创建: {title}")

        if not await _add_source(client, nb.id, url, metadata, config):
            try:
                await client.notebooks.delete(nb.id)
            except Exception:
                pass
            raise ValueError("无法获取视频内容：URL 添加失败且无可用字幕")

        # 2. Chat 核心分析
        print("🧠 正在分析...")
        core = await _chat_analysis(client, nb.id)

        # 路径 A 分析无效 → 用路径 B 重建 Notebook 重试
        if core is None:
            print("⚠️ 分析结果无效，用字幕重试...")
            langs = config.get("youtube", {}).get("preferred_languages", ["zh", "en"])
            transcript = extract_transcript(url, langs)
            if not transcript:
                try:
                    await client.notebooks.delete(nb.id)
                except Exception:
                    pass
                raise ValueError("无法获取视频内容：分析结果无效且无可用字幕")

            try:
                await client.notebooks.delete(nb.id)
            except Exception:
                pass
            nb = await client.notebooks.create(title)
            await client.sources.add_text(nb.id, transcript, title=metadata["title"])
            print(f"🧠 路径 B 重试：字幕文本已上传（{len(transcript)} 字符）")

            core = await _chat_analysis(client, nb.id)
            if core is None:
                raise ValueError("分析失败：NotebookLM 无法生成有效分析")

        print("✅ 核心分析完成")

        # 3. 多 prompt 分析
        multi = await _chat_multi_prompts(client, nb.id, core, config)

        # 4. 生成 artifacts
        artifacts = await _generate_artifacts(client, nb.id, metadata, config)

        # 5. 下载 artifacts
        downloaded = await _download_artifacts(client, nb.id, metadata, config, artifacts)

        # 6. 清理 Notebook
        if config.get("notebooklm", {}).get("cleanup_notebook", True):
            try:
                await client.notebooks.delete(nb.id)
                print("🧠 Notebook 已清理")
            except Exception:
                pass

        return {
            "core": core,
            "type_specific": multi.get("type_specific"),
            "concepts": multi.get("concepts"),
            "actions": multi.get("actions"),
            "notebook_id": nb.id,
            "artifacts": downloaded,
        }
