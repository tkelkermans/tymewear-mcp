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
