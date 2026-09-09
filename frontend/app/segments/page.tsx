"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { RequireSession, Badge, Notice, Empty } from "@/components/Ui";

export default function SegmentsPage() {
  return (
    <RequireSession>
      <Segments />
    </RequireSession>
  );
}

function Segments() {
  const [existing, setExisting] = useState<any[]>([]);
  const [preview, setPreview] = useState<any>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    min_score: 70,
    group_by: "persona",
    min_size: 2,
  });

  const load = () =>
    api.get<any[]>("/leads/segments/list").then(setExisting).catch((e) => setError(e.message));

  useEffect(() => {
    load();
  }, []);

  const call = async (path: string, persist: boolean) => {
    try {
      setBusy(true);
      setError("");
      const res = await api.post<any>(path, { name: "segment", ...form });
      setPreview(res);
      if (persist) {
        setMessage(
          `${res.segments.filter((s: any) => s.viable).length} segments created.`
        );
        load();
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="page-head">
        <h1>Segments</h1>
        <p>
          Group qualified leads into audiences a campaign can target. Segments below
          the minimum size are shown but not created — a segment of one is a
          personal email, not a campaign.
        </p>
      </div>

      <Notice kind="error">{error}</Notice>
      <Notice kind="success">{message}</Notice>

      <div className="card">
        <h2>Build a segment</h2>
        <div className="row">
          <div>
            <label>Minimum score</label>
            <input
              type="number"
              value={form.min_score}
              onChange={(e) => setForm({ ...form, min_score: Number(e.target.value) })}
            />
          </div>
          <div>
            <label>Group by</label>
            <select
              value={form.group_by}
              onChange={(e) => setForm({ ...form, group_by: e.target.value })}
            >
              <option value="persona">Persona</option>
              <option value="industry">Industry</option>
              <option value="seniority">Seniority</option>
            </select>
          </div>
          <div>
            <label>Minimum size</label>
            <input
              type="number"
              value={form.min_size}
              onChange={(e) => setForm({ ...form, min_size: Number(e.target.value) })}
            />
          </div>
          <button
            className="secondary"
            disabled={busy}
            onClick={() => call("/leads/segments/preview", false)}
          >
            Preview
          </button>
          <button disabled={busy} onClick={() => call("/leads/segments", true)}>
            Create
          </button>
        </div>

        {preview && (
          <div style={{ marginTop: 14 }}>
            <h3>{preview.qualified_leads} qualified leads</h3>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Segment</th>
                    <th>Size</th>
                    <th>Average score</th>
                    <th>Viable</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.segments.map((segment: any) => (
                    <tr key={segment.name}>
                      <td>
                        <strong>{segment.name}</strong>
                        <div className="small muted">{segment.explanation}</div>
                      </td>
                      <td>{segment.size}</td>
                      <td>{segment.average_score}</td>
                      <td>
                        <Badge kind={segment.viable ? "ok" : "neutral"}>
                          {segment.viable ? "viable" : "too small"}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      <div className="card">
        <h2>Saved segments</h2>
        {existing.length === 0 ? (
          <Empty>No segments yet.</Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Size</th>
                  <th>Rules</th>
                  <th>Id</th>
                </tr>
              </thead>
              <tbody>
                {existing.map((segment) => (
                  <tr key={segment.id}>
                    <td>
                      <strong>{segment.name}</strong>
                      <div className="small muted">{segment.description}</div>
                    </td>
                    <td>{segment.size}</td>
                    <td className="small mono">{JSON.stringify(segment.rules)}</td>
                    <td className="small mono muted">{segment.id.slice(0, 8)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
