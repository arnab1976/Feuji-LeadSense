"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Connector, SourceConnection } from "@/lib/types";
import { RequireSession, Badge, Notice, Empty } from "@/components/Ui";

export default function SourcesPage() {
  return (
    <RequireSession>
      <Sources />
    </RequireSession>
  );
}

function Sources() {
  const [catalog, setCatalog] = useState<Connector[]>([]);
  const [connections, setConnections] = useState<SourceConnection[]>([]);
  const [selected, setSelected] = useState<Connector | null>(null);
  const [config, setConfig] = useState<Record<string, string>>({});
  const [name, setName] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  const load = () => {
    api.get<Connector[]>("/sources/catalog").then(setCatalog).catch((e) => setError(e.message));
    api
      .get<SourceConnection[]>("/sources/connections")
      .then(setConnections)
      .catch((e) => setError(e.message));
  };

  useEffect(load, []);

  const pick = (connector: Connector) => {
    setSelected(connector);
    setName(connector.display_name);
    const initial: Record<string, string> = {};
    connector.config_fields.forEach((f) => {
      initial[f.name] = f.default != null ? String(f.default) : "";
    });
    setConfig(initial);
    setMessage("");
    setError("");
  };

  const create = async () => {
    if (!selected) return;
    try {
      setBusy("create");
      await api.post("/sources/connections", {
        name,
        connector_key: selected.key,
        config,
        policy_allowed: !selected.requires_policy_review,
        lawful_basis: selected.requires_policy_review ? "unknown" : "legitimate_interest",
      });
      setMessage(`${selected.display_name} connected.`);
      setSelected(null);
      load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  };

  const test = async (id: string) => {
    try {
      setBusy(id);
      const res = await api.post<{ ok: boolean; message: string }>(
        `/sources/connections/${id}/test`
      );
      setMessage(`${res.ok ? "Connected" : "Failed"} — ${res.message}`);
      load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  };

  const sync = async (id: string) => {
    try {
      setBusy(id);
      setError("");
      const res = await api.post<any>(`/sources/connections/${id}/sync`, {
        limit: 25,
        run_pipeline: true,
      });
      setMessage(
        `Fetched ${res.fetched}, created ${res.created}, ${res.duplicates} duplicate, ${res.invalid} invalid.`
      );
      load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  };

  const toggle = async (conn: SourceConnection) => {
    try {
      await api.patch(`/sources/connections/${conn.id}`, { is_enabled: !conn.is_enabled });
      load();
    } catch (e: any) {
      setError(e.message);
    }
  };

  return (
    <>
      <div className="page-head">
        <h1>Source layers</h1>
        <p>
          Every lead source implements one connector interface, so a spreadsheet, a
          CRM and a data vendor all arrive in the same shape and follow the same
          policy checks.
        </p>
      </div>

      <Notice kind="error">{error}</Notice>
      <Notice kind="success">{message}</Notice>

      <UploadCard onDone={(m) => { setMessage(m); load(); }} onError={setError} />

      <div className="card">
        <h2>Configured connections</h2>
        <p className="hint">
          A source flagged for policy review stays blocked until a lawful basis is
          recorded — the compliance agent refuses to send to leads from it.
        </p>
        {connections.length === 0 ? (
          <Empty>No connections yet.</Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Connector</th>
                  <th>Status</th>
                  <th>Policy</th>
                  <th>Last sync</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {connections.map((conn) => (
                  <tr key={conn.id}>
                    <td>
                      <strong>{conn.name}</strong>
                      {conn.last_error && (
                        <div className="small" style={{ color: "var(--red)" }}>
                          {conn.last_error}
                        </div>
                      )}
                    </td>
                    <td className="mono">{conn.connector_key}</td>
                    <td>
                      <Badge kind={conn.is_enabled ? "ok" : "neutral"}>
                        {conn.is_enabled ? conn.status : "disabled"}
                      </Badge>
                    </td>
                    <td>
                      <Badge kind={conn.policy_allowed ? "ok" : "bad"}>
                        {conn.policy_allowed ? conn.lawful_basis : "blocked"}
                      </Badge>
                    </td>
                    <td className="small muted">
                      {conn.last_sync_at
                        ? new Date(conn.last_sync_at).toLocaleString()
                        : "never"}
                    </td>
                    <td>
                      <div className="toolbar" style={{ margin: 0 }}>
                        <button
                          className="secondary small"
                          disabled={busy === conn.id}
                          onClick={() => test(conn.id)}
                        >
                          Test
                        </button>
                        <button
                          className="small"
                          disabled={busy === conn.id || !conn.is_enabled}
                          onClick={() => sync(conn.id)}
                        >
                          {busy === conn.id ? "Syncing…" : "Sync"}
                        </button>
                        <button className="ghost small" onClick={() => toggle(conn)}>
                          {conn.is_enabled ? "Disable" : "Enable"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card">
        <h2>Connector catalog</h2>
        <p className="hint">
          Rendered from the backend registry. Add a class in{" "}
          <span className="mono">app/connectors/</span> and it appears here with no
          frontend change.
        </p>
        <div className="grid cols-3">
          {catalog.map((connector) => (
            <div
              key={connector.key}
              className="stat"
              style={{ cursor: "pointer" }}
              onClick={() => pick(connector)}
            >
              <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                <strong>{connector.display_name}</strong>
                <Badge kind="neutral">{connector.kind}</Badge>
                {connector.requires_policy_review && <Badge kind="warn">policy review</Badge>}
              </div>
              <div className="small muted" style={{ marginTop: 6 }}>
                {connector.description}
              </div>
              <div className="small mono muted" style={{ marginTop: 6 }}>
                {connector.capabilities.join(" · ")}
              </div>
            </div>
          ))}
        </div>
      </div>

      {selected && (
        <div className="card">
          <h2>Connect {selected.display_name}</h2>
          <p className="hint">
            This form is generated from the connector&apos;s declared config fields.
          </p>
          <div className="field">
            <label>Connection name</label>
            <input value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          {selected.config_fields.map((field) => (
            <div className="field" key={field.name}>
              <label>
                {field.label}
                {field.required ? " *" : ""}
              </label>
              {field.type === "select" ? (
                <select
                  value={config[field.name] ?? ""}
                  onChange={(e) => setConfig({ ...config, [field.name]: e.target.value })}
                >
                  {field.options.map((o) => (
                    <option key={o} value={o}>
                      {o}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  type={field.secret ? "password" : field.type === "number" ? "number" : "text"}
                  value={config[field.name] ?? ""}
                  onChange={(e) => setConfig({ ...config, [field.name]: e.target.value })}
                />
              )}
              {field.help && <div className="small muted">{field.help}</div>}
            </div>
          ))}
          <div className="toolbar">
            <button onClick={create} disabled={busy === "create"}>
              {busy === "create" ? "Connecting…" : "Create connection"}
            </button>
            <button className="ghost" onClick={() => setSelected(null)}>
              Cancel
            </button>
          </div>
          <p className="small muted">
            Leave credentials blank to use demo mode — the connector returns
            synthetic records so you can exercise the whole pipeline offline.
          </p>
        </div>
      )}
    </>
  );
}

function UploadCard({
  onDone,
  onError,
}: {
  onDone: (message: string) => void;
  onError: (message: string) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<any>(null);
  const [busy, setBusy] = useState(false);

  const doPreview = async (f: File) => {
    try {
      setBusy(true);
      const form = new FormData();
      form.append("file", f);
      setPreview(await api.upload<any>("/sources/upload/preview", form));
    } catch (e: any) {
      onError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const doUpload = async () => {
    if (!file) return;
    try {
      setBusy(true);
      const form = new FormData();
      form.append("file", file);
      form.append("mapping_json", JSON.stringify(preview?.mapping || {}));
      form.append("run_pipeline", "true");
      const res = await api.upload<any>("/sources/upload", form);
      onDone(
        `Ingested ${res.rows_valid} of ${res.rows_read} rows (${res.rows_duplicate} duplicate, ${res.rows_invalid} invalid).` +
          (res.open_conflicts
            ? ` ${res.open_conflicts} conflicts need review.`
            : "")
      );
      setFile(null);
      setPreview(null);
    } catch (e: any) {
      onError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card">
      <h2>Manual upload</h2>
      <p className="hint">
        Drop a CSV or Excel file. Columns are detected automatically and shown
        before anything is ingested.
      </p>
      <div className="row">
        <input
          type="file"
          accept=".csv,.tsv,.xlsx,.xls"
          onChange={(e) => {
            const f = e.target.files?.[0] || null;
            setFile(f);
            setPreview(null);
            if (f) doPreview(f);
          }}
        />
        <button onClick={doUpload} disabled={!file || busy}>
          {busy ? "Working…" : "Ingest and run pipeline"}
        </button>
      </div>

      {preview && (
        <div style={{ marginTop: 14 }}>
          <h3>
            Detected mapping — {preview.rows_detected} rows
            {preview.rows_invalid ? `, ${preview.rows_invalid} invalid` : ""}
          </h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>LeadSense field</th>
                  <th>Source column</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(preview.mapping as Record<string, string>).map(
                  ([field, column]) => (
                    <tr key={field}>
                      <td className="mono">{field}</td>
                      <td>{column}</td>
                    </tr>
                  )
                )}
              </tbody>
            </table>
          </div>
          {preview.unmapped_headers?.length > 0 && (
            <p className="small muted">
              Unmapped columns kept in the raw payload:{" "}
              {preview.unmapped_headers.join(", ")}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
