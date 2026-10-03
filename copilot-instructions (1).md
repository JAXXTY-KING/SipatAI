# Copilot Instructions

## Project Context

SipatAI is a flood damage assessment platform for agricultural areas. It processes Sentinel-1 SAR and Sentinel-2 MSI imagery, detects flooded areas with a MindSpore U-Net (ResNet-50 backbone) model, intersects the results with farm parcels, and produces damage reports.

Stack:

- AI: MindSpore 2.x, MindIR export, Weighted Focal Loss, Dice Loss
- Cloud: Huawei Cloud ModelArts, OBS, GaussDB (PostGIS spatial engine), ECS
- Backend: Python, FastAPI, RESTful API
- Frontend: Vue 3, Mapbox GL JS
- Geospatial processing: GDAL, SNAP, GeoTIFF
- Output: damage assessment dashboard and PDF reports

The product is a responsive web application delivered through the browser. It is not a native or APK mobile app. Do not add mobile-app frameworks, wrappers, or packaging. The frontend is deployed to Vercel, and the backend runs separately on Huawei Cloud ECS.

Use only these technologies unless asked otherwise. Do not introduce alternative frameworks or libraries for something the stack already covers.

## Project Structure and Organization

- Split code by responsibility. Never place unrelated code in a single file or directory.
- Each file has one purpose. If a file starts handling multiple concerns, split it.
- Follow this layout. Create files in the matching directory, and add new subdirectories only when a new responsibility appears.

```
sipatai/
  backend/
    app/
      main.py                  Application entry point only
      api/
        routes/                One file per resource: analyze, damage_map, barangay, reports
        dependencies.py        Shared FastAPI dependencies
      core/
        config.py              Settings loaded from environment variables
        security.py            Authentication and authorization
        logging.py             Logging setup
      services/
        inference_service.py   Calls the deployed ModelArts endpoint
        damage_service.py      Flood polygon and parcel intersection, damage percentages
        valuation_service.py   Parcel valuation engine
        report_service.py      PDF report generation
      integrations/
        obs_client.py          Huawei OBS access
        modelarts_client.py    ModelArts access
        sentinel_client.py     Sentinel scene search and download
      db/
        session.py             GaussDB connection handling
        models.py              Table definitions
        queries/               Spatial queries, grouped by topic
      schemas/                 Request and response models
      utils/                   Small shared helpers
    tests/                     Mirrors the app/ structure
  ml/
    models/                    U-Net and ResNet-50 definitions
    losses/                    Weighted Focal Loss, Dice Loss
    datasets/                  MindSpore Dataset pipelines
    training/                  Training and evaluation scripts
    export/                    MindIR export
    configs/                   Hyperparameters and training configs
  preprocessing/
    sar/                       Calibration, noise removal, terrain correction (SNAP)
    raster/                    Alignment, reprojection, GeoTIFF handling (GDAL)
    indices/                   NDVI, NDWI and other derived channels
  frontend/
    src/
      api/                     HTTP client modules, one per backend resource
      components/              Reusable components, grouped by feature
      views/                   Page-level screens: Dashboard, FloodMap, ReportCenter
      stores/                  State management
      composables/             Reusable logic
      router/
      map/                     Mapbox layers, sources, and styling
      assets/
      utils/
  deploy/                      Deployment and infrastructure files
  scripts/                     One-off maintenance and setup scripts
  docs/
```

- Route handlers contain no business logic. They validate input, call a service, and return the result.
- Services contain no direct SQL. Database access goes through `db/queries/`.
- Calls to external services (OBS, ModelArts, Sentinel) only happen inside `integrations/`.
- Frontend components do not call the backend directly. They use modules in `api/`.
- Mapbox layer definitions live in `frontend/src/map/`, not inside component files.

## Sensitive Data

- Never hardcode secrets. This includes Huawei Cloud access keys and secret keys, OBS credentials, GaussDB connection strings and passwords, ModelArts endpoint tokens, Mapbox tokens, and any API keys.
- Backend secrets are read only through `backend/app/core/config.py`, which loads environment variables.
- Frontend variables are read through Vite environment variables (`import.meta.env`), and only values safe for public exposure may use the `VITE_` prefix. Anything private stays on the backend.
- Add every secret-bearing file (`.env`, key files, credential JSON) to `.gitignore`.
- Provide `.env.example` with placeholder values only.
- Never log secrets, tokens, or full connection strings.
- Validate and sanitize all input that reaches a database query. Use parameterized queries only.

