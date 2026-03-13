"""Tests for generator helpers and note metadata."""

from src.generator import _has_actions, _parse_concepts


def test_parse_concepts_normalizes_whitespace_and_deduplicates():
    concepts_answer = """
## 关键概念

### [[ React ]]
- 定义：UI library

### [[React]]
- 定义：duplicate

### [[TypeScript]]
- 定义：language
"""

    assert _parse_concepts(concepts_answer) == ["React", "TypeScript"]


def test_has_actions_false_for_placeholder_only():
    actions_answer = "## 行动项\n\n- [ ] 未明确提及"

    assert _has_actions(actions_answer) is False


def test_has_actions_true_for_real_checkbox_items():
    actions_answer = """## 行动项

- [ ] 安装 [[Python]]
  - 目的：搭建环境
"""

    assert _has_actions(actions_answer) is True
