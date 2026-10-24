import * as fs from "node:fs";
import * as path from "node:path";

// ============================================================================
// Stable ID functions (ported from Python for synchronous access)
// ============================================================================

function normalizeName(name: string): string {
  // NFKD decomposition, strip combining marks, lowercase, collapse whitespace
  let nfkd = name.normalize("NFKD");
  let stripped = "";
  for (const c of nfkd) {
    const code = c.charCodeAt(0);
    if (code < 0x300 || code > 0x36f) {
      stripped += c;
    }
  }
  let lower = stripped.toLowerCase();
  lower = lower.replace(/\u00a0/g, " ");
  let collapsed = lower.replace(/\s+/g, " ").trim();
  return collapsed;
}

function entityIdFromName(entityType: string, name: string): string {
  const normalized = normalizeName(name);
  const content = `${entityType}:${normalized}`;
  const hash = syncHash(content);
  return `ent_${hash.slice(0, 16)}`;
}

function externalId(
  entityType: string,
  system: string,
  externalId: string,
): string {
  const content = `${entityType}:${system}:${externalId}`;
  const hash = syncHash(content);
  return `ext_${hash.slice(0, 16)}`;
}

function externalKeyString(
  entityType: string,
  system: string,
  externalId: string,
): string {
  return `${entityType}:${system}:${externalId}`;
}

function contextIdFromAttrs(
  contextType: string,
  attrs: Record<string, any>,
  parent?: string,
): string {
  const attrsJson = JSON.stringify(attrs, Object.keys(attrs).sort());
  const parentStr = parent || "";
  const content = `${contextType}:${parentStr}:${attrsJson}`;
  const hash = syncHash(content);
  return `ctx_${hash.slice(0, 16)}`;
}

function factId(
  about: string,
  predicate: string,
  value: any,
  at: string,
  kind: string,
  url?: string,
): string {
  const valueJson = JSON.stringify(value, Object.keys(value).sort());
  const urlStr = url || "";
  const content = `${about}:${predicate}:${valueJson}:${at}:${kind}:${urlStr}`;
  const hash = syncHash(content);
  return `fact_${hash.slice(0, 16)}`;
}

function relationshipId(
  from: string,
  relType: string,
  to: string,
  context?: string,
  validFrom?: string,
  attrs?: Record<string, any>,
): string {
  const contextStr = context || "";
  const validFromStr = validFrom || "";
  const attrsJson = JSON.stringify(
    attrs || {},
    Object.keys(attrs || {}).sort(),
  );
  const content = `${from}:${relType}:${to}:${contextStr}:${validFromStr}:${attrsJson}`;
  const hash = syncHash(content);
  return `rel_${hash.slice(0, 16)}`;
}

function syncHash(content: string): string {
  // Use a simple sync hash for synchronous operations
  let hash = 0;
  for (let i = 0; i < content.length; i++) {
    const char = content.charCodeAt(i);
    hash = (hash << 5) - hash + char;
    hash = hash & hash; // Convert to 32bit integer
  }
  return Math.abs(hash).toString(16).padStart(8, "0");
}

function canonicalJson(obj: any): string {
  const seen = new WeakSet();
  function sortKeys(o: any): any {
    if (o === null || typeof o !== "object") return o;
    if (seen.has(o)) return o;
    seen.add(o);

    if (Array.isArray(o)) {
      return o.map(sortKeys);
    }

    const sorted: Record<string, any> = {};
    for (const key of Object.keys(o).sort()) {
      sorted[key] = sortKeys(o[key]);
    }
    return sorted;
  }
  return JSON.stringify(sortKeys(obj));
}

function levenshtein(a: string, b: string): number {
  if (a.length < b.length) [a, b] = [b, a];
  if (b.length === 0) return a.length;

  let previousRow = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 0; i < a.length; i++) {
    const currentRow = [i + 1];
    for (let j = 0; j < b.length; j++) {
      const insertions = previousRow[j + 1] + 1;
      const deletions = currentRow[j] + 1;
      const substitutions = previousRow[j] + (a[i] !== b[j] ? 1 : 0);
      currentRow.push(Math.min(insertions, deletions, substitutions));
    }
    previousRow = currentRow;
  }
  return previousRow[b.length];
}

