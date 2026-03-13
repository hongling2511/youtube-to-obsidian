"""YouTube → NotebookLM → Obsidian CLI 入口"""

import asyncio
from pathlib import Path

import click
import yaml

from src.pipeline import Pipeline


def load_config() -> dict:
    """加载 config.yaml 配置"""
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@click.group()
def cli():
    """YouTube → NotebookLM → Obsidian 知识管道"""
    pass


@cli.command()
@click.argument("url")
@click.option("--force", is_flag=True, help="强制重新处理已处理过的视频")
def process(url, force):
    """处理单个 YouTube 视频"""
    config = load_config()
    pipeline = Pipeline(config)
    asyncio.run(pipeline.process(url, force=force))


if __name__ == "__main__":
    cli()
