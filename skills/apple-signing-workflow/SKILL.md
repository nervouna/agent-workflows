---
name: apple-signing-workflow
description: Use when building, packaging, installing, or diagnosing signing for Apple platform apps with Xcode, xcodebuild, Flutter, Swift, or XcodeGen, especially for automatic signing, DEVELOPMENT_TEAM, certificate and provisioning-profile identity, entitlements, codesign verification, or errors such as No Accounts and No profiles found.
---

# Apple Signing Workflow

Use Xcode automatic signing for the user's local development builds while binding the build and final artifact to the intended Apple Developer team.

Signing and artifact checks require macOS and the appropriate Xcode tools. Installing this skill does not supply a developer account, signing identity, provisioning profile, or authorization to distribute an app.

## Signing Contract

- Resolve the intended Team ID from the user's explicit request and the applicable repository contract, including target/configuration-specific `DEVELOPMENT_TEAM` settings. Record that expected identity before selecting a certificate or profile. If the request and project disagree, reconcile the conflict before changing either.
- If the intended team is absent or ambiguous, ask the user. An available certificate, a prior artifact, or an Xcode default is evidence of existing state, not permission to choose that team.
- Do not infer a Team ID from the parenthesized suffix in a certificate display name. Cross-check the selected Apple-issued certificate's subject `OU`, provisioning-profile `TeamIdentifier` where applicable, signed-artifact `TeamIdentifier`, and the signed team-identifier entitlement.
- Keep automatic signing enabled unless the repository or requested distribution workflow explicitly requires manual signing.
- Do not delete or revoke Development certificates as a routine fix. Certificate cleanup is a separate destructive action and requires evidence that the identity is expired, revoked, duplicated without need, or otherwise invalid, plus explicit user authorization.
- Preserve the requested artifact type: Development, Developer ID, and App Store signing are not interchangeable. Do not turn a diagnosis into a rebuild, installation, account change, or publication without authorization for that action.

## Workflow

1. Inspect applicable `AGENTS.md`, project metadata, build scripts, Xcode settings, Bundle IDs, entitlements, and requested artifact type.
2. Resolve the intended team, then inspect only relevant signing identities and profiles without exposing private keys, account identifiers, device lists, or unrelated credential material.
3. Cross-check the selected certificate's subject `OU` and the applicable profile's `TeamIdentifier` against the intended Team ID. Where a profile is required, also verify that it permits the selected signing certificate. Diagnose missing or mismatched evidence; do not silently select a different team to make the build pass.
4. When a build is authorized, use the resolved Team ID as the explicit `DEVELOPMENT_TEAM` value for team-signed Xcode builds. Preserve the repository's signing mode, scheme, configuration, destination, and other build flags. Use provisioning-update flags only when required by the established build flow.
5. Verify the exact final `.app`, archive, or exported artifact rather than relying on project settings or build success alone.

## Artifact Verification

Run checks appropriate to the artifact and record their outputs without leaking sensitive profile content:

- Verify signature integrity with `codesign --verify --deep --strict --verbose=2 <app>`.
- Inspect signature metadata with `codesign -dvvv <app>` and require `TeamIdentifier` to match the intended team for team-signed artifacts produced by this workflow.
- Extract signed entitlements with `codesign --display --entitlements - --xml <app>`. Require `com.apple.developer.team-identifier` to match the intended team when present.
- For profile-backed signing, validate the signed App ID against the profile's entitlement allowlist and actual Bundle ID. The entitlement is `application-identifier` on iOS-family platforms, `com.apple.application-identifier` on macOS, and both on Mac Catalyst.
- Treat the App ID prefix separately from Team ID: legacy prefixes can differ legitimately. Validate each keychain access group against the profile's authorized values or wildcard patterns, not a blanket Team ID prefix rule. Do not change an existing prefix to normalize it; that can break access to saved keychain data and requires a separate migration decision.
- Decode `embedded.mobileprovision`, or `Contents/embedded.provisionprofile` on macOS, when applicable. Cross-check its team, authorized certificate, App ID coverage, expiration, and device coverage when device installation is requested. A macOS app without restricted entitlements may not require a profile; do not invent one merely to satisfy this checklist.

Treat conflicting team evidence or unauthorized entitlements as a failed signing contract. Diagnose before rebuilding or changing Keychain state. A legitimate non-Team-ID App ID prefix is not a team mismatch. For simulator/ad-hoc or Apple-re-signed App Store artifacts, apply the corresponding artifact contract instead of claiming they carry the original developer signature.

## Primary References

Consult current Apple guidance when the artifact or signing behavior needs clarification:

- [Provisioning profiles and entitlement allowlists](https://developer.apple.com/documentation/technotes/tn3125-inside-code-signing-provisioning-profiles)
- [Code-signing certificates and signature verification](https://developer.apple.com/documentation/technotes/tn3161-inside-code-signing-certificates)
- [Managing multiple App ID prefixes](https://developer.apple.com/library/archive/technotes/tn2311/_index.html)

## Completion Report

Report these axes separately as applicable: build, signature integrity, Team ID, profile and entitlements, artifact creation, installation, launch, Developer ID, notarization, and App Store readiness. Do not infer installation or distribution readiness from a successful build.