function nameSimilarity(name1: string, name2: string): number {
  const norm1 = name1.toLowerCase().trim();
  const norm2 = name2.toLowerCase().trim();

  if (norm1 === norm2) return 1.0;

  const maxLen = Math.max(norm1.length, norm2.length);
  if (maxLen === 0) return 1.0;

  const distance = levenshtein(norm1, norm2);
  return 1.0 - distance / maxLen;
}

function jaccard(set1: Set<string>, set2: Set<string>): number {
  if (set1.size === 0 && set2.size === 0) return 1.0;
  if (set1.size === 0 || set2.size === 0) return 0.0;

  const intersection = new Set([...set1].filter((x) => set2.has(x)));
  const union = new Set([...set1, ...set2]);
  return intersection.size / union.size;
}

function decide(
  similarity: number,
  autoMergeAt = 0.85,
  reviewBand: [number, number] = [0.82, 0.85],
): "auto-merge" | "review" | "new" {
  if (similarity >= autoMergeAt) return "auto-merge";
  if (similarity >= reviewBand[0]) return "review";
  return "new";
}

// ============================================================================
// TypeScript native WorldModel implementation
// ============================================================================

type ProvenanceKind = "manual" | "rss" | "api" | "ingest" | "resolver";

interface Provenance {
  kind: ProvenanceKind;
  at: string;
  by?: string;
  run_id?: string;
  url?: string;
}

interface StoredProvenance {
  kind: ProvenanceKind;
  at: string;
  by?: string;
  run_id?: string;
  url?: string;
}

type EntityState = "emerging" | "active" | "archived";

interface Entity {
  type: string;
  id: string;
  attrs: Record<string, any>;
  schema_version: number;
  source: StoredProvenance;
  created_at: string;
  updated_at: string;
  name?: string;
  aliases: string[];
  state: EntityState;
}

interface Context {
  type: string;
  id: string;
  attrs: Record<string, any>;
  schema_version: number;
  source: StoredProvenance;
  created_at: string;
  updated_at: string;
  parent?: string;
}

interface Relationship {
  id: string;
  from_: string;
  type: string;
  to: string;
  context?: string;
  attrs?: Record<string, any>;
  valid_from: string;
  valid_to?: string;
  schema_version: number;
  source: StoredProvenance;
  created_at: string;
}

interface Fact {
  id: string;
  about: string;
  predicate: string;
  value: any;
  confidence: number;
  context?: string;
  source: StoredProvenance;
  asserted_at: string;
  superseded_by?: string;
}

interface WorldEvent {
  id: string;
  kind: string;
  payload: any;
  at: string;
  seq: number;
}

interface AuditEntry {
  seq: number;
  action: string;
  by: string;
  detail: string;
  event_id?: string;
  run_id?: string;
  at: string;
}

interface IngestObservation {
  externalId: string;
  title: string;
  at: string;
  source: Provenance;
  type?: string;
  text?: string;
  entities?: Array<{ type: string; name: string }>;
}

interface IngestEntity {
  type: string;
  name: string;
}

interface IngestReport {
  processed: number;
  clusters: number;
  changed: boolean;
  skipped_unchanged: number;
}

interface MergeProposal {
  id: string;
  left_id: string;
  left_name: string;
  right_id: string;
  right_name: string;
  similarity: number;
  reason: string;
  status: "pending" | "approved" | "rejected";
  proposed_at: string;
  resolved_at?: string;
  resolved_by?: string;
}

interface WorldModelOptions {
  namespace: string;
  storage?: "memory" | "file";
  directory?: string;
  conflict_policy?:
    | "most-recent-wins"
    | "highest-confidence-wins"
    | "source-priority"
    | "manual";
  source_priority?: string[];
  resolver_auto_merge_at?: number;
  resolver_review_band?: [number, number];
  clock?: () => Date;
}

