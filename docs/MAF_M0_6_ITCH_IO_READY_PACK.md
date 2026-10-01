# MAF-M0.6 itch.io Ready Pack

## Goal

Turn a compiled Product ZIP into a human-reviewable itch.io release kit without automatically publishing anything.

## Current itch.io constraints encoded

- Keep the project in Draft while preparing the page.
- Classify this product as Assets.
- Treat the ZIP as Graphical Assets, not an executable platform build.
- Provide a cover image using itch.io's 315:250 aspect ratio. MAF generates 630x500.
- Provide screenshots. MAF generates three truthful screenshots from the packaged assets.
- Accurately complete Generative AI disclosure. Asset pages are subject to strict disclosure expectations.
- Avoid mass-producing minimally curated AI asset pages.
- Use only relevant tags.
- Public publishing remains a human action.

Reference pages:

- https://itch.io/docs/creators/quality-guidelines
- https://itch.io/t/4309690/generative-ai-disclosure-tagging
- https://itch.io/docs/creators/getting-started
- https://itch.io/docs/creators/access-control

## Command

```bash
maf itch-ready runs/<run-id>
```

The command requires M0.5 packaging evidence first:

```bash
maf package runs/<run-id>
maf itch-ready runs/<run-id>
```

## Output

```text
runs/<run-id>/
  itch/
    report.json
    forest-alchemy-icons-0.1.0/
      READY.json
      listing.json
      title.txt
      short-description.txt
      description.md
      tags.json
      ai-disclosure.md
      policy-notes.md
      release-checklist.md
      cover.png
      screenshots/
        01-contact-sheet.png
        02-sprite-sheet.png
        03-samples.png
      upload/
        forest-alchemy-icons-0.1.0.zip
```

## Release gate

`READY.json` separates blockers from warnings.

Blockers currently include:

- product license is not marked public
- a draft license identifier remains
- AI-assisted graphics are not declared in itch metadata

Manual pricing review is a warning, not a blocker.

The fixture intentionally uses `MADO-DOGFOOD-DRAFT`, so its first release pack is expected to build successfully while reporting `ready: false`.

## Exit codes

- 0: ready pack generated and no blockers remain
- 1: build/configuration/integrity error
- 2: ready pack generated, but human-release blockers remain

## Non-goal

M0.6 does not create an itch.io project, log into itch.io, call Butler, or switch a page to Public.
