-- Re-sort the monitoring surveys into the eight напрями the monitoring office named in
-- August 2026 (their doc: «Напрями для сайта»), and replace the area choices in Directus.
--
-- Matching is by survey number, and sub-numbered questionnaires follow their base: 11/1…11/10
-- go wherever 11 goes. Anything the list does not name keeps `other` — today that is only
-- анкета №4 — so nothing disappears from the page while the office decides where it belongs.
--
--   docker run --rm -i --network dbnet -e PGPASSWORD="$DB_PASSWORD" -v "$PWD":/sql \
--     postgres:16-alpine psql -h knpu-university-postgres -U "$DB_USER" -d "$DB_DATABASE" \
--     -v ON_ERROR_STOP=1 -f /sql/resort-areas.sql

BEGIN;
UPDATE monitoring_surveys SET area = 'community-synergy' WHERE number IN ('15', '23', '31') OR number LIKE '15/%' OR number LIKE '23/%' OR number LIKE '31/%';
UPDATE monitoring_surveys SET area = 'educational-ecosystem' WHERE number IN ('1', '2', '3', '5', '11', '21', '22', '30') OR number LIKE '1/%' OR number LIKE '2/%' OR number LIKE '3/%' OR number LIKE '5/%' OR number LIKE '11/%' OR number LIKE '21/%' OR number LIKE '22/%' OR number LIKE '30/%';
UPDATE monitoring_surveys SET area = 'research-innovation' WHERE number IN ('14') OR number LIKE '14/%';
UPDATE monitoring_surveys SET area = 'international-partnership' WHERE number IN ('18/1', '18/2', '18/3');
UPDATE monitoring_surveys SET area = 'youth-policy' WHERE number IN ('8', '16', '20') OR number LIKE '8/%' OR number LIKE '16/%' OR number LIKE '20/%';
UPDATE monitoring_surveys SET area = 'human-capital' WHERE number IN ('6', '7', '9', '10', '17', '19', '24', '25', '26', '32', '41') OR number LIKE '6/%' OR number LIKE '7/%' OR number LIKE '9/%' OR number LIKE '10/%' OR number LIKE '17/%' OR number LIKE '19/%' OR number LIKE '24/%' OR number LIKE '25/%' OR number LIKE '26/%' OR number LIKE '32/%' OR number LIKE '41/%';
UPDATE monitoring_surveys SET area = 'targeted-surveys' WHERE number IN ('12', '27', '28', '29', '33', '34', '35', '36', '37', '38', '39', '40', '42', '43') OR number LIKE '12/%' OR number LIKE '27/%' OR number LIKE '28/%' OR number LIKE '29/%' OR number LIKE '33/%' OR number LIKE '34/%' OR number LIKE '35/%' OR number LIKE '36/%' OR number LIKE '37/%' OR number LIKE '38/%' OR number LIKE '39/%' OR number LIKE '40/%' OR number LIKE '42/%' OR number LIKE '43/%';

-- Directus dropdown: same list, same order.
UPDATE directus_fields
SET options = jsonb_set(options::jsonb, '{choices}', '[
      {"text": "Синергія університету з громадами та місцевою владою", "value": "community-synergy"},
      {"text": "Освітня екосистема", "value": "educational-ecosystem"},
      {"text": "Наука та інновації", "value": "research-innovation"},
      {"text": "Міжнародне партнерство", "value": "international-partnership"},
      {"text": "Молодіжна політика та студентські ініціативи", "value": "youth-policy"},
      {"text": "Людський капітал і управлінська культура", "value": "human-capital"},
      {"text": "Інфраструктура, ресурси і безпека", "value": "infrastructure-safety"},
      {"text": "Цільові опитування", "value": "targeted-surveys"},
      {"text": "Інші дослідження", "value": "other"}
    ]'::jsonb),
    display_options = jsonb_set(display_options::jsonb, '{choices}', '[
      {"text": "Синергія університету з громадами та місцевою владою", "value": "community-synergy"},
      {"text": "Освітня екосистема", "value": "educational-ecosystem"},
      {"text": "Наука та інновації", "value": "research-innovation"},
      {"text": "Міжнародне партнерство", "value": "international-partnership"},
      {"text": "Молодіжна політика та студентські ініціативи", "value": "youth-policy"},
      {"text": "Людський капітал і управлінська культура", "value": "human-capital"},
      {"text": "Інфраструктура, ресурси і безпека", "value": "infrastructure-safety"},
      {"text": "Цільові опитування", "value": "targeted-surveys"},
      {"text": "Інші дослідження", "value": "other"}
    ]'::jsonb)
WHERE collection = 'monitoring_surveys' AND field = 'area';

SELECT area, count(*) FROM monitoring_surveys GROUP BY area ORDER BY count DESC;
COMMIT;