## Code Style

- Do not use emojis anywhere: code, comments, UI text, log messages, commit messages, documentation, or chat responses.
- Use a professional, neutral tone in all user-facing text and logs.
- Python: follow PEP 8, use type hints on function signatures, and use `snake_case` for functions and variables.
- Vue: use Vue 3 with the Composition API and `<script setup>`. Component files use `PascalCase`.
- Use descriptive names. Avoid single-letter names outside of short loops and math expressions.

## Comments

- Comments are encouraged. They must describe what the code does and why it exists.
- Write them in a professional, concise, technical tone.
- Use docstrings for Python functions and classes, and short comments for non-obvious logic.
- Never write comments that narrate your own actions or the history of changes. Do not write things like "fixed", "replaced", "updated", "changed", "added this to", "removed", "now uses", or "previously".
- Comments must read as if the original author wrote them.

## UI and Design

- The interface is a government-facing tool. It must look professional, plain, and conventional.
- Avoid the oversized, overly rounded, soft "bubbly" look:
  - Border radius between 2px and 6px. No pill shapes or large radii on cards, inputs, or buttons.
  - Standard, compact padding and element sizes. Do not inflate elements.
  - No heavy drop shadows, glows, or decorative gradients.
  - Restrained color palette and standard font sizes.
- Do not add decorative filler such as taglines, hero banners, or placeholder text like "Welcome to your dashboard".
- Do not use illustration-style icons or emoji-style graphics. Use a single consistent, simple icon set.
- Data screens (dashboard, flood map, report center) should favor clarity: aligned tables, clear labels, units shown (hectares, currency), and consistent number formatting.
- Map damage severity uses a consistent, documented color scale defined in one place (`frontend/src/map/`). Do not redefine colors per component.
- Match the existing design when one exists.

## Responsive Design

The application must work on phones, tablets, laptops, and large desktop monitors. Responsiveness covers the whole layout, not only text and individual elements.

- Build mobile-first. Start with the smallest layout and add rules for larger screens with `min-width` media queries.
- Use these breakpoints consistently, defined once in a shared stylesheet or config: 640px, 768px, 1024px, 1280px.
- Layout:
  - Use CSS Grid and Flexbox. Do not use fixed pixel widths or heights for containers.
  - Page structure must change by screen size: for example, a sidebar becomes a collapsible drawer or top navigation on small screens, and multi-column grids become a single column.
  - No horizontal page scrolling at any width down to 320px.
- Typography and spacing: use relative units (`rem`, `%`, `clamp()`), not fixed `px` font sizes.
- Tables: on small screens, wrap in a horizontally scrollable container or reflow into stacked rows. Never let a table break the page layout.
- Map (Mapbox GL JS):
  - The map container sizes from its parent and fills the available viewport height, using `dvh` where supported.
  - Call `map.resize()` when the container size or orientation changes.
  - On small screens, move legends, layer toggles, and detail panels into collapsible panels or bottom sheets so they do not cover the map.
  - Controls must be usable by touch.
- Touch: interactive elements have a minimum target size of 44x44px on touch screens. Do not rely on hover for essential actions.
- Images and charts scale with their container and keep their aspect ratio.
- The report center and PDF download flow must work on mobile browsers.
- Include `<meta name="viewport" content="width=device-width, initial-scale=1">` in `index.html`.
- Test every new screen at 320px, 768px, 1024px, and 1440px widths before considering it complete.

## Deployment (Vercel)

The frontend in `frontend/` is deployed to Vercel. Keep it deployable at all times.

- Vercel project settings: root directory `frontend`, framework preset Vite, build command `npm run build`, output directory `dist`.
- Keep `package.json` and the lock file committed and consistent. The build must succeed from a clean install with no manual steps.
- Pin the Node version through the `engines` field in `package.json`.
- Add `frontend/vercel.json` with a rewrite that sends all non-file routes to `index.html`, so Vue Router history mode works on page refresh and direct links.
- Do not hardcode `localhost`, IP addresses, or any absolute backend URL. The API base URL comes from `import.meta.env.VITE_API_BASE_URL`, set in the Vercel dashboard for each environment.
- The backend is not hosted on Vercel. Requests go to the Huawei Cloud backend, which must:
  - be served over HTTPS, since browsers block HTTP requests from an HTTPS page
  - allow the Vercel production and preview domains in its CORS configuration, with the allowed origins read from environment variables
