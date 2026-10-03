# MAF-M0.8.1 Codex ImageGen Bridge

## Goal

Use Codex built-in image generation for MADO Asset Foundry probes and small batches so generation can consume general Codex usage instead of requiring an OpenAI API key.

## Model split

The two model roles are intentionally separate:

```text
Codex orchestrator
  Luna / Sol / Astra
        ↓
      $imagegen
        ↓
built-in renderer
    gpt-image-2
```

OpenAI currently documents Codex built-in image generation as using `gpt-image-2` and counting toward general Codex usage limits.

Changing Luna, Sol, or Astra changes the orchestration/reasoning model. It does not currently select a different built-in image renderer.

## Transparency

Current OpenAI documentation says:

- `gpt-image-2` received transparent-background support in preview on 2026-08-20.
- `gpt-image-2.5-flare` and `gpt-image-2.5-sunburst` support transparent backgrounds with PNG or WebP.

Because the Codex built-in route currently uses `gpt-image-2`, MAF treats transparency as a verified runtime contract:

1. request a genuinely transparent background
2. require PNG output
3. decode the returned PNG
4. inspect its alpha channel
5. reject the candidate if every pixel is opaque

For a workflow that must explicitly render with GPT Image 2.5, use the `openai-image` provider.

## Recipe

```yaml
generation:
  provider: codex-imagegen
  model: gpt-image-2
  codex_model: gpt-6-luna
  codex_binary: codex
  codex_timeout_seconds: 420
  render_size: 1024x1024
  quality: low
  background: transparent
  output_format: png
```

Fixture:

```text
fixtures/forest-alchemy-codex.yaml
```

## Preflight

No image generation:

```bash
maf codex-imagegen-check
```

## Production ladder

Plan only:

```bash
maf production plan fixtures/forest-alchemy-codex.yaml
maf production start fixtures/forest-alchemy-codex.yaml --stage probe
```

One real Codex image:

```bash
maf production start fixtures/forest-alchemy-codex.yaml --stage probe --live
```

Then:

```bash
maf production start fixtures/forest-alchemy-codex.yaml --stage pilot --live
maf production start fixtures/forest-alchemy-codex.yaml --stage production --live
```

## Bridge behavior

For every requested image, MAF:

1. creates an isolated temporary directory
2. runs `codex exec --ephemeral`
3. uses `--sandbox workspace-write`
4. selects the configured Codex orchestration model
5. explicitly invokes `$imagegen`
6. requests exactly one PNG at a deterministic path
7. requires a real PNG file to exist
8. decodes it
9. verifies alpha transparency when the recipe requires it
10. copies the accepted bytes into standard MAF raw evidence

A successful Codex text response without an acceptable PNG is a failed generation.

## Which orchestrator?

For the current Forest Alchemy recipe:

- Luna: default; short and tightly scoped art direction.
- Sol: useful if art-direction interpretation or iterative repair becomes more complex.
- Astra: useful for the most demanding multimodal planning or multi-step creative workflows.

All three currently hand image rendering to the same built-in `gpt-image-2`. Prefer the lightest orchestration model that consistently produces acceptable candidates.

## GPT Image 2.5 route

Use this when explicit GPT Image 2.5 rendering is more important than staying inside general Codex usage:

```yaml
generation:
  provider: openai-image
  model: gpt-image-2.5-flare
  background: transparent
  output_format: png
```

This route uses API Platform billing.

## Official references

- https://learn.chatgpt.com/docs/image-generation
- https://learn.chatgpt.com/docs/model-selection
- https://learn.chatgpt.com/docs/developer-commands
- https://developers.openai.com/api/docs/guides/image-generation
- https://developers.openai.com/api/docs/changelog
