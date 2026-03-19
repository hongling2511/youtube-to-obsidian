# Prompt Lab Policy

## 目标
自动迭代优化 youtube-to-obsidian 的 prompt，产出更高质量的 Obsidian 笔记。

## 可变面 (Mutable Surface)
- `prompts/core.txt` — 核心分析 prompt（本轮实验的优化目标）

## 不可变层 (Truth Layer)
- 测试视频集（固定，保证可比性）
- 评估维度和评分标准
- NotebookLM 分析链路

## 评估维度 (Verifier)
1. Faithfulness (忠实度, 0-10) — 是否编造了视频没说的内容
2. Completeness (完整性, 0-10) — 关键信息是否遗漏
3. Structure (结构合规, 0-10) — 是否严格遵循模板格式
4. Density (信息密度, 0-10) — 有效信息 vs 废话比例
5. Obsidian Fitness (Obsidian 适配度, 0-10) — 双向链接质量、可检索性
6. Actionability (可操作性, 0-10) — 行动项是否真的可执行

## 综合分 = 各维度加权平均
- Faithfulness: 25%
- Completeness: 20%
- Structure: 15%
- Density: 15%
- Obsidian Fitness: 15%
- Actionability: 10%

## Keep/Discard 规则
- 综合分高于 incumbent → keep，成为新 incumbent
- 综合分相同或更低 → discard，回退到 incumbent
- 简洁性优先：同分时更短的 prompt 胜出

## 变异策略
每轮从以下策略中选一个：
- 措辞微调（更精确的指令）
- 增加约束（减少幻觉）
- 删减冗余（提高信息密度）
- 结构调整（改变输出格式）
- 示例注入（添加 few-shot 示例）
