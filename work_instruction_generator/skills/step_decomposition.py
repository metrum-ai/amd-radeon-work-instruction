# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

"""Step decomposition skill for WIG agents.

This skill provides utilities for breaking down complex instructions
into individual procedural steps that serve as input to the
TechnicalIllustrationAgent.
"""

import re


def estimate_view_angle(step_description: str) -> str:
    """Heuristically estimate the best view angle based on step action verbs."""
    action_verbs = {
        "insert": "close-up side view",
        "slide": "close-up side view",
        "attach": "isometric exploded view",
        "screw": "top-down close-up",
        "tighten": "top-down close-up",
        "align": "overhead view",
        "remove": "isometric",
        "lift": "isometric",
        "connect": "front view with cable/component detail",
        "lock": "close-up on locking mechanism",
        "press": "side view showing force direction",
        "rotate": "sequential view showing rotation",
        "install": "isometric exploded view",
        "configure": "interface close-up with callouts",
        "test": "front panel view with callouts",
        "inspect": "magnified detail view",
        "clean": "close-up with tool position",
        "verify": "callout detail on verification point",
    }

    for verb, angle in action_verbs.items():
        if re.search(rf"\b{verb}\b", step_description.lower()):
            return angle

    return "isometric"
