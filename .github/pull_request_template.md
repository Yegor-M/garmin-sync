## What
<!-- One sentence description of the change -->

## Why
<!-- The reason this was needed — a gap, a bug, a new endpoint, etc. -->

## Schema changes
<!-- List any new columns or tables. Note whether ALTER TABLE is safe or a rebuild is needed. -->
None

## Testing
- [ ] `sync.py --date <recent-date>` runs cleanly
- [ ] New fields appear in DuckDB with expected values
- [ ] Existing fields unaffected (spot-check a known date)
- [ ] `explore.py` output matches extraction logic (if adding a new endpoint)
