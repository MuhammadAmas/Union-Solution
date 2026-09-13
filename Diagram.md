# Architecture Diagram

```mermaid
flowchart TB
    LeaderUI["Leadership screen\n(Next.js)"]
    MemberClient["Member client\n(read/ack endpoint)"]

    LB["Load Balancer\n(nginx, round-robin)"]

    subgraph App["App instances (stateless)"]
        A1["Instance 1\nDjango + DRF"]
        A2["Instance 2\nDjango + DRF"]
    end

    DB[("Postgres\nlocals / members / accounts\nannouncements / recipients\nsend_jobs")]
    Cache[("Redis / counts cache\n(aggregated sent/read/ack)")]
    Queue[["Task queue\n(Celery / RQ)"]]
    Worker["Background worker(s)\nfan-out + push dispatch"]
    Push["Push provider\n(logged / stubbed)"]

    LeaderUI -->|"POST /announcements/send"| LB
    MemberClient -->|"POST /recipients/:id/read|ack"| LB
    LB --> A1
    LB --> A2

    A1 -->|"insert announcement + send_job\n(txn, local_id from account)"| DB
    A2 -->|"insert announcement + send_job\n(txn, local_id from account)"| DB
    A1 -->|"read scoped by account.local_id"| DB
    A2 -->|"read scoped by account.local_id"| DB

    A1 --> Queue
    A2 --> Queue
    Queue --> Worker

    Worker -->|"bulk INSERT ... ON CONFLICT DO NOTHING\n(announcement_id, member_id) unique"| DB
    Worker --> Push
    Worker -->|"update recipient.status"| DB

    DB -->|"periodic aggregate"| Cache
    LeaderUI -->|"poll / SSE"| Cache
```

**Notes**
- Both app instances are stateless and interchangeable — either can receive any request, which is what the load-balancer bonus exercises.
- The uniqueness that prevents double-send lives in Postgres (`send_jobs.announcement_id` unique, `recipients(announcement_id, member_id)` unique), not in any single process's memory — so it holds no matter which instance handles a retry.
- The counts cache exists specifically so four people watching the live screen don't each trigger a full `COUNT(*)` over recipients every second.