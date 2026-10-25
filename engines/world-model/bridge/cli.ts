// @ts-nocheck -- standalone runner executed by `tsx`; Node globals have no @types/node in this repo.
// Bridge runner: drives the TypeScript World Model from a one-shot JSON command on stdin (D-058).
//
// The slow integration test in Python runs this through `npx tsx` to prove the TypeScript reference and the
// Python store derive the same stable IDs and both report an empty diff on re-ingest. It reads one JSON
// command and writes one JSON result, so the Python side can bound each call with a subprocess timeout.
import { WorldModel } from "../index";

function respond(value: unknown): void {
  process.stdout.write(JSON.stringify(value) + "\n");
}

function main(): void {
  const chunks: Buffer[] = [];
  process.stdin.on("data", (chunk: Buffer) => chunks.push(chunk));
  process.stdin.on("end", () => {
    let cmd: any;
    try {
      cmd = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    } catch (error) {
      respond({ error: `bad command: ${String(error)}` });
      return;
    }
    try {
      const wm = new WorldModel({
        namespace: cmd.namespace || "barthelona",
        storage: "file",
        directory: cmd.directory,
      });
      if (cmd.op === "ping") {
        respond({ ok: true });
      } else if (cmd.op === "upsert") {
        const before = wm.stateShapeCanonical();
        wm.upsertEntity({
          type: cmd.kind,
          externalKey: { system: "barthelona", id: cmd.key },
          attrs: cmd.attrs || {},
          source: cmd.source,
        });
        respond({ changed: before !== wm.stateShapeCanonical() });
      } else if (cmd.op === "list") {
        const found: any[] = [];
        for (const entity of wm.store.state.entities.values()) {
          if (cmd.run_id && entity.attrs?.run_id !== cmd.run_id) continue;
          found.push({
            id: entity.id,
            kind: entity.type,
            attrs: entity.attrs || {},
          });
        }
        found.sort((a: any, b: any) =>
          (a.kind + a.id).localeCompare(b.kind + b.id),
        );
        respond({ entities: found });
      } else {
        respond({ error: `unknown op: ${cmd.op}` });
      }
    } catch (error) {
      respond({ error: String(error) });
    }
  });
}

main();