interface State {
  entities: Map<string, Entity>;
  contexts: Map<string, Context>;
  relationships: Map<string, Relationship>;
  facts: Map<string, Fact>;
  aliases: Map<string, string>;
  merge_queue: MergeProposal[];
}

interface GraphView {
  neighborsOf(
    id: string,
    options?: { via?: string; in_context?: string; at?: string },
  ): Array<{ id: string }>;
  incoming(id: string, options?: { via?: string }): Array<{ id: string }>;
}

class EventStore {
  namespace: string;
  state: State;
  events: WorldEvent[];
  audit: AuditEntry[];
  _seq: number = 0;
  _filePath: string | null = null;

  constructor(
    namespace: string,
    storage: string = "memory",
    directory: string | null = null,
  ) {
    this.namespace = namespace;
    this.state = {
      entities: new Map(),
      contexts: new Map(),
      relationships: new Map(),
      facts: new Map(),
      aliases: new Map(),
      merge_queue: [],
    };
    this.events = [];
    this.audit = [];

    if (storage === "file" && directory) {
      this._filePath = path.resolve(directory, `${namespace}.jsonl`);
      this._loadFromFile();
    }
  }

  _loadFromFile(): void {
    if (!this._filePath) return;
    try {
      if (!fs.existsSync(this._filePath)) return;
      const content = fs.readFileSync(this._filePath, "utf-8");
      for (const line of content.trim().split("\n")) {
        if (!line.trim()) continue;
        try {
          const eventData = JSON.parse(line);
          const event: WorldEvent = {
            id: eventData.id,
            kind: eventData.kind,
            payload: eventData.payload,
            at: eventData.at,
            seq: eventData.seq,
          };
          this.events.push(event);
          this._applyEvent(event);
          if (event.seq > this._seq) this._seq = event.seq;
        } catch {
          // Skip malformed lines
        }
      }
    } catch {
      // Ignore file errors
    }
  }

  _persistEvent(event: WorldEvent): void {
    if (!this._filePath) return;
    try {
      const eventData = {
        id: event.id,
        kind: event.kind,
        payload: event.payload,
        at: event.at,
        seq: event.seq,
      };
      fs.appendFileSync(this._filePath, JSON.stringify(eventData) + "\n");
    } catch {
      // Ignore persistence errors
    }
  }

  append(kind: string, payload: any, at: string): WorldEvent {
    this._seq += 1;
    const event: WorldEvent = {
      id: `${this.namespace}_${this._seq}_${Date.now()}`,
      kind,
      payload,
      at,
      seq: this._seq,
    };
    this.events.push(event);
    this._applyEvent(event);
    this._persistEvent(event);
    return event;
  }

  _applyEvent(event: WorldEvent): void {
    if (event.kind === "upsertEntity") {
      const entity = event.payload as Entity;
      const resolvedId = this.resolveAlias(entity.id);
      entity.id = resolvedId;
      this.state.entities.set(resolvedId, entity);
    } else if (event.kind === "upsertContext") {
      const context = event.payload as Context;
      this.state.contexts.set(context.id, context);
    } else if (event.kind === "relate") {
      const rel = event.payload as Relationship;
      this.state.relationships.set(rel.id, rel);
    } else if (event.kind === "assertFact") {
      const fact = event.payload as Fact;
      this.state.facts.set(fact.id, fact);
    } else if (event.kind === "alias") {
      const aliasData = event.payload as { aliasId: string; primaryId: string };
      this.state.aliases.set(aliasData.aliasId, aliasData.primaryId);
    }
  }

  resolveAlias(entityId: string): string {
    const visited = new Set<string>();
    let current = entityId;
    while (this.state.aliases.has(current) && !visited.has(current)) {
      visited.add(current);
      current = this.state.aliases.get(current)!;
    }
    return current;
  }

  // Get the external key format (type:system:id) for an entity if it exists
  getExternalKeyFormat(entityId: string): string | null {
    const resolved = this.resolveAlias(entityId);
    const entity = this.state.entities.get(resolved);
    if (!entity) return null;

    // Look for an alias in the format type:system:id
    for (const [aliasId, primaryId] of this.state.aliases) {
      if (
        primaryId === resolved &&
        aliasId.includes(":") &&
        aliasId.split(":").length === 3
      ) {
        return aliasId;
      }
    }
    return null;
  }

