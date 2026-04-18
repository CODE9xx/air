# apps/web — Code9 Next.js 14 frontend

**Owner:** Frontend Engineer.
**Wave 1 (сейчас):** Next.js 14 App Router скелет — landing-заглушка `/` и `/health`.
**Wave 2:** Frontend Engineer реализует:

- i18n через `next-intl` (RU + EN, переключатель)
- auth-flow (login / register / verify email / reset password)
- workspace + crm-connections UI
- audit / export / dashboard страницы
- billing
- admin panel (отдельный layout)

## Запуск

```bash
docker compose up web
# http://localhost:3000
# Health: http://localhost:3000/health
```

Локально без docker:
```bash
cd apps/web
npm install
npm run dev
```
