
## Stack

- **Strapi 5** — Headless CMS / API
- **TypeScript**
- **PostgreSQL**
- **Docker / Docker Compose** — Development environment

## Prerequisites

- Docker and Docker Compose
- (Optional) Node.js 20+ and PostgreSQL 14+ to run without Docker

## Start with Docker Compose

1. Copy the example env file and set required values:

   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and set at least `APP_KEYS`, `API_TOKEN_SALT`, `ADMIN_JWT_SECRET`, `JWT_SECRET`. For dev you can leave `DATABASE_PASSWORD` empty (defaults to `postgres`).

   Generate secrets with:

   ```bash
   openssl rand -base64 32
   ```

3. From the project root, start the stack:

   ```bash
   docker compose -f docker-compose.dev.yml up --build
   ```

   On older Docker setups:

   ```bash
   docker-compose -f docker-compose.dev.yml up --build
   ```