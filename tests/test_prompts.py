"""Regression tests for prompt files."""

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_core_prompt_keeps_parser_required_sections():
    content = (ROOT / "prompts" / "core.txt").read_text(encoding="utf-8")

    required_sections = [
        "## 一句话总结",
        "## 内容类型",
        "## 核心观点",
        "## 详细笔记",
        "## 价值评分",
        "- 信息密度: X/5",
        "- 实用性: X/5",
        "- 新颖性: X/5",
    ]

    for section in required_sections:
        assert section in content


def test_core_prompt_instructs_model_not_to_guess():
    content = (ROOT / "prompts" / "core.txt").read_text(encoding="utf-8")

    assert "未明确提及" in content
    assert "不要猜测" in content


def test_core_playlist_prompt_targets_aggregate_analysis():
    content = (ROOT / "prompts" / "core_playlist.txt").read_text(encoding="utf-8")

    assert "播放列表或系列视频" in content
    assert "不要把它当成单个视频处理" in content
    assert "## 一句话总结" in content
    assert "## 内容类型" in content
    assert "## 核心观点" in content
    assert "## 详细笔记" in content
    assert "## 价值评分" in content


def test_concepts_prompt_stays_focused_on_concept_cards():
    content = (ROOT / "prompts" / "concepts.txt").read_text(encoding="utf-8")

    assert "## 关键概念" in content
    assert "## 概念关系图" in content
    assert "[[概念名称]]" in content
    assert "不要重复总结视频主线" in content
    assert "未明确提及" in content


def test_actions_prompt_requires_checkbox_and_no_guessing():
    content = (ROOT / "prompts" / "actions.txt").read_text(encoding="utf-8")

    assert "## 行动项" in content
    assert "- [ ]" in content
    assert "未明确提及" in content
    assert "不要重复视频总结" in content


@pytest.mark.parametrize(
    ("prompt_name", "signature_section"),
    [
        ("type_tech_tutorial.txt", "## 技术栈与环境要求"),
        ("type_knowledge.txt", "## 概念图谱"),
        ("type_podcast.txt", "## 嘉宾信息"),
        ("type_business.txt", "## 市场数据与关键指标"),
    ],
)
def test_type_prompts_are_supplemental_and_no_guessing(prompt_name, signature_section):
    content = (ROOT / "prompts" / prompt_name).read_text(encoding="utf-8")

    assert signature_section in content
    assert "补充分析" in content
    assert "不要重复" in content
    assert "未明确提及" in content
    assert "不要猜测" in content
