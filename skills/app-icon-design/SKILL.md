---
name: app-icon-design
description: Design and prepare platform app icons at the requested stage, especially for macOS/iOS icons that should be finalized with Apple Icon Composer. Use when Codex is asked to design an app icon, generate icon concepts, choose icon style/subject, prepare 1024 square icon artwork, use Icon Composer, avoid manual rounded-corner masking, export review PNGs, or integrate generated icons into app build assets.
---

# App Icon Design

Use this skill to turn an app icon request into a reusable design and production workflow.

Identify the current deliverable: concept exploration, production assets, or project
integration. Enter at the required stage and run only applicable steps. Reuse any direction
already specified or accepted by the user; honor delegated design choices and existing
authorization. Stop when the requested deliverable meets its applicable checks below.

## Workflow

1. Clarify the product signal.
   - Identify the app name, category, primary object/metaphor, target platform, and desired tone.
   - Ask only for missing decisions that materially affect visual direction.
   - Prefer concrete visual anchors over abstract brand adjectives.

2. Explore style when needed.
   - Generate alternatives when requested or needed to resolve a material visual choice. Otherwise reuse the established direction.
   - Vary subject treatment, material, perspective, background, and accent color.
   - Present options as style candidates, not production-ready assets.
   - Judge concepts in likely real contexts: Dock, Finder, Launchpad, Home Screen, or app store listings when relevant.

3. Resolve the direction for production.
   - Proceed with the specified or accepted direction. Ask about remaining material choices only when the user has not delegated them.
   - Resolve scale, whitespace, contrast, recognizability at small sizes, and whether the icon reads beside system icons.
   - If the icon looks too large beside system icons, adjust subject scale and padding rather than corner radius.

4. Prepare production inputs when applicable.
   - Output square artwork at 1024 x 1024 px for macOS, iOS, and iPadOS unless the target platform requires another size.
   - Do not bake in macOS/iOS rounded corners for Icon Composer or asset catalog inputs.
   - Use full square canvas artwork with appropriate edge-safe padding.
   - Use transparent layers only when intentionally creating layered artwork; for a flattened icon input, prefer an opaque square image.
   - Keep source inputs named clearly, such as `app-icon-input-1024.png`.

5. Use Icon Composer for Apple app icons when applicable.
   - If Codex needs to operate Icon Composer directly, use the `computer-use` skill or available GUI automation tools. Icon Composer is primarily a GUI app.
   - First verify Icon Composer is installed, usually through Xcode > Open Developer Tool > Icon Composer or `/Applications/Xcode.app/Contents/Applications/Icon Composer.app`.
   - Import the square artwork or layers into Icon Composer.
   - Preview platform and appearance variants inside Icon Composer.
   - Disable Icon Composer effects that unintentionally recolor or distort already-rendered bitmap artwork.
   - Save the `.icon` document as the editable source of truth.
   - Export static PNGs only for review, handoff, or custom build pipelines that cannot consume `.icon`.
   - Do not assume `ictool` can create `.icon` documents. Use it only as an optional export/inspection helper for existing `.icon` files after verifying it works in the local Xcode version.
   - If GUI automation is unavailable, prepare the input files and give the user exact Icon Composer steps instead of pretending the task is fully automated.

6. Avoid double masking.
   - Do not feed a rounded-corner PNG into a pipeline that will apply system masking again.
   - If a static exported PNG already contains a mask, treat it as a final rendered asset for contexts that expect alpha, not as a new source image for another masked pipeline.
   - When using Xcode asset catalogs or Icon Composer directly, prefer unmasked square sources.

7. Integrate when authorized, based on project shape.
   - For Xcode projects that support Icon Composer, add the `.icon` file to the project and configure the target to use it.
   - For projects using asset catalogs, provide the required unmasked square app icon assets.
   - For custom macOS `.app` bundling, generate `.icns` from the chosen production source and ensure `Info.plist` points to it with `CFBundleIconFile`.
   - Add a build or packaging check when feasible so app bundles do not silently lose their icon.

## Apple-Specific Guidance

For Apple platform icons, verify current guidance from official Apple sources when exact behavior matters:

- https://developer.apple.com/design/human-interface-guidelines/app-icons
- https://developer.apple.com/documentation/xcode/creating-your-app-icon-using-icon-composer
- https://developer.apple.com/design/resources/

Use Apple templates or Icon Composer previews for shape, scale, and platform fit. Do not manually approximate the system corner radius unless the target output explicitly requires a pre-rendered static icon and no later system masking will occur.

## Output Checklist

Before declaring the requested deliverable complete, verify only its applicable checks:

- For concept exploration, deliver the requested style candidates and explain their tradeoffs; production approval and assets are not required.
- For production, the visual direction matches the user's request, prior approval, or delegated choice.
- Any production input meets the target platform's required dimensions and is square and unmasked when intended for Icon Composer or system masking.
- Production artwork has been reviewed at realistic small sizes and beside neighboring system/app icons.
- The `.icon` source file is saved when Icon Composer is used for production.
- Any exported PNG or `.icns` has a clear role and is not being reused in a way that causes double masking.
- The app build or packaging path has been verified when the task includes integration.
