---
name: apple-signing-workflow
description: Use when building, packaging, installing, or diagnosing signing for Apple platform apps with Xcode, xcodebuild, Flutter, Swift, or XcodeGen, especially for automatic signing, DEVELOPMENT_TEAM, certificate and provisioning-profile identity, entitlements, codesign verification, or errors such as No Accounts and No profiles found.
---

# Apple Signing Workflow

Use Xcode automatic signing for the user's local development builds while binding the build and final artifact to the intended Apple Developer team.

## Signing Contract

- Treat `<REDACTED_APPLE_ID>` as the expected Team ID for the user's own development-signed apps.
- Do not infer a Team ID from the parenthesized suffix in a certificate display name. In particular, `<REDACTED_APPLE_ID>` in a display name is not this user's Team ID.
- Prefer authoritative identity evidence: certificate subject `OU`, provisioning-profile `TeamIdentifier`, signed-artifact `TeamIdentifier`, and signed entitlements.
- Keep automatic signing enabled unless the repository or requested distribution workflow explicitly requires manual signing.
- Do not delete or revoke Development certificates as a routine fix. Certificate cleanup is a separate destructive action and requires evidence that the identity is expired, revoked, duplicated without need, or otherwise invalid, plus explicit user authorization.
- If an applicable repository deliberately uses another team or distribution identity, stop and reconcile that contract instead of silently replacing it.

## Workflow

1. Inspect applicable `AGENTS.md`, project metadata, build scripts, Xcode settings, Bundle IDs, entitlements, and requested artifact type.
2. Inspect signing identities and profiles without exposing private keys, account identifiers, or unrelated credential material.
3. Cross-check that the selected Development certificate has subject `OU=<REDACTED_APPLE_ID>` and that the applicable provisioning profile has `TeamIdentifier=<REDACTED_APPLE_ID>`.
4. Build the user's app with automatic signing and an explicit `DEVELOPMENT_TEAM=<REDACTED_APPLE_ID>`. Preserve the repository's scheme, configuration, destination, and other build flags. Use provisioning-update flags only when required by the established build flow.
5. Verify the exact final `.app`, archive, or exported artifact rather than relying on project settings or build success alone.

## Artifact Verification

Run checks appropriate to the artifact and record their outputs without leaking sensitive profile content:

- Verify signature integrity with `codesign --verify --deep --strict --verbose=2 <app>`.
- Inspect signature metadata with `codesign -dvvv <app>` and require `TeamIdentifier=<REDACTED_APPLE_ID>`.
- Extract signed entitlements with `codesign -d --entitlements :- <app>`.
- Require `com.apple.developer.team-identifier` to equal `<REDACTED_APPLE_ID>` when present.
- Require `application-identifier` and relevant keychain access groups to start with `<REDACTED_APPLE_ID>.` for this user's development profile.
- Decode `embedded.mobileprovision` when present and cross-check its `TeamIdentifier`, application identifier, Bundle ID coverage, expiration, and target-device coverage when device installation is requested.

Treat any disagreement among certificate `OU`, build setting, profile, signature metadata, and entitlements as a failed signing contract. Diagnose the mismatch before rebuilding or changing Keychain state.

## Completion Report

Report these axes separately as applicable: build, signature integrity, Team ID, profile and entitlements, artifact creation, installation, launch, Developer ID, notarization, and App Store readiness. Do not infer installation or distribution readiness from a successful build.
