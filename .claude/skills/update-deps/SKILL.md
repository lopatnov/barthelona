---
name: update-deps
description: Add, remove or upgrade a Python dependency the barthelona way - edit pyproject.toml, re-lock with scripts/lock.ps1 (hash-locked, Windows + Linux), reinstall with scripts/create_env.ps1, then verify. Use whenever a package needs to change; never pip install ad hoc.
argument-hint: "<add|remove|upgrade> <package>[spec] [extra]"
---
# Update dependencies: $ARGUMENTS

Read first: ADR D-031 (`docs/adr/D-031-dependencies-in-pyproject-locked-per-platform.md`).

1. **Justify the package.** It must not be on the exclusion list (LiteLLM, PyMuPDF, GPUtil, crewai, langchain provider packages). Verify the current version, license and Windows wheel availability on pypi.org; use the `docs-researcher` agent if unsure. If the dependency is significant, write an ADR (`/new-adr`).
2. **Edit `pyproject.toml`.** Runtime packages go in `[project.dependencies]`; optional ones go in the right extra (`dev`, `kb`, `obs`, `ingest-pdf`). Give the range a lower bound and a major-version upper bound.
3. **Re-lock:**
   - `.\scripts\lock.ps1` after an add or remove;
   - `.\scripts\lock.ps1 -UpgradePackage <name>` for a targeted upgrade;
   - `.\scripts\lock.ps1 -Upgrade` only if the user asked for everything.

   This asks for permission. Show `git diff --stat requirements/` and the changed pins.
4. **Reinstall** with `.\scripts\create_env.ps1`, which asks for permission and ends with `pip check`.
5. **Verify.** Run `/verify` and import-check the package.
6. **Report:** what changed, why, the pinned versions, and any transitive surprises (new native wheels, license changes).

Never edit `requirements/*.lock` by hand. A hook blocks it.
