# youtube-to-obsidian

[English README](./README.en.md)

将 YouTube 视频或播放列表送入 NotebookLM，产出结构化中文笔记并写入 Obsidian。

## 核心亮点

- 零 API 成本：不需要自备 OpenAI / Anthropic API key，也不会产生单独的模型 API 调用账单
- 面向 Obsidian：直接输出适合长期沉淀的结构化 Markdown
- 支持播放列表汇总：既能逐条分析，也能把一组视频合并成一篇系列总结
- 有字幕兜底：NotebookLM 读不动 URL 时，会尝试提取字幕继续分析

## 这是什么

这个项目解决的是一条完整知识管道：

1. 用 `yt-dlp` 读取 YouTube 元数据
2. 优先把 YouTube URL 直接喂给 NotebookLM
3. 如果 NotebookLM 不能直接读取，就提取字幕文本作为兜底 source
4. 用一组 prompt 生成中文结构化分析
5. 把结果写成 Markdown，落到 Obsidian Vault

输出内容面向“二次整理和长期检索”，不是简单摘要。

## 当前能力

- 处理单个 YouTube 视频
- 处理 YouTube 播放列表
- 播放列表支持两种模式：
  - `individual`：逐个视频分析，逐篇生成笔记
  - `combined`：把多个视频放进同一个 Notebook，生成一篇汇总笔记
- 多 prompt 分析：
  - `core` / `core_playlist`
  - `type_*`
  - `concepts`
  - `actions`
- 可选生成 NotebookLM artifacts：
  - mind map
  - study guide
  - quiz
  - audio overview
- 自动写入 Obsidian frontmatter
- SQLite 去重，避免重复处理

## 技术栈

- Python 3.12
- `uv`
- `yt-dlp`
- `notebooklm-py[browser]`
- `click`
- `pyyaml`
- `pytest`

## 项目结构

```text
youtube-to-obsidian/
├── main.py                 # CLI 入口
├── config.yaml             # 运行配置
├── prompts/                # 所有分析 prompt
├── src/
│   ├── extractor.py        # yt-dlp 元数据/字幕提取
│   ├── analyzer.py         # NotebookLM 分析
│   ├── generator.py        # Markdown 生成
│   └── pipeline.py         # 流程编排
├── tests/                  # 回归测试
└── processed.db            # 处理记录（运行后创建）
```

## 环境要求

你需要本地具备：

- Python 3.12+
- `uv`
- `yt-dlp`
- 可用的 Google / NotebookLM 登录环境
- 一个可写入的 Obsidian Vault

## 安装

### 1. 安装依赖

```bash
uv sync
```

如果你还没有装 `yt-dlp`，请先确保它在 PATH 中可用：

```bash
yt-dlp --version
```

### 2. 登录 NotebookLM

首次使用前先完成登录：

```bash
uv run notebooklm login
```

这个步骤会打开浏览器登录。后续 CLI 会通过本地已保存的登录态访问 NotebookLM。

### 3. 修改配置

编辑 [`config.yaml`](/Users/hongling/youtube-to-obsidian/config.yaml)：

```yaml
obsidian:
  vault_path: "/Users/yourname/your-vault"
  inbox_folder: "0-收集箱"

youtube:
  preferred_languages: ["zh", "en"]

notebooklm:
  cleanup_notebook: true
  generate_audio: false
  generate_mind_map: true
  generate_quiz: false
  generate_study_guide: true
  analyze_concepts: true
  analyze_actions: true
  analyze_type_specific: true

playlist:
  default_delay: 5

db_path: "./processed.db"
```

最重要的是：

- `obsidian.vault_path`
- `youtube.preferred_languages`
- `notebooklm.*` 开关

## 用法

### 处理单个视频

```bash
uv run python main.py process "https://www.youtube.com/watch?v=VIDEO_ID"
```

强制重新处理：

```bash
uv run python main.py process --force "https://www.youtube.com/watch?v=VIDEO_ID"
```

### 处理播放列表

#### 模式一：逐个分析

每个视频单独创建 Notebook、单独写一篇笔记。

```bash
uv run python main.py playlist "https://www.youtube.com/playlist?list=PLAYLIST_ID" --mode individual
```

只处理最新 5 个：

```bash
uv run python main.py playlist "https://www.youtube.com/playlist?list=PLAYLIST_ID" --mode individual --last 5
```

设置视频间隔：

```bash
uv run python main.py playlist "https://www.youtube.com/playlist?list=PLAYLIST_ID" --mode individual --delay 10
```

#### 模式二：合并分析

把多个视频作为一个 Notebook 的多个 source，输出一篇汇总笔记。

```bash
uv run python main.py playlist "https://www.youtube.com/playlist?list=PLAYLIST_ID" --mode combined
```

