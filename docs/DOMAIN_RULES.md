# Domain rules

- `raw_mass_kg` is the physical сырьё mass.
- `active_mass_kg` is the active-substance mass; it is not interchangeable with raw mass.
- User-entered `т`, `кг`, `г` are normalized to kilograms. A number without a mass basis is ambiguous for planning and deficit calculations.
- `GOOD`, `REWORK` and `REJECTED` are derived from the current quality rules.
- Rejected batches are never selected by a plan. Rework is selected only when the tool explicitly allows it.
- Preview calculations do not alter inventory. Confirmation is explicit, authenticated, owned by the preview creator, transactional and idempotent.