  logAudit(
    action: string,
    by: string,
    detail: string,
    eventId?: string,
    runId?: string,
    at?: string,
  ): void {
    const entry: AuditEntry = {
      seq: this.audit.length + 1,
      action,
      by,
      detail,
      event_id: eventId,
      run_id: runId,
      at: at || new Date().toISOString(),
    };
    this.audit.push(entry);
  }

  foldUntil(at: string): State {
    const tempState: State = {
      entities: new Map(),
      contexts: new Map(),
      relationships: new Map(),
      facts: new Map(),
      aliases: new Map(),
      merge_queue: [],
    };
    for (const event of this.events) {
      if (event.at > at) break;
      this._applyEventToState(tempState, event);
    }
    return tempState;
  }

  _applyEventToState(state: State, event: WorldEvent): void {
    if (event.kind === "upsertEntity") {
      const entity = event.payload as Entity;
      const resolvedId = this._resolveAliasInState(state, entity.id);
      entity.id = resolvedId;
      state.entities.set(resolvedId, entity);
    } else if (event.kind === "upsertContext") {
      const context = event.payload as Context;
      state.contexts.set(context.id, context);
    } else if (event.kind === "relate") {
      const rel = event.payload as Relationship;
      state.relationships.set(rel.id, rel);
    } else if (event.kind === "assertFact") {
      const fact = event.payload as Fact;
      state.facts.set(fact.id, fact);
    } else if (event.kind === "alias") {
      const aliasData = event.payload as { aliasId: string; primaryId: string };
      state.aliases.set(aliasData.aliasId, aliasData.primaryId);
    }
  }

  _resolveAliasInState(state: State, entityId: string): string {
    const visited = new Set<string>();
    let current = entityId;
    while (state.aliases.has(current) && !visited.has(current)) {
      visited.add(current);
      current = state.aliases.get(current)!;
    }
    return current;
  }
}

function worldStateShape(store: EventStore): any {
  const entities: Record<string, any> = {};
  for (const [eid, e] of store.state.entities) {
    entities[eid] = {
      type: e.type,
      id: e.id,
      attrs: e.attrs,
      name: e.name,
      aliases: e.aliases,
      state: e.state,
    };
  }

  const contexts: Record<string, any> = {};
  for (const [cid, c] of store.state.contexts) {
    contexts[cid] = {
      type: c.type,
      id: c.id,
      attrs: c.attrs,
      parent: c.parent,
    };
  }

  const relationships: Record<string, any> = {};
  for (const [rid, r] of store.state.relationships) {
    relationships[rid] = {
      id: r.id,
      from: r.from_,
      type: r.type,
      to: r.to,
      context: r.context,
      valid_from: r.valid_from,
      valid_to: r.valid_to,
    };
  }

  const facts: Record<string, any> = {};
  for (const [fid, f] of store.state.facts) {
    facts[fid] = {
      id: f.id,
      about: f.about,
      predicate: f.predicate,
      value: f.value,
      confidence: f.confidence,
      context: f.context,
      superseded_by: f.superseded_by,
    };
  }

  const aliases: Record<string, string> = {};
  for (const [aid, pid] of store.state.aliases) {
    aliases[aid] = pid;
  }

  return { entities, contexts, relationships, facts, aliases };
}

function normalizeProvenance(source: Provenance | undefined): StoredProvenance {
  if (!source || !source.kind || !source.at) {
    throw new Error(
      "World Model: every write carries provenance (kind + at). No provenance, no write.",
    );
  }
  return {
    kind: source.kind,
    at: source.at,
    by: source.by,
    run_id: source.run_id,
    url: source.url,
  };
}

function resolveEntityId(
  store: EventStore,
  type: string,
  externalKey?: { system: string; id: string },
  name?: string,
): string {
  if (externalKey) {
    return externalId(type, externalKey.system, externalKey.id);
  }
  if (!name) {
    throw new Error(
      "World Model: name-keyed entities need a name (or provide an externalKey)",
    );
  }
  return entityIdFromName(type, name);
}

