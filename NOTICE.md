# NOTICE

Barthelona
Copyright (c) 2026, Oleksandr Lopatnov

Barthelona was created and is maintained by Oleksandr Lopatnov (https://github.com/lopatnov). The original
work in this repository (source code, configuration, scripts and documentation, except the third-party
material listed below) is licensed under the BSD 2-Clause License; see `LICENSE`.

If you redistribute this software or a derivative work, in source or binary form, the BSD 2-Clause License
requires you to keep the copyright notice and license text in `LICENSE`. The license sets no other
conditions. As a courtesy, not a license term, please also keep this `NOTICE.md` file or an equivalent
attribution to Oleksandr Lopatnov as the original author.

## AI-assisted development

Parts of this repository were written with AI coding assistants (Anthropic Claude Code, OpenAI Codex)
working under the author's direction. Such commits carry a `Co-Authored-By:` trailer. The author reviewed,
selected and owns the resulting work; the assistants hold no rights in it.

## Third-party material in this repository

These files are not covered by the BSD 2-Clause License. They remain under their own licenses and belong to
their respective authors. Whether to keep them in the published repository is open decision 7 in
`docs/roadmap.md`.

| Path | Work | Rights holder | License |
| --- | --- | --- | --- |
| `asm_doc/nasm-3.02-xdoc/` | NASM 3.02 documentation | The NASM Authors | BSD 2-Clause |
| `asm_doc/binutils/` | GNU Binutils manuals (as, ld, bfd, binutils, gprof, gprofng, ctf, sframe) | Free Software Foundation, Inc. | GNU Free Documentation License |
| `asm_doc/fasm/` | flat assembler and fasmg manuals | Tomasz Grysztar | Terms stated by the author; not verified |
| `asm_doc/masm/` | Microsoft C++ / MASM assembler reference (PDF) | Microsoft Corporation | Creative Commons Attribution 4.0 (Microsoft Learn docs) |

`.reference/` (gitignored, never published) holds third-party study projects under their own licenses.

## Third-party software used at run time

Barthelona does not bundle third-party software. Its Python dependencies are declared in `pyproject.toml`
and installed from PyPI under their own licenses, among them:

- Unicorn (`unicorn`, emulator), Capstone (`capstone`, disassembler): BSD-style licenses per their package
  metadata. Unicorn's native core has historically been GPL-2.0; check its current license before
  distributing binaries that bundle it.
- LIEF (`lief`): Apache License 2.0. pyelftools: public domain.
- LangGraph, Streamlit and the provider SDKs (Anthropic, OpenAI, Google GenAI): their own licenses.

Toolchains used in the WSL sandbox images (NASM, GNU Binutils, GCC, FASM and others) are installed from
their distributors when the images are built, and are not distributed with Barthelona.

Product and company names (Claude, ChatGPT, Gemini, DeepSeek, LM Studio, Ollama, Qdrant, Microsoft, Intel)
are trademarks of their owners and are used only to identify those products.
