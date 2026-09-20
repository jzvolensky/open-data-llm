# Documentation

Docusaurus site for the Bratislava Open Data LLM project. Content is available in
English and Slovak (use the language switch in the top-right).

## Run locally

```bash
npm install
npm run serve -- --build     # builds ALL locales, serves them -> switch works
# English at http://localhost:3000/ , Slovak at http://localhost:3000/sk/
```

For hot reload while editing, use the dev server (one locale at a time, Docusaurus
limitation):

```bash
npm start -- --locale en     # English
npm start -- --locale sk     # Slovak at /sk/
```

Via make:

```bash
make docs-serve     # build + serve both locales (recommended)
make docs-dev       # hot-reload dev server, DOCS_LOCALE=en
```

## Build

```bash
npm run build      # static output in ./build (en) and ./build/sk
```

## Deploy to GitHub Pages

A workflow at `.github/workflows/docs.yml` builds and publishes the site on every push
to `main` that touches `docs/`.

1. In the repository, open **Settings → Pages** and set **Source: GitHub Actions**.
2. Push to `main` (or run the **docs** workflow manually from the Actions tab).
3. The site is published at `https://<owner>.github.io/<repo>/`.

### If a deploy fails

`No artifacts named "github-pages" were found for this workflow run` means the `deploy`
job ran without the `build` job's artifact. The usual cause is using **Re-run failed
jobs**, which re-runs only `deploy` and does not re-upload the artifact. Instead:

> Actions → **docs** → **Re-run all jobs** (or push a new commit).

Also confirm **Settings → Pages → Source** is **GitHub Actions** (not "Deploy from a
branch"). The workflow uses the current Pages actions (`configure-pages@v6`,
`upload-pages-artifact@v5`, `deploy-pages@v5`) which run on Node 24.

The workflow derives `DOCS_URL`/`DOCS_BASE_URL` from the repository, so the base path is
correct for both project pages (`/<repo>/`) and user pages (`/`). To test locally with a
base path:

```bash
DOCS_URL=https://<owner>.github.io DOCS_BASE_URL=/<repo>/ npm run build
```

## Troubleshooting

**A translated page 404s (e.g. `/sk/developer-guide`)**

You are almost certainly running the **hot-reload dev server** (`npm start` / `make
docs-dev`), which — by Docusaurus design — compiles **one locale at a time**. It serves
English at `/` and does not compile `/sk/...`, so those URLs show "Page Not Found". The
translation is not missing.

Use the build+serve path, which serves every locale and makes the language switch work:

```bash
make docs-serve                          # or: npm run serve -- --build
```

If you prefer hot reload and only need Slovak, start it explicitly:

```bash
npm start -- --locale sk                 # serve at http://localhost:3000/sk/
```

**"Your Docusaurus site did not load properly … wrong site baseUrl"**

This happens when a GitHub Pages build (which uses `DOCS_BASE_URL=/<repo>/`) left stale
state in `.docusaurus`. The `prestart` script clears it automatically; to do it manually:

```bash
npm run clear
```

Local development always uses `baseUrl: '/'` unless `DOCS_BASE_URL` is set.

## Diagrams

Diagrams use [Mermaid](https://mermaid.js.org/) (` ```mermaid ` fenced blocks) and render
in the browser.

## Structure

- `docs/` – English Markdown sources (default locale).
- `i18n/sk/docusaurus-plugin-content-docs/current/` – Slovak translations.
- `i18n/sk/docusaurus-theme-classic/` – Slovak navbar/footer strings.
- `docusaurus.config.ts` – site config and locale setup.
- `sidebars.ts` – sidebar order.
