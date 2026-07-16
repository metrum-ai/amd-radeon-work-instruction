<!--
Copyright Advanced Micro Devices, Inc.

SPDX-License-Identifier: MIT
-->
---
name: flux-prompt-summarization
description: Precede illustration generation by summarizing a step into the physical-scene sentence the Flux image model needs.
command-dispatch: tool
command-name: wig-tools__generate_illustrations
---

# Flux prompt summarization

Use this skill for the `generate_illustrations` stage of
`openclaw/lobster/wig_pipeline.lobster.yaml`.

Call the `wig-tools__generate_illustrations` tool with the document ID and
the authored steps. Internally, the tool summarizes each step into a single
physical-scene sentence via the authoring model before submitting the Flux
render job on GPU 3 via Lemonade — if that summarization call fails, it falls
back to using the step's title verbatim. Do not write the Flux prompt
yourself; always invoke the tool and return its result unmodified.
