"""全局配置（基于 pydantic-settings，从环境变量或 .env 加载）。

约定：
- 所有配置项可通过环境变量覆盖
- DOCANCHOR_* 前缀的环境变量
- .env 文件优先级低于显式环境变量
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置。"""

    model_config = SettingsConfigDict(
        env_prefix="DOCANCHOR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- LLM（小模型） ---
    llm_base_url: str = Field(default="", description="内网OpenAI兼容API地址")
    llm_api_key: str = Field(default="", description="鉴权Key")
    llm_model: str = Field(default="qwen2.5-7b-instruct", description="模型名")
    llm_call_budget: int = Field(default=20, ge=1, description="单篇文档LLM调用上限")
    llm_temperature_judgment: float = Field(default=0.0, le=1.0, description="判断/分类任务温度")
    llm_temperature_semantic: float = Field(default=0.3, le=1.0, description="语义分析任务温度")

    # --- PDF转换 ---
    pdf_engine: Literal["libreoffice", "onlyoffice", "word_com"] = "libreoffice"
    pdf_engine_fallback: list[str] = Field(
        default_factory=lambda: ["libreoffice", "onlyoffice", "word_com"],
        description="降级链路顺序",
    )

    # --- 阈值 ---
    block_confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    llm_confidence_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    cross_page_overlap_threshold_low: float = Field(default=0.15, ge=0.0, le=1.0)
    cross_page_overlap_threshold_high: float = Field(default=0.30, ge=0.0, le=1.0)
    heading_level_window_size: int = Field(default=10, ge=2)
    heading_level_window_overlap: int = Field(default=2, ge=1)
    heading_level_rollback_after_windows: int = Field(default=5, ge=1)
    image_caption_distance_ratio: float = Field(default=0.30, ge=0.0, le=2.0)

    # --- 文字校验 ---
    text_strong_match_threshold: float = Field(default=0.95, ge=0.0, le=1.0)
    text_weak_match_threshold: float = Field(default=0.80, ge=0.0, le=1.0)

    # --- VLM Adapter ---
    vlm_provider: Literal["mock", "mineru"] = "mock"
    vlm_max_retries: int = Field(default=2, ge=0)
    vlm_fallback_to_pymupdf: bool = True

    # --- 输出 ---
    template_path: str = Field(default="", description="预置DOCX模板路径，空则使用内置默认")
    output_dir: str = "output"


_settings: Settings | None = None


def get_settings() -> Settings:
    """获取全局配置单例。"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    """测试用：重置配置单例。"""
    global _settings
    _settings = None


__all__ = ["Settings", "get_settings", "reset_settings"]