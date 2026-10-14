/**
 * /architecture page structure: the platform's technical architecture as of
 * 2026-09, one section per topic. The copy lives in the locale catalogs under
 * `architecture.sections.<id>.{title,intro,bullets[]}` (intro and bullets
 * render inline **bold** and `code`). Keep it truthful: every bullet
 * describes something that exists in the repos today, not a roadmap.
 */

export interface ArchSection {
  id: string
  /** Optional monospace diagram (language-neutral). */
  diagram?: string
}

export const ARCHITECTURE_DIAGRAM = `    +----------------------------------------------------+
    |                 Traefik (Ingress)                  |
    |    BenGER host / student host / org subdomains     |
    +----------------------------------------------------+
                |                             |
+-----------------------+       +-----------------------+
|        Frontend       |       |          API          |
|  Next.js 15, React 18 |  -->  |  FastAPI, Pydantic v2 |
| expert + student shell|       | sync + async DB lanes |
|      slot system      |       | JWT, org context, LTI |
+-----------------------+       +-----------------------+
                                    |       |       |
+-----------------------------------+       |       +-----------------+
v                                           v                         v
+-----------------------+   Redis   +-----------------------+   +-----------------------+
|      Worker pools     |<- broker ->|       PostgreSQL      |   |       MinIO / S3      |
|    Celery, 6 queues   |   pub/sub  |     Alembic, JSONB    |   |     import/export,    |
|    + beat schedule    |            |                       |   |        uploads        |
+-----------------------+            +-----------------------+   +-----------------------+

benger-platform (open core, Apache-2.0) + benger-extended (private): one image set;
extended plugs into API hooks, frontend slots and worker metric mappings.`

export const ARCHITECTURE_SECTIONS: ArchSection[] = [
  { id: 'overview', diagram: ARCHITECTURE_DIAGRAM },
  { id: 'frontend' },
  { id: 'api' },
  { id: 'workers' },
  { id: 'storage' },
  { id: 'annotation' },
  { id: 'organizations' },
  { id: 'integrations' },
  { id: 'deployment' },
]
