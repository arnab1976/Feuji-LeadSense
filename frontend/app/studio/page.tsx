"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { GeneratedEmail } from "@/lib/types";
import { RequireSession, Badge, Notice, Empty, verdictKind } from "@/components/Ui";

export default function StudioPage() {
  return (
    <RequireSession>
      <Studio />
    </RequireSession>
  );
}

function Studio() {
  const [emails, setEmails] = useState<GeneratedEmail[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [open, setOpen] = useState<GeneratedEmail | null>(null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState("");

  const load = () =>
    api
      .get<GeneratedEmail[]>("/emails")
      .then((rows) => {
        setEmails(rows);
        setSelected(
          rows
            .filter((e) => e.compliance?.verdict !== "BLOCK" && e.status === "pending_approval")
            .map((e) => e.id)
        );
      })
      .catch((e) => setError(e.message));

  useEffect(() => {
    load();
  }, []);

  const approve = async () => {
    try {
      setBusy("approve");
      setError("");
      const res = await api.post<any>("/emails/approve", {
        email_ids: selected,
        decision: "approved",
        justification: "Reviewed in the email studio",
      });
      setMessage(`${res.approved} emails approved by ${res.approver}.`);
      load();
    } catch (e: any) {
      setError(
        e.message +
          (e.detail?.blocked
            ? ` (${e.detail.blocked.length} blocked by compliance)`
            : "")
      );
    } finally {
      setBusy("");
    }
  };

  const send = async () => {
    try {
      setBusy("send");
      const res = await api.post<any>("/emails/send", { email_ids: [] });
      setMessage(
        `${res.sent} sent, ${res.failed} failed, ${res.skipped} skipped without approval.`
      );
      load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  };

  const saveEdit = async () => {
    if (!open) return;
    try {
      setBusy("edit");
      await api.patch(`/emails/${open.id}`, { body: draft });
      setMessage("Draft updated and re-checked for compliance.");
      setOpen(null);
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
        <h1>Email studio</h1>
        <p>
          Review, edit and approve. Blocked drafts cannot be approved at all — the
          API refuses, rather than relying on a reviewer noticing.
        </p>
      </div>

      <Notice kind="error">{error}</Notice>
      <Notice kind="success">{message}</Notice>

      <div className="toolbar">
        <span className="small muted">
          {selected.length} of {emails.length} selected
        </span>
        <span className="spacer" />
        <button className="secondary" disabled={!selected.length || busy === "approve"} onClick={approve}>
          Approve selected
        </button>
        <button disabled={busy === "send"} onClick={send}>
          {busy === "send" ? "Sending…" : "Send approved"}
        </button>
      </div>

      {emails.length === 0 ? (
        <div className="card">
          <Empty>No drafts yet. Generate emails from a campaign first.</Empty>
        </div>
      ) : (
        emails.map((email) => (
          <div className="card" key={email.id}>
            <div className="toolbar" style={{ marginBottom: 8 }}>
              <input
                type="checkbox"
                style={{ width: "auto" }}
                disabled={email.compliance?.verdict === "BLOCK"}
                checked={selected.includes(email.id)}
                onChange={(e) =>
                  setSelected(
                    e.target.checked
                      ? [...selected, email.id]
                      : selected.filter((id) => id !== email.id)
                  )
                }
              />
              <strong>{email.lead_name}</strong>
              <span className="small muted">{email.lead_email}</span>
              <Badge kind={verdictKind(email.compliance?.verdict)}>
                {email.compliance?.verdict?.replace(/_/g, " ") || "unchecked"}
              </Badge>
              <Badge kind="neutral">{email.status}</Badge>
              {email.edited_by_human && <Badge kind="agent">human edited</Badge>}
              <span className="spacer" />
              <span className="small muted mono">
                grounded {email.groundedness.toFixed(2)} · {email.tokens} tokens · $
                {email.cost_usd.toFixed(4)}
              </span>
              <button
                className="ghost small"
                onClick={() => {
                  setOpen(email);
                  setDraft(email.body);
                }}
              >
                Edit
              </button>
            </div>

            <div className="grid cols-2">
              <div>
                <h3>Subject variants</h3>
                {email.subject_variants.map((subject, i) => (
                  <div key={i} className="small" style={{ marginBottom: 4 }}>
                    <Badge kind={i === email.selected_variant ? "ok" : "neutral"}>
                      {String.fromCharCode(65 + i)}
                    </Badge>{" "}
                    {subject}
                  </div>
                ))}
                <h3 style={{ marginTop: 12 }}>Body</h3>
                <div className="pre">{email.body}</div>
                {email.grounding.length > 0 && (
                  <p className="small muted" style={{ marginTop: 8 }}>
                    Grounded in:{" "}
                    {email.grounding.map((g) => g.title).join(", ")}
                  </p>
                )}
              </div>
              <div>
                <h3>Compliance checks</h3>
                {(email.compliance?.checks || []).map((check) => (
                  <div key={check.key} style={{ marginBottom: 6 }}>
                    <Badge kind={check.pass ? "ok" : "bad"}>
                      {check.pass ? "pass" : "fail"}
                    </Badge>{" "}
                    <strong className="small">{check.label}</strong>
                    <div className="small muted">{check.reason}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ))
      )}

      {open && (
        <div className="card">
          <div className="toolbar">
            <h2 style={{ margin: 0 }}>Editing draft for {open.lead_name}</h2>
            <span className="spacer" />
            <button className="ghost small" onClick={() => setOpen(null)}>
              Cancel
            </button>
          </div>
          <p className="hint">
            Saving re-runs the compliance checks — an edited body has not been
            checked yet.
          </p>
          <textarea rows={14} value={draft} onChange={(e) => setDraft(e.target.value)} />
          <div className="toolbar" style={{ marginTop: 10 }}>
            <button onClick={saveEdit} disabled={busy === "edit"}>
              Save and re-check
            </button>
          </div>
        </div>
      )}
    </>
  );
}
