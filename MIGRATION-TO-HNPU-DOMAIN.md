# Переїзд нового сайту на hnpu.edu.ua

Новий сайт живе на сервері **A** (`165.232.84.116`, домени `hnpu.dev42hub.uk` /
`hnpu-admin.dev42hub.uk` за Cloudflare). Треба перенести його **без втрати даних** на сервер **B**
(`193.105.7.20`, Hestia) і віддати йому домен `hnpu.edu.ua`, а старий сайт із сервера **C**
(`193.105.7.18`, nginx + Drupal 7) лишити робочим на `old.hnpu.edu.ua`.

## Що вже відомо (перевірено 23.08.2026)

| Що | Значення |
|---|---|
| `hnpu.edu.ua` A | `193.105.7.18` (сервер C), TTL 14400 |
| `www.hnpu.edu.ua` | CNAME → `hnpu.edu.ua` |
| `old.hnpu.edu.ua` A | `193.105.7.18` — **запис уже є**, але vhost і сертифіката на C немає (HTTPS падає) |
| NS | `ns.hnpu.edu.ua` = `193.105.7.20` (сервер B, Hestia — первинний), `ns3.therecom.net` (вторинний, у синхроні) |
| MX | Google Workspace (`aspmx.l.google.com` та ін.) — **не чіпати** |
| Пастка | `smc`, `journals`, `ftp` — CNAME на `hnpu.edu.ua`; після перемикання поїдуть на новий сервер |
| Інші піддомени | `lms` → `.19`, `dspace`/`library`/`catalog` → `.21`, `mail`/`webmail` → `.20` — не чіпаємо |
| Сервер C | nginx, Drupal 7, сертифікат Let's Encrypt на `hnpu.edu.ua` |
| Сервер B | Hestia (панель `:31121`, SSH `:10163`, користувач `hnpu`), веб-домен `hnpu.edu.ua` уже заведено |

Стек, який переїжджає:

- `knpu-university-be` — Directus 11.17.4 (контейнер `knpu-university-directus`), том `uploads`,
  мережі `webnet` + `dbnet`;
- **Postgres** — на сервері A це *спільний* контейнер з іншим проєктом; на B піднімаємо власний;
- `knpu-university-fe` — Nuxt (контейнер `knpu-university-fe`), мережа `webnet`;
- попереду на A стоїть Caddy; на B цю роль бере nginx від Hestia.

---

## Стан на 24.08.2026

| Етап | Стан |
|---|---|
| 0. Передумови (диск, sudo) | зроблено |
| 1. Сервер B: своп, Docker, репи, Postgres, шаблони nginx | зроблено |
| 1.5 Сертифікат `admin.hnpu.edu.ua` | зроблено, force-SSL увімкнено |
| 2. Перенос даних (17 ГБ файлів + дамп), Directus і фронт на B | зроблено, `admin.hnpu.edu.ua` віддає 200 |
| 3. `old.hnpu.edu.ua` на сервері C | **чекає адміністратора C — блокує етап 7** |
| 4. DNS: піддомени відв'язані, TTL | піддомени зроблено; TTL apex лишається довести до 300 |
| 5. Переписані 610 посилань на `old.hnpu.edu.ua` | зроблено, у `origin/dev` |
| 6. Фінальна синхронізація | попереду, у день переїзду |
| 7. Перемикання | попереду |
| 10. Бекап бази в крон на B | зроблено достроково |

## Етап 0. Передумови (закриті 23.08.2026)

Розвідка 23.08.2026 знайшла на сервері B (`hosting.hnpu.edu.ua`, Debian 12, 4 vCPU, 7.8 ГБ RAM)
дві перешкоди — **обидві зняті адміністратором**:

1. **Диск** був 9.7 ГБ при потребі 40–60 ГБ (том `uploads` Directus сам по собі ~15 ГБ, образ
   фронту з шарами складання ще 4–6 ГБ, база ~0.1–1 ГБ, образи 1 ГБ, своп 4 ГБ) — **ресайзнуто**.
2. **Права**: користувач `hnpu` не мав `sudo`, тож не міг ні поставити Docker, ні покласти шаблон
   nginx, ні випустити сертифікат — **`sudo` видано**.

