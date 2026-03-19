# Prompt Lab — Agent Program

你是一个自主 prompt 优化研究员。你的任务是通过自动化实验循环，迭代优化 `prompts/core.txt`。

## 环境准备

1. 读取 `prompt_lab/policy.md` 了解评估标准
2. 读取当前 `prompts/core.txt` 作为 baseline
3. 准备测试视频（使用已缓存的分析结果，或运行新分析）

## 测试视频

使用这个视频作为固定测试集（已在系统中处理过）：
- Karpathy "[1hr Talk] Intro to Large Language Models" (ID: zjkBMFhNj_g)

由于 NotebookLM 调用成本高且耗时长，采用以下策略：
- 使用 LLM 模拟评估：将 prompt + 视频字幕 → LLM 生成分析 → 评估输出质量
- 不实际调用 NotebookLM，而是用本地 LLM API 模拟分析过程

## 实验循环

每轮实验：

1. **读取 incumbent**: 当前最优的 `prompts/core.txt`
2. **变异**: 基于上一轮评分反馈，选择一个变异策略，生成新版 prompt
3. **执行**: 用新 prompt + 测试视频字幕，通过 LLM 生成分析结果
4. **评估**: 用 LLM-as-Judge 对输出打分（6 个维度，0-10）
5. **记录**: 将结果写入 `prompt_lab/results.tsv`
6. **决策**: 
   - 综合分 > incumbent → keep，保存新 prompt 到 `prompt_lab/versions/vN.txt`
   - 否则 → discard
7. **重复**

## 评估 Prompt (LLM-as-Judge)

对每个分析输出，使用以下评估 prompt：

```
你是一个严格的笔记质量评审员。请对以下 Obsidian 笔记分析结果打分。

评分维度（每项 0-10 分）：
1. Faithfulness (忠实度): 内容是否忠实于原始视频，有无编造
2. Completeness (完整性): 关键信息是否完整覆盖
3. Structure (结构合规): 是否严格遵循指定的 Markdown 模板格式
4. Density (信息密度): 有效信息占比，是否有废话或重复
5. Obsidian Fitness (Obsidian 适配度): 双向链接 [[]] 使用是否恰当，是否便于检索
6. Actionability (可操作性): 行动项是否具体、可执行

请严格按 JSON 格式输出：
{"faithfulness": N, "completeness": N, "structure": N, "density": N, "obsidian_fitness": N, "actionability": N, "reasoning": "简要说明"}
```

## 输出格式

results.tsv (tab-separated):
```
round	version	weighted_score	faithfulness	completeness	structure	density	obsidian_fitness	actionability	status	mutation_strategy	description
```

## 约束

- 共跑 10 轮
- 每轮只改 core.txt，不改其他 prompt
- 保留所有版本到 `prompt_lab/versions/`
- 完成后输出最终报告：最优版本、分数变化趋势、关键改进点