只汇总最后 7 个视频：

```bash
uv run python main.py playlist "https://www.youtube.com/playlist?list=PLAYLIST_ID" --mode combined --last 7
```

强制重跑：

```bash
uv run python main.py playlist --force "https://www.youtube.com/playlist?list=PLAYLIST_ID" --mode combined --last 7
```

## 输出内容

### 单视频笔记

默认写入：

```text
{vault_path}/{inbox_folder}/视频标题.md
```

内容包含：

- frontmatter
- 核心分析
- 类型专项分析
- 概念卡片
- 行动项
- 可选 artifacts 链接

### 播放列表汇总笔记

默认写入：

```text
{vault_path}/{inbox_folder}/播放列表标题.md
```

内容包含：

- 播放列表 frontmatter
- 视频列表表格
- `core_playlist` 汇总分析
- 类型专项分析
- 概念提取
- 行动建议

### Artifact 输出

如果在配置中开启，会写到 Vault 附件目录：

- `mind_map` → `_附件/mindmaps/`
- `study_guide` → `_附件/`
- `quiz` → `_附件/quizzes/`
- `audio` → `_附件/`

## Prompt 体系

Prompt 文件位于 `prompts/`：

- `core.txt`：单视频核心分析
- `core_playlist.txt`：播放列表汇总分析
- `type_tech_tutorial.txt`
- `type_knowledge.txt`
- `type_podcast.txt`
- `type_business.txt`
- `concepts.txt`
- `actions.txt`

设计原则：

- `core*` 负责主线
- `type_*` 只做补充分析
- `concepts` 只提炼概念卡片
- `actions` 只提炼可执行动作

## 工作机制

### 单视频流程

1. `yt-dlp` 提取元数据
2. 创建 NotebookLM Notebook
3. 优先添加 YouTube URL
4. 失败时提取字幕并上传文本
5. 运行 `core`
6. 运行 `type_* / concepts / actions`
7. 可选生成 artifacts
8. 写入 Obsidian

### 播放列表 combined 流程

1. `yt-dlp --flat-playlist` 拉取播放列表条目
2. 把多个视频逐个加入同一个 Notebook
3. 运行 `core_playlist`
4. 根据识别出的 `内容类型` 追加 `type_*`
5. 再运行 `concepts` 和 `actions`
6. 生成一篇汇总 Markdown

## 已知限制

- `combined` 模式受 NotebookLM source 数量限制影响，当前最多支持 50 个视频
- `combined` 模式真实分析通常比单视频慢很多
- 如果 YouTube URL 无法被 NotebookLM 直接读取，项目会尝试走字幕兜底，但不保证每个视频都能成功
- 播放列表汇总质量高度依赖 NotebookLM 对多 source 的读取质量
- 有些视频没有字幕，或者字幕质量很差，分析质量会下降

## 调试

### 运行测试

```bash
pytest -q
```

### 常见问题排查

#### 1. `yt-dlp` 报错

先手动验证：

```bash
yt-dlp --dump-json --no-download --no-playlist "https://www.youtube.com/watch?v=VIDEO_ID"
```

#### 2. NotebookLM 一直卡在分析阶段

先确认登录态是否仍然有效：

```bash
uv run notebooklm login
```

然后减少处理规模，例如：

```bash
uv run python main.py playlist "https://www.youtube.com/playlist?list=PLAYLIST_ID" --mode combined --last 2
```

#### 3. 输出内容不像汇总，更像单视频

确认你在用的是：

```bash
--mode combined
```

当前实现会使用 `core_playlist.txt` 做播放列表专用汇总分析。如果你修改了 prompt，请检查它是否仍保留“汇总多个视频”的约束。

#### 4. 生成的 Obsidian 链接不对

检查：

- `vault_path` 是否正确
- Vault 内是否存在对应目录
- Obsidian 是否启用了标准 wikilink 解析

## 开发

### 安装开发依赖

```bash
uv sync --dev
```

### 运行测试

```bash
pytest -q
```

### 关键文件

- [`main.py`](/Users/hongling/youtube-to-obsidian/main.py)
- [`src/extractor.py`](/Users/hongling/youtube-to-obsidian/src/extractor.py)
- [`src/analyzer.py`](/Users/hongling/youtube-to-obsidian/src/analyzer.py)
- [`src/pipeline.py`](/Users/hongling/youtube-to-obsidian/src/pipeline.py)
- [`src/generator.py`](/Users/hongling/youtube-to-obsidian/src/generator.py)
- [`config.yaml`](/Users/hongling/youtube-to-obsidian/config.yaml)

## 许可证

本项目采用 [MIT License](./LICENSE) 开源协议。