export class WorldModelClass {
  opts: WorldModelOptions;
  clock: () => Date;
  store: EventStore;
  _ingestClock: () => number;

  constructor(opts: WorldModelOptions) {
    if (!opts.namespace) {
      throw new Error("WorldModel: namespace is required");
    }
    this.opts = opts;
    this.clock = opts.clock || (() => new Date());
    const directory = opts.storage === "file" ? opts.directory : undefined;
    this.store = new EventStore(
      opts.namespace,
      opts.storage || "memory",
      directory,
    );
    this._ingestClock = () => Math.floor(this.clock().getTime() / 1000);
  }

  _normalizeProvenance(source: Provenance | undefined): StoredProvenance {
    return normalizeProvenance(source);
  }

  _foldEntityUpsert(
    entityId: string,
    inputData: {
      type: string;
      attrs?: Record<string, any>;
      external_key?: { system: string; id: string };
      name?: string;
      state?: EntityState;
    },
    source: StoredProvenance,
    name?: string,
  ): Entity {
    const resolved = this.store.resolveAlias(entityId);
    const existing = this.store.state.entities.get(resolved);

    if (existing) {
      const newAttrs = { ...existing.attrs, ...(inputData.attrs || {}) };
      const newAliases = [...existing.aliases];
      if (name && !newAliases.includes(name)) {
        newAliases.push(name);
      }

      existing.attrs = newAttrs;
      existing.aliases = newAliases;
      existing.updated_at = source.at;
      existing.source = source;
      if (inputData.state) {
        existing.state = inputData.state;
      }

      this.store.append("upsertEntity", existing, source.at);
      this.store.logAudit(
        "upsertEntity",
        source.by || "system",
        `${resolved} (${inputData.type})`,
        undefined,
        source.run_id,
        source.at,
      );
      return existing;
    } else {
      const entity: Entity = {
        type: inputData.type,
        id: resolved,
        attrs: { ...(inputData.attrs || {}) },
        schema_version: 1,
        source,
        created_at: source.at,
        updated_at: source.at,
        name,
        aliases: name ? [name] : [],
        state: inputData.state || "active",
      };
      this.store.append("upsertEntity", entity, source.at);
      this.store.logAudit(
        "upsertEntity",
        source.by || "system",
        `${resolved} (${inputData.type})`,
        undefined,
        source.run_id,
        source.at,
      );
      return this.store.state.entities.get(resolved)!;
    }
  }

