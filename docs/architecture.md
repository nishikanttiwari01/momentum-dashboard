# Architecture

    ## Context (C4-Style)
    ```mermaid
    C4Context
      title Momentum Dashboard — System Context
      Person(user, "Trader", "Uses the dashboard to research swing trades")
      System_Boundary(app, "Momentum Dashboard") {
        System(back, "FastAPI Backend", "Python")
        System(front, "React Frontend", "TypeScript + Vite")
        System(extdata, "Yahoo Finance", "Market data (prices, OHLCV)")
        System(sqlite, "SQLite", "User state: alerts, positions, jobs, settings")
        System(parquet, "Parquet Store", "Snapshots: universe, indicators, scores")
        System(scheduler, "APScheduler", "Recurring scans + post-scan jobs")
      }
      Rel(user, front, "Uses")
      Rel(front, back, "REST (OpenAPI client)")
      Rel(back, parquet, "Read/Write", "pyarrow")
      Rel(back, sqlite, "CRUD", "SQLAlchemy")
      Rel(back, extdata, "Fetch OHLCV")
      Rel(scheduler, back, "Triggers scans")
    ```

    ## Container / Component
    ```mermaid
    C4Container
      title Containers
      Container(front, "React App", "Vite/React", "Screens, Table, Drawer")
      Container(back, "FastAPI Service", "Python", "Routers, Services, Repos")
      ContainerDb(sqlite, "SQLite", "SQLAlchemy", "alerts, positions, jobs, settings")
      ContainerDb(parquet, "Parquet", "PyArrow", "scores, indicators, universe")
      Rel(front, back, "JSON over HTTP")
      Rel(back, parquet, "pyarrow.parquet")
      Rel(back, sqlite, "ORM")
    ```

    ## Key Sequences

    **Screening Run → Score Snapshot**
    ```mermaid
    sequenceDiagram
      autonumber
      participant UI as React UI
      participant API as FastAPI /scan
      participant SVC as ScreeningService
      participant DS as Parquet Datasets
      participant DB as SQLite (jobs)
      UI->>API: POST /scan
      API->>DB: jobs.create(run_id, status='running')
      API->>SVC: screen(universe, config)
      SVC->>DS: begin_atomic_write('scores', run_id)
      SVC->>Yahoo: fetch prices/indicators
      SVC->>DS: write parquet partitions
+ metadata(schema_ver, rowcount)
      SVC-->>DB: jobs.update(status='success', timings, rowcount)
      API-->>UI: 202 Accepted + run_id
    ```

    **Open Right Drawer**
    ```mermaid
    sequenceDiagram
      autonumber
      participant UI as React UI
      participant API as GET /instruments/:symbol/detail
      participant Repo as ScoresRepo + MarketDataRepo
      UI->>API: GET /instruments/MAHASTEEL.NS/detail?run_id=latest
      API->>Repo: read score + indicators + sparkline
      Repo-->>API: DrawerDetail (next_action, reasons, metrics)
      API-->>UI: 200 JSON
    ```

    **Alert Pipeline (Post-Scan)**
    ```mermaid
    sequenceDiagram
      autonumber
      participant Sch as APScheduler
      participant API as post_scan_job
      participant Rules as AlertRules
      participant DB as alerts, history
      participant Notif as Email Digest
      Sch->>API: on scan completion(run_id)
      API->>Rules: evaluate(thresholds, crossings)
      Rules->>DB: enqueue history + actionable alerts
      API->>Notif: render digest(run_id summary, top movers)
      Notif-->>User: email preview / send
    ```