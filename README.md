# Multi-Agent AI Orchestration Platform

Hermetisch afgesloten, reproduceerbare ontwikkelomgeving voor een multi-agent platform met:

- FastAPI backend
- LangGraph orchestration
- PostgreSQL long-term memory en checkpoints
- (Voorbereide) Next.js frontend integratie

## Mappenstructuur

```text
multiAgentOrchestraPlatform/
├── backend/
│   ├── api/                # FastAPI routes + SSE streaming
│   ├── multi_agent/        # LangGraph state, nodes, routing, graph
│   ├── db/                 # SQLAlchemy modellen + checkpointing
│   ├── alembic/            # Migraties
│   ├── init_db.py          # Veilige startup migratie runner
│   ├── Dockerfile
│   └── README.md
├── frontend/               # React/Next UI modules (agent stream)
├── docker-compose.yml      # Orchestration van backend + postgres
├── requirements.txt        # Python dependencies
└── README.md
```

## Snelle Setup

1. Kopieer environment variabelen:

```bash
cp .env.example .env
```

2. Vul je OpenAI API key in .env.

3. Start alles:

```bash
docker compose up -d --build
```

4. Controleer status:

```bash
docker compose ps
curl http://127.0.0.1:8000/health
```

## Reproduceerbaarheid

- PostgreSQL gebruikt een named volume (`postgres_data`), dus lokale state blijft bewaard na restart.
- Backend draait automatische Alembic migraties op startup (`AUTO_MIGRATE_ON_STARTUP=true`).
- `init_db.py` gebruikt een advisory lock om migratie-races te voorkomen bij parallelle container starts.

## Werkwijze in Fases

1. Setup basis opzetten en valideren.
2. Eerste harde save state commit zodra backend + db gezond zijn.
3. Fase 1 core agent logica bouwen en lokaal testen.
4. Committen na elke stabiele fase en documentatie direct bijwerken.

## Belangrijke Commando's

```bash
docker compose logs -f backend
docker compose logs -f db
docker compose down
docker compose down -v   # let op: verwijdert lokale db volume data
```