  upsertEntity(params: {
    type: string;
    externalKey?: { system: string; id: string };
    name?: string;
    attrs?: Record<string, any>;
    source?: Provenance;
    state?: EntityState;
  }): Entity {
    const source = this._normalizeProvenance(params.source);
    const entityId = resolveEntityId(
      this.store,
      params.type,
      params.externalKey,
      params.name,
    );

    // Resolution pass for name-keyed entities
    if (!params.externalKey && params.name) {
      for (const other of this.store.state.entities.values()) {
        if (other.type !== params.type || other.id === entityId || !other.name)
          continue;
        const similarity = nameSimilarity(params.name, other.name);
        const decision = decide(
          similarity,
          this.opts.resolver_auto_merge_at || 0.85,
          this.opts.resolver_review_band || [0.82, 0.85],
        );
        if (decision === "auto-merge") {
          this.store.append(
            "alias",
            {
              aliasId: entityId,
              primaryId: other.id,
              mergedAt: source.at,
              mergedBy: "resolver",
              reason: `similarity ${similarity.toFixed(3)}`,
            },
            source.at,
          );
          this.store.logAudit(
            "auto-merge",
            "resolver",
            `${params.name} -> ${other.name} (${similarity.toFixed(3)})`,
            undefined,
            undefined,
            source.at,
          );
          return this._foldEntityUpsert(
            other.id,
            { type: params.type, attrs: params.attrs },
            source,
            params.name,
          );
        } else if (decision === "review") {
          const proposalId = `merge_${this.store.state.merge_queue.length + 1}`;
          if (
            !this.store.state.merge_queue.some(
              (p) =>
                (p.left_id === entityId && p.right_id === other.id) ||
                (p.left_id === other.id && p.right_id === entityId),
            )
          ) {
            const proposal: MergeProposal = {
              id: proposalId,
              left_id: entityId,
              right_id: other.id,
              left_name: params.name,
              right_name: other.name!,
              similarity,
              reason: "name similarity in review band [0.82, 0.85)",
              status: "pending",
              proposed_at: source.at,
            };
            this.store.state.merge_queue.push(proposal);
            this.store.logAudit(
              "merge-proposed",
              "resolver",
              `${params.name} ~ ${other.name} (${similarity.toFixed(3)}) queued`,
              undefined,
              undefined,
              source.at,
            );
          }
        }
      }
    }

    const result = this._foldEntityUpsert(
      entityId,
      {
        type: params.type,
        attrs: params.attrs,
        external_key: params.externalKey,
      },
      source,
      params.name,
    );

    // Create external key alias for hash-based ID
    if (params.externalKey) {
      const externalKeyStr = externalKeyString(
        params.type,
        params.externalKey.system,
        params.externalKey.id,
      );
      if (!this.store.state.aliases.has(externalKeyStr)) {
        this.store.append(
          "alias",
          {
            aliasId: externalKeyStr,
            primaryId: entityId,
            mergedAt: source.at,
            mergedBy: "system",
            reason: "external key alias",
          },
          source.at,
        );
        this.store.logAudit(
          "alias",
          "system",
          `${externalKeyStr} -> ${entityId}`,
          undefined,
          undefined,
          source.at,
        );
      }
    }

    return result;
  }

  upsertContext(params: {
    type: string;
    externalKey?: { system: string; id: string };
    attrs?: Record<string, any>;
    parent?: string;
    source?: Provenance;
  }): Context {
    const source = this._normalizeProvenance(params.source);

    let contextId: string;
    if (params.externalKey) {
      contextId = externalId(
        params.type,
        params.externalKey.system,
        params.externalKey.id,
      );
    } else {
      contextId = contextIdFromAttrs(
        params.type,
        params.attrs || {},
        params.parent,
      );
    }

    const context: Context = {
      type: params.type,
      id: contextId,
      attrs: params.attrs || {},
      schema_version: 1,
      source,
      created_at: source.at,
      updated_at: source.at,
      parent: params.parent,
    };
    this.store.append("upsertContext", context, source.at);
    this.store.logAudit(
      "upsertContext",
      source.by || "system",
      `${contextId} (${params.type})`,
      undefined,
      source.run_id,
      source.at,
    );
    return this.store.state.contexts.get(contextId)!;
  }

  relate(params: {
    from: string;
    type: string;
    to: string;
    context?: string;
    attrs?: Record<string, any>;
    validFrom?: string;
    validTo?: string;
    source?: Provenance;
  }): Relationship {
    const source = this._normalizeProvenance(params.source);
    const fromResolved = this.store.resolveAlias(params.from);
    const toResolved = this.store.resolveAlias(params.to);

    // For bitemporal edges: find and close any existing open edge with same from and type
    for (const existingRel of this.store.state.relationships.values()) {
      if (
        existingRel.from_ === fromResolved &&
        existingRel.type === params.type &&
        existingRel.valid_to === undefined
      ) {
        existingRel.valid_to = params.validFrom || source.at;
        this.store.append("relate", existingRel, source.at);
        this.store.logAudit(
          "relate",
          source.by || "system",
          `${fromResolved} -[${params.type}]-> ${existingRel.to} (closed)`,
          undefined,
          source.run_id,
          source.at,
        );
        break;
      }
    }

    const relId = relationshipId(
      fromResolved,
      params.type,
      toResolved,
      params.context,
      params.validFrom,
      params.attrs,
    );
    if (this.store.state.relationships.has(relId)) {
      return this.store.state.relationships.get(relId)!;
    }

    const rel: Relationship = {
      id: relId,
      from_: fromResolved,
      type: params.type,
      to: toResolved,
      context: params.context,
      attrs: params.attrs,
      valid_from: params.validFrom || source.at,
      valid_to: params.validTo,
      schema_version: 1,
      source,
      created_at: source.at,
    };
    this.store.append("relate", rel, source.at);
    this.store.logAudit(
      "relate",
      source.by || "system",
      `${fromResolved} -[${params.type}]-> ${toResolved}`,
      undefined,
      source.run_id,
      source.at,
    );
    return this.store.state.relationships.get(relId)!;
  }

