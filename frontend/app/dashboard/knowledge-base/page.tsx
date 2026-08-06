"use client";

import { useEffect, useState } from "react";
import { api, KBArticle, KBAskResponse, User } from "@/lib/api";

export default function KnowledgeBasePage() {
  const [articles, setArticles] = useState<KBArticle[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [activeCategory, setActiveCategory] = useState<string>("");
  const [expanded, setExpanded] = useState<number | null>(null);
  const [user, setUser] = useState<User | null>(null);

  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [answer, setAnswer] = useState<KBAskResponse | null>(null);
  const [error, setError] = useState("");

  const [showAdmin, setShowAdmin] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newCategory, setNewCategory] = useState("General");
  const [newContent, setNewContent] = useState("");
  const [saving, setSaving] = useState(false);

  function load() {
    api<KBArticle[]>("/kb/articles").then(setArticles);
    api<string[]>("/kb/categories").then(setCategories);
  }

  useEffect(() => {
    load();
    api<User>("/me").then(setUser);
  }, []);

  async function ask() {
    if (!question.trim()) return;
    setAsking(true);
    setError("");
    setAnswer(null);
    try {
      const result = await api<KBAskResponse>("/kb/ask", { method: "POST", body: JSON.stringify({ question }) });
      setAnswer(result);
    } catch (err: any) {
      setError(err.message || "Couldn't get an answer right now.");
    } finally {
      setAsking(false);
    }
  }

  async function addArticle() {
    setSaving(true);
    try {
      await api("/kb/articles", {
        method: "POST",
        body: JSON.stringify({ category: newCategory, title: newTitle, content: newContent }),
      });
      setNewTitle(""); setNewContent("");
      load();
    } catch (err: any) {
      alert(err.message || "Couldn't add that article.");
    } finally {
      setSaving(false);
    }
  }

  async function removeArticle(id: number) {
    await api(`/kb/articles/${id}`, { method: "DELETE" });
    load();
  }

  const shown = activeCategory ? articles.filter((a) => a.category === activeCategory) : articles;

  return (
    <div>
      <h1>Knowledge Base</h1>
      <p className="muted">Answers grounded in real documentation about how Riseply actually works — never a guess.</p>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Ask a question</h3>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") ask(); }}
            placeholder="e.g. Can my employer see my Job Buddy chats?"
            style={{ flex: 1 }}
          />
          <button className="btn btn-primary" onClick={ask} disabled={asking || !question.trim()}>
            {asking ? "Asking…" : "Ask"}
          </button>
        </div>

        {error && <p className="error-text">{error}</p>}

        {answer && (
          <div style={{ marginTop: 14 }}>
            <p>{answer.answer}</p>
            {answer.sources.length > 0 && (
              <p className="hint">
                Sources: {answer.sources.map((s) => s.title).join(" · ")}
              </p>
            )}
          </div>
        )}
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
        <button className="btn btn-ghost btn-sm"
                style={!activeCategory ? { background: "var(--accent-soft)", color: "var(--accent-hover)", borderColor: "var(--accent)" } : {}}
                onClick={() => setActiveCategory("")}>
          All
        </button>
        {categories.map((c) => (
          <button key={c} className="btn btn-ghost btn-sm"
                  style={activeCategory === c ? { background: "var(--accent-soft)", color: "var(--accent-hover)", borderColor: "var(--accent)" } : {}}
                  onClick={() => setActiveCategory(c)}>
            {c}
          </button>
        ))}
      </div>

      {shown.map((a) => (
        <div key={a.id} className="card">
          <div className="card-row" style={{ cursor: "pointer" }} onClick={() => setExpanded(expanded === a.id ? null : a.id)}>
            <div>
              <span className="hint">{a.category}</span>
              <h3 style={{ margin: "2px 0 0" }}>{a.title}</h3>
            </div>
            <span className="hint">{expanded === a.id ? "Hide" : "Show"}</span>
          </div>
          {expanded === a.id && <p style={{ marginTop: 10 }}>{a.content}</p>}
          {user?.is_admin && (
            <button className="btn btn-ghost btn-sm" style={{ marginTop: 8 }} onClick={() => removeArticle(a.id)}>
              Remove
            </button>
          )}
        </div>
      ))}

      {user?.is_admin && (
        <div className="card">
          <div className="card-row">
            <h3 style={{ margin: 0 }}>Add an article (admin)</h3>
            <button className="btn btn-ghost btn-sm" onClick={() => setShowAdmin((s) => !s)}>
              {showAdmin ? "Hide" : "Show"}
            </button>
          </div>
          {showAdmin && (
            <div style={{ marginTop: 12 }}>
              <div className="field">
                <label>Category</label>
                <input value={newCategory} onChange={(e) => setNewCategory(e.target.value)} />
              </div>
              <div className="field">
                <label>Title</label>
                <input value={newTitle} onChange={(e) => setNewTitle(e.target.value)} />
              </div>
              <div className="field">
                <label>Content</label>
                <textarea rows={5} value={newContent} onChange={(e) => setNewContent(e.target.value)} />
              </div>
              <button className="btn btn-primary btn-sm" onClick={addArticle}
                      disabled={saving || !newTitle.trim() || !newContent.trim()}>
                {saving ? "Adding…" : "Add article"}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
