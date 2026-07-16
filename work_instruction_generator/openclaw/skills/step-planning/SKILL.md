<!--
Copyright Advanced Micro Devices, Inc.

SPDX-License-Identifier: MIT
-->

---
name: step-planning
description: Decompose an EV battery assembly procedure into an ordered list of atomic operator steps, inserting unmet-prerequisite steps where needed.
command-dispatch: tool
command-name: wig-tools__plan_steps
---

# Step planning

Use this skill for the `plan_steps` stage of
`openclaw/lobster/wig_pipeline.lobster.yaml`, before per-step authoring begins.

Call the `wig-tools__plan_steps` tool with the procedure's source evidence,
SOP context, and (if the station is interlock-blocked) the list of
`required_actions` as `blocked_prereqs`. The tool handles prompt
construction, the call to the authoring model, deduplication, step-count
capping, and the fallback step list used when the model is unreachable.
Return the tool's result unmodified — each item is `{"desc": str, "prereq": bool}`.