Тому переїзд починається з етапу 1. Спершу — контрольні заміри на B:

```bash
ssh -p 10163 root@193.105.7.20

df -h; lsblk                                  # має бути ≥ 40 ГБ вільних під / та /var/lib/docker
free -h                                       # своп: якщо 0 — етап 1.1
grep -E 'WEB_SYSTEM|PROXY_SYSTEM|WEB_PORT|WEB_SSL_PORT' /usr/local/hestia/conf/hestia.conf
v-list-web-domains hnpu                       # має бути hnpu.edu.ua
v-list-dns-domains hnpu
docker --version
```

`WEB_SYSTEM` / `PROXY_SYSTEM` визначають, куди лягає шаблон nginx (етап 1.5). Розбиратися вручну
не треба — `install-templates.sh` читає `hestia.conf` сам; але подивитися варто, щоб знати, чого
чекати: `PROXY_SYSTEM=nginx` — nginx проксі перед apache, `WEB_SYSTEM=nginx` без проксі — nginx
єдиний веб-сервер.

Якщо диск виявиться меншим, ніж домовлялися, — зупинитися тут: том `uploads` не влізе, а
складання фронту впаде на середині й лишить по собі мертві шари.

## Етап 1. Підготувати сервер B

### 1.1 Своп і Docker

Своп потрібен навіть при 7.8 ГБ RAM: складання фронту бере ~3 ГБ понад те, що вже тримають
Directus, Postgres і сам Hestia.

```bash
swapon --show                                  # якщо порожньо — робимо
fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab

curl -fsSL https://get.docker.com | sh
usermod -aG docker hnpu                        # щоб не ходити під root щоразу
docker network create webnet
docker network create dbnet
```

`webnet` і `dbnet` — зовнішні мережі, на які посилаються всі compose-файли; без них
`docker compose up` одразу впаде.

### 1.2 Каталоги й код

```bash
cd ~
git clone https://github.com/screamodev/knpu-university-be.git
git clone https://github.com/screamodev/knpu-university-fe.git
cd ~/knpu-university-be && git checkout dev
cd ~/knpu-university-fe && git checkout dev
```

Приватні репозиторії — знадобиться deploy key або токен.

Усе, що потрібно саме для сервера B, уже лежить у гілці `dev` (якщо клон робився раніше —
`git pull`):

| Файл | Що це |
|---|---|
| `knpu-university-be/docker-compose.db.yml` | власна Postgres 16 на `dbnet`, том `pgdata` |
| `knpu-university-be/docker-compose.host.yml` | Directus на `127.0.0.1:8055` |
| `knpu-university-fe/docker-compose.host.yml` | Nuxt на `127.0.0.1:3000` |
| `knpu-university-be/deploy/hestia/dockerapp.{tpl,stpl}` | vhost сайту (проксі на 3000) |
| `knpu-university-be/deploy/hestia/dockeradmin.{tpl,stpl}` | vhost адмінки (проксі на 8055) |
| `knpu-university-be/deploy/hestia/install-templates.sh` | кладе шаблони куди треба й вішає на домени |

### 1.3 Власна Postgres

На A база живе в чужому контейнері (спільному з іншим проєктом); на B піднімаємо свою —
`docker-compose.db.yml`. Ім'я ролі, бази й пароль беруться з `.env`, тобто з тих самих, що на A,
і `.env` через це міняти не доводиться. Запускати після того, як `.env` опиниться на місці
(етап 2.3):

```bash
cd ~/knpu-university-be
set -a; . ./.env; set +a
docker compose -f docker-compose.db.yml up -d
docker compose -f docker-compose.db.yml ps      # має бути healthy
```

Дані живуть у томі `knpu-university-be_pgdata`. `docker compose down -v` на цьому стеку не
запускати ніколи — `-v` зносить том разом із базою.

### 1.4 Публікація портів для nginx

Робочі compose-файли портів не відкривають (на A їх бачив Caddy зсередини мережі `webnet`). На B
nginx працює на хості, тож порти прокидаємо **тільки на loopback** — це роблять оверлеї
`docker-compose.host.yml` в обох репозиторіях. Далі всі команди на B запускати з обома файлами:

