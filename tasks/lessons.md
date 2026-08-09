# Lessons

- Treat arbitrary upstream JSON values as untrusted shapes. Presence checks must
  not hash dict/list values, and compact status snapshots must validate any
  scalar before returning it rather than echoing URL, path, email, token, or
  secret-like content.
- Preserve semantic labels across composition boundaries. TymeWear
  `times_zone` is an elapsed-time axis, not a raw zone-label series. Channel
  filters must also filter the observed timeline so unrequested channels do not
  create empty sample rows.
- Prefer evidenced live integration field names over synthetic examples. Garmin
  health reports `is_connected` and `is_healthy`; these current booleans do not
  prove authentication or any historical recovery state.
- Validate composition inputs before creating any upstream coroutine, normalize
  capability envelopes once for both metadata and payload usability, and apply
  the same bounded JSON-safe scalar/name/unit policy to values and nested
  provenance. Optional capability gaps must not automatically downgrade the
  whole analysis.
- Apply the same semantic privacy checks to source-controlled dictionary keys
  and string values. Reject embedded absolute paths, bare storage hosts,
  emails, credentials, tokens, and UUID identity material, while preserving
  only explicitly contracted identifiers such as `activity_id`.
- Make public privacy allowlists structural, not name-only: UUID recognition is
  version-agnostic, location metadata accepts only documented metadata fields
  and shapes, and any runtime input constraint needed by MCP clients must also
  appear in the published JSON Schema.
