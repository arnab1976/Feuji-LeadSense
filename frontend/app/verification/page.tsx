"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Conflict } from "@/lib/types";
import { RequireSession, Badge, Notice, Empty, statusKind } from "@/components/Ui";

export default function VerificationPage() {
  return (
    <RequireSession>
      <Workbench />
    </RequireSession>
  );
}

function Workbench() {
  const [queue, setQueue] = useState<Conflict[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  const load = () =>
    api
      .get<Conflict[]>("/leads/verification/queue")
      .then(setQueue)
      .catch((e) => setError(e.message));

  useEffect(() => {
    load();
  }, []);

  const resolve = async (id: string, resolution: string, custom = "") => {
    try {
      setBusy(id);
      const res = await api.post<any>("/leads/verification/resolve", {
        verification_id: id,
        resolution,
        custom_value: custom,
      });
      setMessage(
        res.remaining_conflicts
          ? `Resolved. ${res.remaining_conflicts} conflict(s) remain on this lead.`
          : "Resolved. This lead is now verified."
      );
      load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  };

  const bulk = async (resolution: string) => {
    try {
      setBusy("bulk");
      const res = await api.post<any>("/leads/verification/bulk-resolve", { resolution });
      setMessage(`${res.resolved} conflicts resolved across ${res.leads_cleared} leads.`);
      load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  };

  return (
    <>
      <div className="page-head">
        <h1>Verification workbench</h1>
        <p>
          Uploaded values on the left, extracted values on the right. Leads with an
          open conflict do not move on to enrichment or scoring until someone
          decides — that gate is the point of the product.
        </p>
      </div>

      <Notice kind="error">{error}</Notice>
      <Notice kind="success">{message}</Notice>

      <div className="toolbar">
        <strong>{queue.length}</strong>
        <span className="small muted">open conflict{queue.length === 1 ? "" : "s"}</span>
        <span className="spacer" />
        <button className="secondary" disabled={!queue.length || busy === "bulk"} onClick={() => bulk("extracted")}>
          Accept all extracted
        </button>
        <button className="ghost" disabled={!queue.length || busy === "bulk"} onClick={() => bulk("uploaded")}>
          Keep all uploaded
        </button>
      </div>

      {queue.length === 0 ? (
        <div className="card">
          <Empty>
            Queue is clear. Every lead has a trusted value for each compared field.
          </Empty>
        </div>
      ) : (
        queue.map((conflict) => (
          <ConflictCard
            key={conflict.verification_id}
            conflict={conflict}
            busy={busy === conflict.verification_id}
            onResolve={resolve}
          />
        ))
      )}
    </>
  );
}

function ConflictCard({
  conflict,
  busy,
  onResolve,
}: {
  conflict: Conflict;
  busy: boolean;
  onResolve: (id: string, resolution: string, custom?: string) => void;
}) {
  const [custom, setCustom] = useState("");

  return (
    <div className="card">
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <strong>{conflict.lead_name}</strong>
        <span className="small muted">{conflict.company}</span>
        <Badge kind={statusKind(conflict.status)}>{conflict.status.replace("_", " ")}</Badge>
        <Badge kind="neutral">{conflict.field.replace("_", " ")}</Badge>
        <span className="spacer" />
        <span className="small muted mono">
          {conflict.method} · confidence {conflict.confidence.toFixed(2)}
        </span>
      </div>

      <p className="hint" style={{ margin: "8px 0 12px" }}>
        {conflict.reason}
      </p>

      <div className="diff">
        <div className="side">
          <div className="k">Uploaded</div>
          <div className="v">{conflict.uploaded_value || <em className="muted">empty</em>}</div>
        </div>
        <div className="side">
          <div className="k">Extracted</div>
          <div className="v">{conflict.extracted_value || <em className="muted">empty</em>}</div>
        </div>
      </div>

      <div className="row" style={{ marginTop: 12 }}>
        <input
          placeholder="Or type the correct value"
          value={custom}
          onChange={(e) => setCustom(e.target.value)}
        />
        <button
          disabled={busy}
          onClick={() => onResolve(conflict.verification_id, "extracted")}
        >
          Use extracted
        </button>
        <button
          className="secondary"
          disabled={busy}
          onClick={() => onResolve(conflict.verification_id, "uploaded")}
        >
          Keep uploaded
        </button>
        <button
          className="ghost"
          disabled={busy || !custom.trim()}
          onClick={() => onResolve(conflict.verification_id, "custom", custom)}
        >
          Use my value
        </button>
      </div>
    </div>
  );
}
