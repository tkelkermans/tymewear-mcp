# TymeWear Complete Analysis Contract Design

**Date:** 2026-08-09

## Decision

Add one compact activity-analysis tool that reports each upstream source as a
tagged capability, reconciles timestamps against the epoch, labels metrics and
provenance, and falls back to an in-memory FIT export for Garmin channels. Fix
processed-data window semantics and apply privacy-safe public projection.

## Problem

TymeWear reports algorithm success and summary physiology while processed and
strap endpoints may be gated or missing. Existing results mix nulls, empty
arrays and 404s, mislabel local clock time as UTC, expose personal/internal
metadata, and provide server-local export paths. The Garmin FIT attached to a
third-party activity is usable but not exposed as a safe series.

## Interfaces

### `tw_get_activity_analysis`

- Inputs: `activity_id`, `offset` (default 0), `limit` (default 500, max 1000),
  optional `channels`, and `include_location` (default false).
- Returns normalized identity/timestamps, summary physiology, zone totals,
  model quality, source capabilities, selected paginated samples and provenance.
- Source priority is per channel, not per response. Samples are aligned by
  integer elapsed second. Each channel selects processed data, then new
  processed data, then FIT, while null or absent values fall through. This
  allows processed VE to coexist with FIT HR, power or cadence. Pagination is
  applied after the merged elapsed-time timeline is built. Each channel reports
  its selected source, source unit, canonical unit, scale and coverage.
  Workout-zone detection remains a separate labeled summary source.
- A missing source is never inferred from an empty unrelated array.

### Tagged capability

Each source is one of `available`, `partial`, `not_applicable`, `not_computed`,
`sync_pending`, `unavailable`, or `permission_denied`, with a stable reason,
source and optional HTTP status. Raw upstream error text is not returned.

### Timestamp reconciliation

`unix_timestamp` is the authoritative instant when present. The result includes
UTC RFC3339, local RFC3339 with numeric offset, source timestamp, timezone label,
offset minutes and a consistency flag with delta seconds. For the August 9 ride
the expected values are `2026-08-09T10:31:35Z` and
`2026-08-09T12:31:35+02:00`; the source string conflict is reported.

### FIT fallback

Refactor the existing export FIT request into a byte-returning helper and decode
it in memory using Garmin's official Python SDK. Never return bytes, a signed
URL or a server path. Developer fields retain their declared field names and
units. Location is excluded by default. If the export endpoint returns JSON
with a signed URL instead of bytes, the URL must be HTTPS, use an explicit
TymeWear-owned host allowlist, reject embedded credentials and fragments, allow
at most one allowlisted redirect, and enforce compressed/decompressed size
limits before decode. No arbitrary URL is fetched.

## Existing-tool corrections

- Processed data accepts list and common dictionary wrappers.
- `window_start`/`window_end` filter elapsed-time values, not list indexes.
- Success and failure share the same availability envelope.
- Activity insights rename `min_max` to `model_input_bounds` and distinguish
  model fit from raw-channel completeness.
- Normal rides explicitly mark VT1/VT2 breakpoints `not_computed` rather than
  presenting empty strings as evidence.
- Integration health is an honest current snapshot and declares history,
  replay, cursor and backlog unavailable when the upstream endpoint omits them.

## Privacy

Public responses remove email, account/user UUID, device identifiers, signed or
callback URLs, S3 and temporary paths, and coordinates by default. Raw logs and
filesystem-writing export tools remain disabled in public mode. Location can be
requested only through an explicit analytic-tool opt-in.

## August 9 acceptance

- Activity `5ca66dc7-c21f-47c6-bd6d-cc7cea8c2b9e` reports the correct UTC/local
  timestamps and flags the two-hour source-label conflict.
- WZD summary remains available even when processed endpoints are 404.
- FIT fallback exposes Garmin HR/power/cadence and Tyme developer fields if they
  are in the file, without exposing its signed URL.
- Zone seconds plus uncategorized time match duration within two seconds.
- No email, home coordinate, callback URL, S3 path or server path is returned.

## Self-review

The MCP cannot unlock `raw_data_access`, reconstruct strap waveforms, or preserve
Garmin sync history that the upstream API does not provide. The contract makes
those limits machine-readable and uses the already authorized FIT export as the
best available channel fallback. No speculative POST, replay, or OAuth endpoint
is introduced.
