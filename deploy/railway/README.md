# Railway: engine + LibreChat

One Railway project, three parts:

| Service | What | Network |
|---|---|---|
| `constraint-engine` | this repo's `Dockerfile` (MCP over streamable HTTP, `[::]:8000/mcp`) | private only |
| LibreChat (+ MongoDB, Meilisearch, RAG API, VectorDB) | template `librechat-official` | LibreChat public |
| `librechat-config` | `config-service.Dockerfile`: serves `librechat.yaml` | private only |

Steps (CLI, logged in):

1. `railway init -n constraint-engine` in this repo, then `railway deploy -t librechat-official`.
2. `railway add --service constraint-engine` and `railway up --service constraint-engine`.
3. Build `librechat.yaml` = the template's config (its `CONFIG_PATH` URL) + `librechat-mcp.yaml`.
   Put it next to `config-service.Dockerfile` (renamed `Dockerfile`) in a folder, then
   `railway add --service librechat-config` and `railway up <folder> --path-as-root --service librechat-config`.
4. On LibreChat set `CONFIG_PATH=http://librechat-config.railway.internal:8080/librechat.yaml`
   and `SCHEDULES_SINGLE_PROCESS=true` (one replica).

The LibreChat log should show `[MCP] Initialized with 1 configured server and 12 tools.`

Notes:
- Model API keys are "user provided": each user enters theirs in LibreChat's UI.
- The template allows open registration; after creating your account set
  `ALLOW_REGISTRATION=false` on LibreChat.
- Engine state is in memory: a redeploy of `constraint-engine` loses loaded problems.
- `load_data` and `export_option` read and write files on the engine's own disk, so
  from a hosted chat they cannot reach files on your computer yet.
