# stepik-archive

Локальный архив теории курсов [Stepik](https://stepik.org): выгрузка текстовых шагов в Markdown и поиск по файлам.

Для офлайн-доступа к материалам, к которым у вас уже есть доступ на Stepik.

## Возможности

- OAuth через официальный API Stepik
- Экспорт только теории (`block.name == text`); видео и задания пропускаются
- Опция `--include-all` — всё кроме video
- Структура папок: курс → модуль → урок.md
- Поиск через `ripgrep` (или встроенный fallback)

## Установка

Нужны [uv](https://docs.astral.sh/uv/) и Python 3.12+.

```bash
uv sync
cp .env.example .env
```

Для поиска удобно иметь [ripgrep](https://github.com/BurntSushi/ripgrep) (`rg`).

## OAuth на Stepik

1. Открыть https://stepik.org/oauth2/applications/
2. Создать приложение:
   - **Client type:** confidential
   - **Authorization grant type:**
     - `password` — для купленных/закрытых курсов (нужны логин и пароль Stepik)
     - `client-credentials` — только публичный контент
3. Grant type приложения и способ входа в `.env` должны совпадать. Если в `.env` заполнены `STEPIK_USERNAME` / `STEPIK_PASSWORD`, клиент использует `password`; при приложении с `client-credentials` будет `unauthorized_client`.
4. Записать Client ID и Client Secret в `.env`:

```env
STEPIK_CLIENT_ID=...
STEPIK_CLIENT_SECRET=...
STEPIK_USERNAME=your@email.com
STEPIK_PASSWORD=...
# STEPIK_GRANT_TYPE=password
```

Без username/password (или с `STEPIK_GRANT_TYPE=client_credentials`) API не отдаст содержимое платных/закрытых курсов.

## Использование

```bash
# список курсов, на которые вы записаны
uv run stepik-archive list

# выгрузка одного или нескольких курсов
uv run stepik-archive export 67
uv run stepik-archive export 67 70 76

# включая задания (без video)
uv run stepik-archive export 67 --include-all

# пример поиска по архиву
uv run stepik-archive search "декоратор"
```

Каталог по умолчанию: `./courses` (или `STEPIK_COURSES_DIR`).

Пример дерева:

```
courses/
  067_Course_Title/
    _meta.json
    01_Module/
      01_Lesson.md
```
