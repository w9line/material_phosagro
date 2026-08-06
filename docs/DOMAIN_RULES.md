# Domain rules

- `raw_mass_kg` is the physical сырьё mass.
- `active_mass_kg` is the active-substance mass; it is not interchangeable with raw mass.
- User-entered `т`, `кг`, `г` are normalized to kilograms. A number without a mass basis is ambiguous for planning and deficit calculations.
- `GOOD`, `REWORK` and `REJECTED` are derived from the current quality rules.
- Rejected batches are never selected by a plan. Rework is selected only when the tool explicitly allows it.
- Preview calculations do not alter inventory. Confirmation is explicit, authenticated, owned by the preview creator, transactional and idempotent.

## Классификация и активное вещество

На вход партии приходят `batch_id`, `material_type`, `raw_mass_kg`, `concentration_percent` и `arrival_date`; поставщик, склад, сертификат и заметки необязательны. Остаток сырья (`remaining_raw_mass_kg`) по умолчанию равен исходной массе.

Для каждого материала хранится правило с двумя порогами:

- `GOOD`: концентрация `>= good_threshold_percent`;
- `REWORK`: концентрация между порогом доработки и хорошей партии;
- `REJECTED`: концентрация ниже `rework_threshold_percent`.

Теоретическое активное вещество считается как `raw_mass_kg × concentration_percent / 100`. Доступное активное вещество считается от текущего остатка: `remaining_raw_mass_kg × concentration_percent / 100 × recovery_factor`. Поэтому у GOOD по умолчанию коэффициент восстановления 1.0, у REWORK — 0.9, у REJECTED — 0.

Раньше список был жёстко ограничен `A/B/C`, включая генератор. Сейчас в стартовом реестре есть `A/B/C/D/E`, а новый материал можно добавить вручную, импортом или через настройку правила: код должен начинаться с латинской буквы и содержать до 16 безопасных символов. Для нового кода создаётся правило по умолчанию; его пороги затем можно изменить.