  assertFact(params: {
    about: string;
    predicate: string;
    value: any;
    confidence?: number;
    context?: string;
    source?: Provenance;
  }): Fact {
    const source = this._normalizeProvenance(params.source);
    const aboutResolved = this.store.resolveAlias(params.about);

    const factIdVal = factId(
      aboutResolved,
      params.predicate,
      params.value,
      source.at,
      source.kind,
      source.url || "",
    );
    if (this.store.state.facts.has(factIdVal)) {
      return this.store.state.facts.get(factIdVal)!;
    }

    const fact: Fact = {
      id: factIdVal,
      about: aboutResolved,
      predicate: params.predicate,
      value: params.value,
      confidence: params.confidence ?? 0.5,
      context: params.context,
      source,
      asserted_at: source.at,
    };

    // Conflict resolution
    const policy = this.opts.conflict_policy || "most-recent-wins";
    const rivals = Array.from(this.store.state.facts.values()).filter(
      (f) =>
        f.about === aboutResolved &&
        f.predicate === params.predicate &&
        !f.superseded_by,
    );
    let winner = fact;
    for (const rival of rivals) {
      let rivalWins = false;
      if (policy === "highest-confidence-wins") {
        rivalWins = rival.confidence > winner.confidence;
      } else if (policy === "source-priority") {
        const rivalPriority = this._priorityOf(rival.source.kind);
        const winnerPriority = this._priorityOf(winner.source.kind);
        rivalWins = rivalPriority < winnerPriority;
      } else {
        rivalWins = rival.asserted_at > winner.asserted_at;
      }
      if (rivalWins) {
        winner = rival;
      }
    }

    this.store.append("assertFact", fact, source.at);

    for (const f of [fact, ...rivals]) {
      if (f.id !== winner.id) {
        const existingFact = this.store.state.facts.get(f.id);
        if (existingFact) {
          existingFact.superseded_by = winner.id;
        }
      }
    }

    // Ensure subject entity exists
    if (!this.store.state.entities.has(aboutResolved)) {
      const inferredType = aboutResolved.split(":")[0] || "entity";
      this.store.append(
        "upsertEntity",
        {
          type: inferredType,
          id: aboutResolved,
          attrs: {},
          schema_version: 1,
          source,
          created_at: source.at,
          updated_at: source.at,
          aliases: [],
          state: "emerging",
        },
        source.at,
      );
    }

    const entity = this.store.state.entities.get(aboutResolved)!;
    entity.attrs[params.predicate] = winner.value;
    entity.updated_at = source.at;

    this.store.logAudit(
      "assertFact",
      source.by || "system",
      `${aboutResolved}.${params.predicate} = ${winner.value} (${policy})`,
      undefined,
      source.run_id,
      source.at,
    );

    return this.store.state.facts.get(factIdVal)!;
  }

  _priorityOf(kind: string): number {
    const ranking = this.opts.source_priority || [];
    const idx = ranking.indexOf(kind);
    return idx >= 0 ? idx : 1000;
  }

