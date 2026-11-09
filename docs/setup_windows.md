# Windows Setup

Node.js runs the Vue website during development and builds it for deployment. Python runs the FastAPI backend and generates PDF reports. MindSpore is installed into a separate ML environment when training or testing the model locally; production inference is intended to run through ModelArts.

## Install Node.js

1. Download Node.js 22.23.3 for Windows x64 from the official site: https://nodejs.org/dist/latest-v22.x/node-v22.23.3-x64.msi
2. Run the Windows installer and keep the default options.
3. Close and reopen the VS Code terminal.
4. Check that Node.js and npm are available:

```powershell
node --version
npm --version
```

The first command should begin with `v22.`. The second should print an npm version.

## Install Python

1. Download Python 3.12 for Windows from the official site: https://www.python.org/downloads/windows/
2. Run the installer and select **Add python.exe to PATH** before choosing **Install Now**.
3. Close and reopen the VS Code terminal.
4. Check the installation:

```powershell
py --version
```

The result should begin with `Python 3.12.`. If `py` is not recognized, rerun the installer and enable the Python launcher and PATH option.

## Start the backend

In the VS Code terminal, change to the `backend` folder:

```powershell
cd backend
```

Create a private Python environment for this project:

```powershell
py -3.12 -m venv .venv
```

Install the backend packages into that environment:

```powershell
\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Start the API:

```powershell
$env:CORS_ALLOWED_ORIGINS = "http://localhost:5173"
\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

When it starts, open http://127.0.0.1:8000/health in a browser. The response should show `{"status":"ok"}`. API documentation is at http://127.0.0.1:8000/docs.

## Start the website

Keep the backend terminal running. Open a second VS Code terminal at the project root and enter the frontend folder:

```powershell
cd frontend
```

Install the website packages:

```powershell
npm install
```

Create your local settings file by copying the example:

```powershell
Copy-Item .env.example .env.local
```

Open `frontend/.env.local` and set `VITE_API_BASE_URL` to `http://127.0.0.1:8000`. To enable the interactive map, also set `VITE_MAPBOX_ACCESS_TOKEN` to a public token created in your Mapbox account. The token is exposed to website visitors, so use a public token restricted to your deployed domains. Do not put private credentials in this file.

Create a restricted public Mapbox token at https://account.mapbox.com/ and add it only if you want the interactive map tiles. Never use a secret Mapbox token in the frontend.

Start the website:

```powershell
npm run dev
```

Keep this frontend terminal running too. Vite prints a local website address, normally `http://localhost:5173`; open the exact **Local** address shown in the terminal. The app needs both terminals: Vite serves the website, while Uvicorn serves weather and other API requests.

After the page opens:

1. Confirm the backend is still running by opening http://127.0.0.1:8000/health in a browser. It should return `{"status":"ok"}`.
2. In **Map layers → Weather type**, choose rainfall screening, clouds, wind, precipitation, temperature, or pressure. The weather forecast layers load from the backend.
3. If you change `frontend/.env.local`, stop and restart Vite so it reads the new settings.

### If the app says “Failed to fetch”

“Failed to fetch” usually means the browser cannot reach the API; it does not by itself identify a weather-provider problem.

- If http://127.0.0.1:8000/health does not load, start or restart the backend in the `backend` terminal:

  ```powershell
  cd backend
  .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
  ```

- If the health check works but the page still fails, verify `frontend/.env.local` contains `VITE_API_BASE_URL=http://127.0.0.1:8000`, then stop and restart Vite.
- Keep both terminal windows open. If either server exits or its terminal is closed, restart that server and refresh the browser.
- Parcel and completed-assessment data can still report unavailable until GaussDB is configured and contains authorized data. This does not prevent the public Open-Meteo forecast layers from loading.

## MindSpore and Huawei Cloud

Do not install MindSpore or download an Ubuntu image for this dashboard stage. The official MindSpore installer currently lists Windows x64 as well as Linux options, but the correct package depends on the chosen MindSpore version and compute hardware. We will select it when the model code, training data, and ModelArts target are ready: https://www.mindspore.cn/install/en.

Ubuntu is an operating-system image for a cloud server, not an application to install on Windows. We only need to select a Linux image if a later deployment step calls for a Linux Huawei ECS server. ModelArts is the planned training and inference platform: https://support.huaweicloud.com/intl/en-us/modelarts/index.html.

SNAP and the full GDAL command-line toolchain are deferred until the Sentinel preprocessing pipeline is implemented. The parcel importer uses Fiona, which includes the GDAL support it needs for vector formats; install it through `backend/requirements.txt` rather than installing a separate GDAL package for the importer.
