# MAF-M1.5.2 Colab Artifact Export / Persistent GPU Evidence Bridge

MAF-M1.5.2 provides human-triggered export of finished MiniMax H3 video outputs, persistent-destination readback, and secure offline intake into MAF.

No GPU job launch, Colab authentication, API tunnel, third-party repository cloning, model downloading, marketplace release, or license clearance is performed.

## Why a single ZIP?

Google's Colab FAQ warns that mounted Drive folders can suffer I/O errors and quota limits when used for many small files. We stage one archive on the local runtime first, then copy the archive to an explicitly selected folder and rehash it.

Note: successful mounted-filesystem readback is NOT evidence that Google Drive has finished synchronizing to the cloud.

## Run in Colab after a successful H3 generation

1. Generate a video in the supplied MiniMax_H3.ipynb notebook. Its outputs are under /content/h3-lab/results/<job-id>/.
2. Manually mount Drive using the trusted notebook's Colab session: from google.colab import drive; drive.mount('/content/drive').
3. Manually create /content/drive/MyDrive/madowaku/h3. It must exist before export.
4. Explicitly place a reviewed checkout of mado-asset-foundry under /content/mado-asset-foundry. No automatic download is implemented.
5. In a new Colab Python cell, run:

    import sys
    from pathlib import Path
    sys.path.insert(0, "/content/mado-asset-foundry/src")
    from mado_asset_foundry.colab_artifact_bridge import export_h3_bundle, inspect_h3_bundle

    job = "<job-id>"  # Use the actual notebook results subfolder
    folder = Path("/content/h3-lab/results") / job
    receipt = export_h3_bundle(
        folder / "video.mp4",
        "/content/drive/MyDrive/madowaku/h3",
        run_id=f"h3-{job}",
        settings=folder / "settings.json",
        profile="int8",
    )
    print(receipt)
    print(inspect_h3_bundle(receipt["destination"])["integrity"])

Change profile to full only when the notebook generation actually used that setting. Video generation is NOT performed by the export call.

## CLI on a MAF checkout

    maf colab preflight --profile int8
    maf colab export /content/h3-lab/results/<job-id>/video.mp4 --settings /content/h3-lab/results/<job-id>/settings.json --dest /content/drive/MyDrive/madowaku/h3 --run-id h3-probe-001 --profile int8
    maf colab inspect /content/drive/MyDrive/madowaku/h3/h3-probe-001.h3.zip

After manually transferring the ZIP to another machine, install ffprobe and run:

    maf colab import /path/to/h3-probe-001.h3.zip --output-root runs/h3-imports

## Evidence formats

The archive contains manifest.json, video.mp4, hardware.json, and optionally settings.json.

- manifest.json: run ID, declared model and notebook name, profile, per-file sizes and SHA-256.
- hardware.json: M1.5.1 read-only hardware capacity report and explicit unverified-GPU-generation state.
- settings.json: original H3 notebook generation report if supplied by the operator.
- import_receipt.json: independent MAF ffprobe data, hashes, license-review requirement and closed release gate, written under runs/h3-imports/<run-id>/.

No hardware report proves that the notebook actually completed GPU inference. Always keep model and regional-license review, media-rights review, and visual approval separate.

## Safety and persistence boundaries

- The operator must choose an existing destination. Never intentionally overwrite prior run IDs or valid archives.
- Members must have fixed file names. Reject archive traversal, symlinks, compressed payloads, extras, duplicates, oversized files, corrupted SHA-256 or non-object JSON metadata.
- Intake rechecks copied bytes and uses M1.5.1 ffprobe validation. It does not execute content from ZIP.
- Persistent destination readback confirms bytes currently available at that mount, not asynchronous cloud replication.
- Inspect a newly downloaded ZIP on another machine before deleting the Colab original. Preserve a backup until verified.
- Work only with completed notebook results. No automatic marketplace publishing or asset-pack promotion.

## Follow-up

M1.5.3: Cockpit UI review and optional provider-authenticated post-sync evidence; keep remote authentication strictly opt-in.

Reference: https://research.google.com/colaboratory/faq.html?hl=ja
