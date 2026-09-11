"""VLM Provider集合（可插拔）。"""

from docanchor.modules.vlm_adapter.providers.base import BaseVLMProvider
from docanchor.modules.vlm_adapter.providers.mock import MockVLMProvider
from docanchor.modules.vlm_adapter.providers.mineru import MinerUProvider

__all__ = ["BaseVLMProvider", "MockVLMProvider", "MinerUProvider"]