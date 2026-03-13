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


@cli.command()
@click.argument("url")
@click.option("--mode", type=click.Choice(["individual", "combined"]), default="individual", help="分析模式")
@click.option("--last", type=int, default=None, help="只处理最新 N 个视频")
@click.option("--delay", type=int, default=5, help="视频间隔秒数（仅 individual 模式）")
@click.option("--force", is_flag=True, help="强制重新处理")
def playlist(url, mode, last, delay, force):
    """处理 YouTube 播放列表"""
    config = load_config()
    pipeline = Pipeline(config)
    if mode == "combined":
        asyncio.run(pipeline.process_playlist_combined(url, last=last, force=force))
    else:
        asyncio.run(pipeline.process_playlist_individual(url, last=last, delay=delay, force=force))


if __name__ == "__main__":
    cli()