- Environment variables:
  - Only variables that are safe to expose may use the `VITE_` prefix, because they are embedded in the built files.
  - The Mapbox token used by the frontend must be a public token restricted to the deployed domain.
  - Private keys are never placed in the frontend. They stay in the backend environment.
  - Keep `frontend/.env.example` listing every required variable with placeholder values.
- Imports must match file names exactly, including letter case. The Vercel build runs on Linux, which is case-sensitive.
- Do not commit build output (`dist/`), `node_modules/`, or `.env` files.
- Do not place GeoTIFFs, rasters, models, or other large data files in the frontend. Large data is served from OBS or through the backend.
- Keep the production build free of errors and warnings. Remove unused imports and `console.log` statements.
- Add a `<title>`, favicon, and basic meta description in `index.html`.
- Do not add Vercel serverless functions or Vercel-specific services unless asked.

## Geospatial and ML Rules

- Always state and preserve the coordinate reference system. Do not reproject data silently. Reprojection happens in `preprocessing/raster/`, and the target CRS is defined in config.
- Keep the processing order of the SAR pipeline intact: calibration, noise removal, geo-referencing, raster alignment, GeoTIFF output. Do not reorder or skip steps.
- Input channel order for the model (VV, VH, and derived channels) is defined in one place in `ml/configs/`. Do not hardcode channel indexes elsewhere.
- Do not change the model input size, class definitions, or loss configuration without being asked. Training and inference must stay consistent with each other.
- Spatial intersection and damage percentages are computed in the database layer through PostGIS functions, not in Python loops.
- Large rasters are read in windows or tiles. Do not load full scenes into memory.

## Making Changes and Fixes

- Make the smallest change that solves the problem. Do not rewrite or refactor code that was not part of the request.
- Never delete, rename, or alter existing functions, variables, exports, files, endpoints, or parameters without first searching the entire project for every place they are used.
- If something looks unused, do not remove it unless explicitly asked. If removal is requested, confirm it has no references first.
- Preserve existing behavior, API contracts (request and response shapes), and database schemas unless the request is to change them.
- Before fixing an issue, check whether the same logic or fix already exists elsewhere.
  - Do not create duplicate functions, components, endpoints, queries, or styles.
  - Reuse or extend existing code instead of writing a parallel version.
  - If a previous attempt at the same fix is present, modify or replace that attempt instead of stacking another one on top.
- Do not leave behind dead code, commented-out blocks, or leftover debugging statements.
- Database changes must go through a migration. Never edit existing tables or data by hand-written one-off statements in application code.

## Downloads, Installs, and Setup Steps

The user is not experienced with development tools. Whenever the project needs something to be downloaded, installed, configured, or run (for example Node.js, Python, GDAL, SNAP, MindSpore, a package, a database tool, or the Vercel CLI), explain it in very simple terms.

- Never assume the user knows what a tool is, where to get it, or how to run it. Do not skip steps.
- Before the steps, say in one or two plain sentences what the thing is and why the project needs it.
- Give numbered steps, one action per step, in the exact order to do them.
- State exactly where to get it: the official website or official package source only, with the full link. Never point to unofficial mirrors or random download sites.
- State the exact version when the version matters.
- When the user must type a command:
  - Put each command in its own code block so it can be copied as is.
  - Say where to run it, for example "open the terminal inside VS Code" and which folder it must be run from.
  - Provide commands for the user's operating system. If the operating system is unknown, ask first, or give Windows, macOS, and Linux separately and label each one clearly.
  - Say what the user should see when it works.
- After install, give one simple command to check that it worked, and show what a successful result looks like.
- Add a short "If something goes wrong" note for the most likely errors, such as a command not being recognized, with the fix.
- Warn clearly before any step that could change or delete existing files or settings.
- Never ask the user to disable security features, run unknown scripts, or paste secrets into the chat.
- Do not use technical jargon without explaining it in the same sentence. Avoid abbreviations on first use.
- If the project already has a setup script or a documented install step, use it instead of inventing a new one, and record any new required setup in `docs/` and the README so it stays reproducible.
- Keep each response focused on one setup task at a time. Do not list many installs at once.

## Reporting Changes

After every update or fix, tell me in the chat response (never in code comments):

1. What was changed, listed by file.
2. Why the change was needed.
3. Anything that was removed or renamed, and confirmation that its usages were checked.
4. Any other files, endpoints, or features that could be affected.

If a request is unclear, or a fix could affect other parts of the system, ask before making the change.
