# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Illustration style presets."""
from dataclasses import dataclass


@dataclass
class IllustrationStyle:
    """Illustration style."""

    id: str
    name: str
    description: str
    prompt_prefix: str
    negative_prompt: str
    controlnet_strength: float
    width: int
    height: int
