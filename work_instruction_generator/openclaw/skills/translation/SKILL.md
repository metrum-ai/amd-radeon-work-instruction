<!--
Copyright Advanced Micro Devices, Inc.

SPDX-License-Identifier: MIT
-->

---
name: translation
description: Translate an authored work-instruction step's title and body into the document's target language, preserving part numbers, units, and safety prefixes.
command-dispatch: tool
command-name: wig-tools__translate_step
---

# Translation

Use this skill when a document's `target_language` is not `"en"`, after the
`author_steps` stage produces an English step.

Call the `wig-tools__translate_step` tool with the step dict and the target
language. The tool calls the `translate-gemma` model with the terminology-
preservation rules baked into its prompt, and falls back to returning the
original English text unchanged if the translation model is unreachable —
do not translate text yourself or paraphrase the tool's output.