```bash
docker compose -f docker-compose.prod.yml -f docker-compose.host.yml up -d
```

Забути другий `-f` = отримати від nginx `502`, бо порт не опублікований. Забути його в `down` /
`ps` — теж плутанина: compose вважатиме конфігурацію іншою.

### 1.5 Домен адмінки й шаблони nginx

```bash
v-add-web-domain hnpu admin.hnpu.edu.ua
v-add-dns-record hnpu hnpu.edu.ua admin A 193.105.7.20
v-add-web-domain-alias hnpu hnpu.edu.ua www.hnpu.edu.ua
```

Далі — шаблони. Скрипт сам читає `hestia.conf` і робить решту:

```bash
bash ~/knpu-university-be/deploy/hestia/install-templates.sh
```

Що він вирішує за тебе:

- **куди класти** — `data/templates/web/nginx/` при `PROXY_SYSTEM=nginx` (nginx проксі перед
  apache) або `data/templates/web/nginx/php-fpm/` при `WEB_SYSTEM=nginx`, з заміною
  `%proxy_port%` → `%web_port%` у другому випадку;
- **`http2`** — окремою директивою для nginx ≥ 1.25.1, інакше на рядку `listen … ssl http2;`;
- **`$connection_upgrade`** — додає `map` у `/etc/nginx/conf.d/`, якщо його ще ніде немає
  (без нього websocket'и Directus і live preview не працюють);
- **призначення** — `v-change-web-domain-proxy-tpl` або `v-change-web-domain-tpl` на
  `hnpu.edu.ua` (`dockerapp`) і `admin.hnpu.edu.ua` (`dockeradmin`), потім `nginx -t` і рестарт.

Прапорці: `--user`, `--site`, `--admin` — якщо імена інші; `--no-assign` — тільки покласти файли.
Наявні шаблони з такими іменами скрипт перед перезаписом копіює поруч із суфіксом `.bak.<дата>`.

Дві речі шаблони навмисно не роблять самі:

- **не редіректять на HTTPS** — поки сертифіката немає, vhost'а на 443 з цим іменем теж немає,
  відповідає дефолтний сервер, і `v-add-letsencrypt-domain` падає з `Redirect loop detected`;
- **не обробляють ACME** — Hestia не кладе токен на диск, а пише
  `conf/web/<домен>/nginx.conf_letsencrypt` з regex-локацією, яка віддає відповідь інлайн;
  її підтягує `include … nginx.conf_*` наприкінці шаблону. Власна
  `location ^~ /.well-known/acme-challenge/` перебиває цей regex (префікс із `^~` сильніший) —
  і випуск сертифіката ламається.

Порядок такий: шаблони → сертифікат → примусовий HTTPS:

```bash
v-add-letsencrypt-domain  hnpu admin.hnpu.edu.ua
v-add-web-domain-ssl-force hnpu admin.hnpu.edu.ua
```

`v-add-web-domain-ssl-force` пише `nginx.forcessl.conf`, який шаблон уже підключає. Продовження
сертифіката з увімкненим редіректом проходить: ACME йде за 301 на 443, а `nginx.conf_letsencrypt`
підключений в обох половинах шаблону.

Перевірка після встановлення (контейнерів ще немає, тож 502 — очікуваний результат; головне, що
відповідає саме наш vhost):

```bash
nginx -T | grep -A5 'server_name .*hnpu.edu.ua' | head -40
curl -sI http://hnpu.edu.ua -H 'Host: hnpu.edu.ua' --resolve hnpu.edu.ua:80:193.105.7.20 | head -3
```

## Етап 2. Перенести дані (перший, «тренувальний» прогін)

### 2.1 Дамп бази на сервері A

База маленька (11 МБ у `-Fc`), її переносимо файлом:

```bash
ssh root@165.232.84.116
cd ~/knpu-university-be
set -a; . ./.env; set +a

docker run --rm --network dbnet -e PGPASSWORD="$DB_PASSWORD" -v "$PWD":/backup postgres:16-alpine \
  pg_dump -h "$DB_HOST" -p "${DB_PORT:-5432}" -U "$DB_USER" -d "$DB_DATABASE" \
  -Fc -f /backup/knpu-move.dump && ls -lh knpu-move.dump
```

Том `uploads` (17 ГБ, 22 494 файли) **не пакуємо**: на A вільно всього 18 ГБ, а gzip на одному
vCPU тягнувся б годинами. Ллємо теку тому напряму `rsync`'ом — без місця під архів, без
розпакування на тому боці й із докачкою після обриву.

### 2.2 Передати на B

Root по SSH на B закритий (`permitrootlogin no`), тож ходимо під `hnpu`. Ключ з A — у
`/home/hnpu/.ssh/authorized_keys` на B (`ssh-keygen -t ed25519` на A, якщо ключа ще немає).

```bash
# дамп і обидва .env
cd ~/knpu-university-be && cp ~/knpu-university-fe/.env /tmp/fe.env
rsync -avP -e 'ssh -p 10163' knpu-move.dump .env /tmp/fe.env hnpu@193.105.7.20:/home/hnpu/transfer/

# файли Directus — довго, тримати у screen
screen -S move -d -m rsync -avP -e 'ssh -p 10163' \
  /var/lib/docker/volumes/knpu-university-be_uploads/_data/ \
  hnpu@193.105.7.20:/home/hnpu/transfer/uploads/
```

Слеші в кінці обох шляхів обов'язкові. Прогрес — `screen -r move`, назад — `Ctrl+A`, `D`.
Обірветься — повторити той самий рядок, rsync дошле різницю. Перевірка після завершення:

```bash
rsync -ain -e 'ssh -p 10163' /var/lib/docker/volumes/knpu-university-be_uploads/_data/ \
  hnpu@193.105.7.20:/home/hnpu/transfer/uploads/ | head
```

Порожній вивід = все на місці (рядки `<f` — ще не долиті файли; `-n` нічого не пише).

На B перекласти в том. `/home` і `/var/lib/docker` — один розділ, тож `mv` це перейменування,
без другої копії. Власник файлів на A — `1000:1000` (користувач `node` у контейнері Directus):

```bash
docker volume create knpu-university-be_uploads
mv /home/hnpu/transfer/uploads/* /var/lib/docker/volumes/knpu-university-be_uploads/_data/
chown -R 1000:1000 /var/lib/docker/volumes/knpu-university-be_uploads/_data
du -sh /var/lib/docker/volumes/knpu-university-be_uploads/_data      # 17G
```

`.env` тягнемо з A, щоб **не змінилися `KEY` і `SECRET`** — інакше Directus не прочитає наявні
сесії й токени.

### 2.3 Розгорнути на B

`.env` кладемо в клони з етапу 1.2 — вони вже на місці.

```bash
ssh -p 10163 root@193.105.7.20
cp /root/transfer/.env    ~/knpu-university-be/.env
cp /root/transfer/fe.env  ~/knpu-university-fe/.env

cd ~/knpu-university-be
# правки під нове оточення
sed -i 's#^DB_HOST=.*#DB_HOST=knpu-university-postgres#' .env
sed -i 's#^PUBLIC_URL=.*#PUBLIC_URL=https://admin.hnpu.edu.ua#' .env
sed -i 's#^CORS_ORIGIN=.*#CORS_ORIGIN=https://hnpu.edu.ua,https://www.hnpu.edu.ua#' .env

set -a; . ./.env; set +a
docker compose -f docker-compose.db.yml up -d

# дочекатися, поки база підніметься, — pg_restore у порожнечу впаде
until [ "$(docker inspect -f '{{.State.Health.Status}}' knpu-university-postgres)" = healthy ]; do
  sleep 3; done

# відновити базу
docker run --rm -i --network dbnet -e PGPASSWORD="$DB_PASSWORD" \
  -v /root/transfer:/backup postgres:16-alpine \
  pg_restore -h knpu-university-postgres -U "$DB_USER" -d "$DB_DATABASE" \
  --clean --if-exists --no-owner --no-privileges /backup/knpu-move.dump

# відновити файли Directus
docker volume create knpu-university-be_uploads
docker run --rm -v knpu-university-be_uploads:/uploads -v /root/transfer:/backup alpine \
  tar xzf /backup/knpu-uploads-move.tar.gz -C /uploads

docker compose -f docker-compose.prod.yml -f docker-compose.host.yml up -d
curl -s localhost:8055/server/health          # {"status":"ok"}
```

Directus на старті проганяє власні міграції — перший запуск після відновлення бази довший за
звичайний, це нормально.

Фронт (збірка з новою адресою адмінки — вона запікається в бандл):

```bash
cd ~/knpu-university-fe
sed -i 's#^NUXT_PUBLIC_DIRECTUS_URL=.*#NUXT_PUBLIC_DIRECTUS_URL=https://admin.hnpu.edu.ua#' .env
docker compose -f docker-compose.prod.yml -f docker-compose.host.yml build app
docker compose -f docker-compose.prod.yml -f docker-compose.host.yml up -d app
curl -sI localhost:3000 | head -3
```

Складання фронту з'їдає ~3 ГБ RAM — своп із етапу 1.1 має бути вже увімкнений.

### 2.4 Перевірити до перемикання DNS

На своєму комп'ютері додай у `/etc/hosts`:

```
193.105.7.20 hnpu.edu.ua www.hnpu.edu.ua admin.hnpu.edu.ua
```

і пройди сайт очима: головна, новини, пошук, PDF-документи, адмінка. Потім рядок прибрати.

## Етап 3. Старий сайт на old.hnpu.edu.ua (сервер C)

**Блокує перемикання.** Після етапу 7 apex віддамо новому сайту, і старий стане недосяжним ні за
якою адресою — а на нього ведуть 610 переписаних посилань (етап 5), стара пошукова видача й
посилання в зовнішніх реєстрах. DNS-запис `old` на `193.105.7.18` уже є, vhost і сертифіката
немає.

Доступу до сервера C у нас немає (24.08.2026), і ззовні він не відповідає ні на `curl`, ні на
`openssl s_client` — фільтрує все, що не браузер. Тому це запит до адміністратора C:

> На сервері `193.105.7.18`:
> 1. створити vhost `old.hnpu.edu.ua` — копію наявного конфігу `hnpu.edu.ua` зі зміненим
>    `server_name`;
> 2. випустити сертифікат: `certbot --nginx -d old.hnpu.edu.ua`;
> 3. у `settings.php` Drupal: `$base_url = 'https://old.hnpu.edu.ua';` і
>    `$settings['trusted_host_patterns'] = ['^old\.hnpu\.edu\.ua$', '^hnpu\.edu\.ua$'];`
>
> Vhost `hnpu.edu.ua` поки лишити робочим — він обслуговує домен до перемикання.

Якщо доступу так і не дадуть, є обхід **без сервера C**: перевести `old.hnpu.edu.ua` на B і
проксувати звідти на `193.105.7.18` з `Host: hnpu.edu.ua`, сертифікат брати на B. Мінус — Drupal
може редіректити на канонічний хост і зациклитися; лікується `sub_filter`, який переписує
`hnpu.edu.ua` на `old.hnpu.edu.ua` у HTML. Це варто протестувати **до** перемикання, поки apex ще
показує на C.

Перевірка (з будь-якої машини, коли зроблено): `curl -sI https://old.hnpu.edu.ua/uk | head -3`
→ 200 і валідний сертифікат.

## Етап 4. Підготовка DNS (за добу до переїзду)

Виконано 24.08.2026. Зона на сервері B, тож усе через `v-*` (або панель на `:31121`).

1. **Відв'язати піддомени, які були CNAME на apex** — інакше вони поїдуть за новим сайтом.
   ID видно у `v-list-dns-records hnpu hnpu.edu.ua`; CNAME і A з тим самим іменем співіснувати
   не можуть, тому видалення й додавання йдуть одним ланцюжком:

```bash
v-delete-dns-record hnpu hnpu.edu.ua <ID_smc>      && v-add-dns-record hnpu hnpu.edu.ua smc      A 193.105.7.18
v-delete-dns-record hnpu hnpu.edu.ua <ID_journals> && v-add-dns-record hnpu hnpu.edu.ua journals A 193.105.7.18
v-delete-dns-record hnpu hnpu.edu.ua <ID_ftp>      && v-add-dns-record hnpu hnpu.edu.ua ftp      A 193.105.7.18
```

`www` лишається CNAME на apex — він має їхати за новим сайтом. У зоні знайшлося **два однакові
записи `www`** (ID 10 і 66) — дубль видалено, лишився один.

2. **Знизити TTL** — мінімум за 4 години до перемикання (стільки живе старий кеш 14400).
   Команди `v-change-dns-record-ttl` у цій збірці Hestia **немає**, є тільки на всю зону:

```bash
v-change-dns-domain-ttl hnpu hnpu.edu.ua 300
v-list-dns-records hnpu hnpu.edu.ua | awk 'NR==1 || $NF!=300 {print}'   # що не піддалося
```

Перевір другою командою: у нас частина записів (зокрема apex A) з першого разу лишилася на
14400. Якщо повтор не допомагає — перевидати запис із явним TTL останнім аргументом:

```bash
v-delete-dns-record hnpu hnpu.edu.ua <ID_apex> && v-add-dns-record hnpu hnpu.edu.ua '@' A 193.105.7.18 '' '' 300
```

3. **Вторинний NS відстає.** `ns3.therecom.net` тягне зону за `refresh` із SOA — 7200 с, тобто до
   двох годин. Поки він віддає старий apex, частина резолверів ітиме на старий сервер незалежно
   від TTL. Перед етапом 7 серіали мають зійтися:

```bash
dig +short hnpu.edu.ua SOA @193.105.7.20; dig +short hnpu.edu.ua SOA @ns3.therecom.net
```

4. Переконатися, що MX (Google), SPF/DKIM/DMARC TXT і записи `lms`, `dspace`, `library`,
   `catalog`, `mail`, `webmail`, `ns` лишилися недоторканими.

```bash
v-list-dns-records hnpu hnpu.edu.ua | less
```

## Етап 5. Код: посилання на старий сайт

Зараз у контенті й у коді **610 посилань** на `hnpu.edu.ua` — після переїзду вони вестимуть на
новий сайт і дадуть 404. Один скрипт переписує їх на `old.hnpu.edu.ua`; пошту
(`@hnpu.edu.ua`), `sites.google.com/hnpu.edu.ua/...` і піддомени (`smc.`, `lms.`, `dspace.`,
`journals.`, `library.`, `catalog.`) він не чіпає.

Виконано 24.08.2026 (коміт `content: point legacy links at old.hnpu.edu.ua` у `dev`). На робочій
машині:

```bash
cd knpu-university-be/migration/cleanup
python3 rewrite_legacy_links.py --dry-run     # 610 посилань у 258 файлах
python3 rewrite_legacy_links.py
```

Після цього сайт посилається на `old.hnpu.edu.ua`, якого ще немає — тому етап 3 має бути
закритий **до** перемикання, інакше всі 610 посилань ведуть у нікуди.

Під зміну потрапляють і константи `app/utils/externalSites.ts` (`LEGACY_SITE_URL`,
`ADMISSIONS_LEGACY_URL`, `WINTER_ADMISSIONS_LEGACY_URL`), і списки посилань у
`science/library.vue`, `student/sports.vue`, `university/wartime.vue`.

Перевірити, що не лишилося прямих посилань на апекс:

```bash
grep -rn "//hnpu\.edu\.ua\|//www\.hnpu\.edu\.ua" knpu-university-fe/app | grep -v sites.google.com
```

Далі — коміт, пуш, на B `git pull` і перезбірка фронту (етап 2.3).

Якщо переїзд відкладеться, скрипт має зворотний хід: `python3 rewrite_legacy_links.py --revert`.

> Старі адреси `/uk/**` і `/sites/default/files/**`, які лишилися в реєстрах і пошуковій видачі,
> новий сайт обробляє сам: `server/middleware/legacy-redirects.ts` віддає 301 за таблицею
> `legacy_redirects` (вона їде разом із дампом). Перевірити після переїзду — етап 8.

## Етап 6. Фінальна синхронізація (у день переїзду)

1. Попередити редакторів: з цього моменту **не редагувати** контент на старій адмінці.
2. Повторити етап 2.1–2.3. Другий прогін швидкий: `rsync` дошле лише те, що змінилося з
   першого разу (нові файли редакторів), а `pg_restore --clean --if-exists` перезаписує вміст,
   тож повторний прогін безпечний. Файли цього разу ллються одразу в том — на B:

```bash
# на A
rsync -avP -e 'ssh -p 10163' /var/lib/docker/volumes/knpu-university-be_uploads/_data/ \
  hnpu@193.105.7.20:/home/hnpu/transfer/uploads/
# на B
mv /home/hnpu/transfer/uploads/* /var/lib/docker/volumes/knpu-university-be_uploads/_data/ 2>/dev/null
chown -R 1000:1000 /var/lib/docker/volumes/knpu-university-be_uploads/_data
```
3. Перезапустити Directus і фронт на B, ще раз пройтися по сайту через `/etc/hosts`.

## Етап 7. Перемикання

```bash
# Hestia на B
v-change-dns-record hnpu hnpu.edu.ua <ID_A_запису> ... 193.105.7.20
# або в панелі: DNS → hnpu.edu.ua → запис @ → IP 193.105.7.20
```

Далі:

```bash
# дочекатися, поки розійдеться (TTL 300)
dig +short @1.1.1.1 hnpu.edu.ua
dig +short @ns3.therecom.net hnpu.edu.ua

# сертифікат на апекс — тільки коли DNS уже показує на B, інакше ACME не достукається
v-add-letsencrypt-domain   hnpu hnpu.edu.ua www.hnpu.edu.ua
v-add-web-domain-ssl-force hnpu hnpu.edu.ua
```

Сертифікат для `admin.hnpu.edu.ua` береться раніше (етап 1.5) — його A-запис не залежить від
перемикання.

Cloudflare тут ні до чого — зона обслуговується Hestia, сертифікати від Let's Encrypt
випускаються прямо на B.

## Етап 8. Перевірка після перемикання

```bash
for u in / /education/programs /education/staff-rating /student/sports \
         /university/structure/mathematics-informatics/history /news; do
  printf '%-52s ' "$u"; curl -s -o /dev/null -w '%{http_code}\n' "https://hnpu.edu.ua$u"
done

curl -sI https://www.hnpu.edu.ua | head -3          # редірект або 200
curl -sI https://admin.hnpu.edu.ua/server/health    # адмінка
curl -s -o /dev/null -D - -H 'Accept-Language: en-US,en' https://hnpu.edu.ua/ | head -3   # без /en

# 301 зі старих адрес
curl -sI "https://hnpu.edu.ua/uk/specializovana-vchena-rada-d-64-053-04" | head -3

# старий сайт живий
curl -sI https://old.hnpu.edu.ua/uk | head -3

# піддомени, які лишилися на C і .19/.21
for h in smc journals lms dspace library catalog; do
  printf '%-12s ' "$h"; dig +short "$h.hnpu.edu.ua" | tail -1
done

# пошта не зачеплена
dig +short hnpu.edu.ua MX
```

Очима: файли-PDF відкриваються (адреси `/assets/**` тепер ідуть на `admin.hnpu.edu.ua`),
логін в адмінку, пошук по сайту, галерея ФМІПО, кнопка «Старий сайт» веде на `old.hnpu.edu.ua`.

## Етап 9. Відкат

Якщо після перемикання щось критично не так:

```bash
v-change-dns-record hnpu hnpu.edu.ua <ID_A_запису> ... 193.105.7.18
```

Домен повернеться на старий сайт за 5 хвилин (TTL 300). Сервер A і `hnpu.dev42hub.uk` тримаємо
живими щонайменше два тижні — це і запасний майданчик, і джерело даних, якщо доведеться
перезаливати.

## Етап 10. Після переїзду

- підняти TTL назад до 3600–14400;
- на C прибрати vhost `hnpu.edu.ua` (лишити тільки `old.`), щоб не було двох сайтів з однією
  назвою;
- `hnpu.dev42hub.uk` лишити як стенд або вимкнути — за домовленістю;
- бекап бази на B — уже в крон-розкладі (`/root/backup-directus.sh`, щоночі о 03:17,
  дампи в `/root/backups`, зберігаються два тижні; том `uploads` не дампиться — 17 ГБ і
  змінюється рідко, його страхує сервер A);
- переглянути статичні токени Directus: після переїзду перевипустити ті, власники яких не
  можуть пояснити, навіщо вони.

---

### Дрібниці, на яких легко спіткнутися

1. **`KEY`/`SECRET` Directus** мають переїхати без змін — інакше злетять сесії й статичні токени.
2. **`NUXT_PUBLIC_DIRECTUS_URL` запікається у бандл** — після зміни адреси адмінки фронт треба
   **перезібрати**, а не просто перезапустити.
3. **`smc` і `journals`** — CNAME на apex. Не прибити їх до `193.105.7.18` = покласти сайт центру
   якості й журнали.
4. **`ftp`** — теж CNAME на apex; якщо ним користуються для старого сайту, пін на C обов'язковий.
5. **Postgres на A спільний з іншим проєктом** — на B піднімаємо власний контейнер, дамп
   відновлюємо в нього; імена ролі й бази лишаємо ті самі, щоб `.env` не міняти.
6. **Збірка фронту** потребує ~3 ГБ RAM — без свопу на 1–2 ГБ машині вона впаде з OOM.
7. **Пошта живе на Google** — MX/SPF/DKIM у зоні не чіпати; переїзд сайту на них не впливає.
8. **`-f docker-compose.host.yml` у кожній команді** — без нього порт на loopback не
   публікується і nginx віддає 502.
9. **ACME обробляє сама Hestia** через `nginx.conf_letsencrypt`. У шаблоні має лишатися
   `include %home%/%user%/conf/web/%domain%/nginx.conf_*;` — і жодної своєї локації на
   `/.well-known/acme-challenge/`, інакше вона перебиває рідну regex-локацію.
10. **CORS звіряє схему, не лише хост.** Поки apex без сертифіката, сайт відкривається як
    `http://hnpu.edu.ua` — і всі клієнтські запити до Directus ріже CORS, бо в `CORS_ORIGIN`
    записано `https://`. Це нормально до етапу 7; перевірити можна так:
    `curl -sI -H 'Origin: https://hnpu.edu.ua' https://admin.hnpu.edu.ua/items/articles?limit=1`.
11. **Редірект на HTTPS вмикається після сертифіката**, і не в шаблоні, а
    `v-add-web-domain-ssl-force`. Жорсткий `return 301` у `.tpl` = `Redirect loop detected`
    від Let's Encrypt, бо на 443 ще нікого немає.

---

## Додаток. Запит до адміністратора сервера B (закритий 23.08.2026)

Лишається тут як історія й як чекліст, якщо доведеться повторювати на іншій машині.

1. **Диск**: розширити до 60 ГБ (або підмонтувати окремий том під `/var/lib/docker` і дані
   сайту). — **зроблено.**
2. **Права**: `sudo` для користувача `hnpu`. — **зроблено.** Далі все з етапів 1–10 робиться
   самостійно: Docker (`curl -fsSL https://get.docker.com | sh`, `usermod -aG docker hnpu`),
   своп, шаблони nginx (`deploy/hestia/install-templates.sh`), домен адмінки, Let's Encrypt.
3. **DNS**: зона `hnpu.edu.ua` обслуговується цим же сервером — етапи 4 і 7 робляться в панелі
   Hestia або через `v-*-dns-record`.

### Варіант «без Docker», якщо root не дадуть

Не знадобився — `sudo` видали. Лишаю опис на випадок іншої машини; робочий, але помітно
незручніший:

- Node 22 і pnpm — під користувача (`fnm`/`nvm` у `~/.local`), фронт запускати як
  `node .output/server/index.mjs` на порту > 1024;
- Directus — теж npm-пакет під тим самим Node, з тим же `.env`;
- Postgres — або створити базу в панелі Hestia (якщо там увімкнено PostgreSQL), або попросити
  адміністратора створити роль і базу;
- тримати процеси живими — `systemd --user` (потрібен `loginctl enable-linger`) або крон
  `@reboot`;
- проксі з nginx на ці порти **все одно робить адміністратор** — без шаблону Hestia домен
  віддаватиме статику з `~/web/hnpu.edu.ua/public_html`.

Диск у цьому варіанті потрібен той самий: файли Directus нікуди не подінуться.