  ingest(observations: IngestObservation[]): IngestReport {
    // Capture state shape before
    const shapeBefore = worldStateShape(this.store);

    let processed = 0;

    for (const obs of observations) {
      const source = this._normalizeProvenance(obs.source);
      const obsType = obs.type || "item";
      const obsEntityId = externalId(obsType, "ingest", obs.externalId);

      // Create or update observation entity
      this._foldEntityUpsert(
        obsEntityId,
        {
          type: obsType,
          external_key: { system: "ingest", id: obs.externalId },
          attrs: { title: obs.title, text: obs.text },
        },
        source,
        obs.title,
      );

      // Process mentioned entities
      for (const mention of obs.entities || []) {
        const mid = entityIdFromName(mention.type, mention.name);
        this._foldEntityUpsert(
          mid,
          { type: mention.type, name: mention.name },
          source,
          mention.name,
        );
        const resolvedMid = this.store.resolveAlias(mid);

        // Create mentions relationship
        const rid = relationshipId(
          obsEntityId,
          "mentions",
          resolvedMid,
          undefined,
          undefined,
          { mention: true },
        );
        if (!this.store.state.relationships.has(rid)) {
          const rel: Relationship = {
            id: rid,
            from_: obsEntityId,
            type: "mentions",
            to: resolvedMid,
            valid_from: source.at,
            schema_version: 1,
            source,
            created_at: source.at,
          };
          this.store.append("relate", rel, source.at);
        }
      }
      processed++;
    }

    // Capture state shape after
    const shapeAfter = worldStateShape(this.store);
    const changed = canonicalJson(shapeBefore) !== canonicalJson(shapeAfter);

    let skipped = 0;
    if (!changed) skipped = processed;

    return {
      processed,
      clusters: 0,
      changed,
      skipped_unchanged: skipped,
    };
  }

  stateShapeCanonical(): string {
    return canonicalJson(worldStateShape(this.store));
  }

  view(name: string): GraphView {
    if (name === "graph") {
      const self = this;
      return {
        neighborsOf(
          id: string,
          options?: { via?: string; in_context?: string; at?: string },
        ): Array<{ id: string }> {
          const rid = self.store.resolveAlias(id);
          const out: Array<{ id: string }> = [];

          for (const rel of self.store.state.relationships.values()) {
            if (options?.via && rel.type !== options.via) continue;
            if (options?.in_context && rel.context !== options.in_context)
              continue;
            if (options?.at && !self._validAt(rel, options.at)) continue;
            if (!options?.at && rel.valid_to) continue;

            let other: string | null = null;
            if (rel.from_ === rid) other = rel.to;
            else if (rel.to === rid) other = rel.from_;

            if (!other) continue;

            const entity = self.store.state.entities.get(other);
            if (entity) {
              // Return external key format if available, otherwise internal ID
              const displayId =
                self.store.getExternalKeyFormat(entity.id) || entity.id;
              out.push({ id: displayId });
            }
          }

          return out.sort((a, b) => a.id.localeCompare(b.id));
        },
        incoming(
          id: string,
          options?: { via?: string },
        ): Array<{ id: string }> {
          const rid = self.store.resolveAlias(id);
          const out: Array<{ id: string }> = [];

          for (const rel of self.store.state.relationships.values()) {
            if (rel.to !== rid) continue;
            if (options?.via && rel.type !== options.via) continue;
            if (rel.valid_to) continue;

            const entity = self.store.state.entities.get(rel.from_);
            if (entity) {
              // Return external key format if available, otherwise internal ID
              const displayId =
                self.store.getExternalKeyFormat(entity.id) || entity.id;
              out.push({ id: displayId });
            }
          }

          return out.sort((a, b) => a.id.localeCompare(b.id));
        },
      };
    }
    throw new Error(`World Model: unknown view '${name}'`);
  }

  _validAt(rel: Relationship, at: string): boolean {
    if (rel.valid_from && at < rel.valid_from) return false;
    if (rel.valid_to && at >= rel.valid_to) return false;
    return true;
  }

  audit(): AuditEntry[] {
    return [...this.store.audit];
  }

  events(): WorldEvent[] {
    return [...this.store.events];
  }
}

// ============================================================================
// Exports required by conformance runner
// ============================================================================

export {
  WorldModelClass as WorldModel,
  canonicalJson,
  contextIdFromAttrs,
  decide,
  entityIdFromName,
  externalId,
  factId,
  jaccard,
  levenshtein,
  nameSimilarity,
  normalizeName,
  relationshipId,
};
