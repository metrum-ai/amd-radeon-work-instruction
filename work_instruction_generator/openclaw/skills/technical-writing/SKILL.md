<!--
Copyright Advanced Micro Devices, Inc.

SPDX-License-Identifier: MIT
-->

---
name: technical-writing
description: Write one ISO 9001-compliant EV battery assembly work-instruction step for shop-floor operators, adapting language when a station is interlock-blocked.
command-dispatch: tool
command-name: wig-tools__generate_step
---

# Technical writing

Use this skill when the pipeline needs the next authored instruction step for
a document (the `author_steps` stage of `openclaw/lobster/wig_pipeline.lobster.yaml`).

Call the `wig-tools__generate_step` tool with the step number, step
description, source evidence, SOP context, current machine state, and
interlock result. The tool owns all prompt construction, the call to the
authoring model (`gemma-author`), safety-warning extraction, and the
deterministic offline fallback — do not attempt to draft instruction text
yourself; always invoke the tool and return its result unmodified.

If `interlock_result.status` is `"blocked"`, the tool automatically switches
to authoring recovery/prerequisite instructions instead of the normal step —
no special handling is needed on the caller side.
