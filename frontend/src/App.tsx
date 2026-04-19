import { useCallback, useEffect, useMemo, useState } from "react";

const LS_USER = "scholarship_test_user_id";
const LS_ADMIN = "scholarship_test_admin_token";

const DEFAULT_PROFILE = `{
  "education_level": "undergraduate",
  "field_of_study": "engineering",
  "state": "KA",
  "keywords": ["merit", "engineering", "STEM"]
}`;

const SAMPLE_IMPORT = {
  items: [
    {
      source: "seed",
      source_url: "https://example.org/scholarships/ui-sample-merit",
      title: "Merit scholarship for engineering students",
      summary: "Open to undergraduate engineering students with strong academics.",
      eligibility_text:
        "Applicants must be pursuing B.Tech or BE in any discipline. Minimum 75% marks.",
      amount: "₹50,000",
      deadline: "2026-12-31",
      tags: ["engineering", "undergraduate"],
    },
    {
      source: "seed",
      source_url: "https://example.org/scholarships/ui-sample-stem",
      title: "Women in STEM grant",
      summary: "Supporting women students in science and technology fields.",
      eligibility_text:
        "Female students enrolled in STEM programs at recognized institutions.",
      amount: "₹30,000",
      deadline: "2026-08-15",
      tags: ["women", "stem", "science"],
    },
  ],
};

function apiBase(): string {
  return import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
}

async function apiFetch(
  path: string,
  options: RequestInit & { adminToken?: string } = {},
): Promise<Response> {
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type") && options.body && typeof options.body === "string") {
    headers.set("Content-Type", "application/json");
  }
  if (options.adminToken) {
    headers.set("X-Admin-Token", options.adminToken);
  }
  const { adminToken, ...rest } = options;
  return fetch(`${apiBase()}${path}`, { ...rest, headers });
}

type ScholarshipRow = {
  id: string;
  title: string;
  deadline: string | null;
  source_url: string;
};

type MatchItem = {
  score: number;
  scholarship: ScholarshipRow;
  reasons: { type: string; detail: string; weight: number }[];
};

export default function App() {
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [profileJson, setProfileJson] = useState(DEFAULT_PROFILE);
  const [userId, setUserId] = useState(() => localStorage.getItem(LS_USER) ?? "");
  const [adminToken, setAdminToken] = useState(
    () => localStorage.getItem(LS_ADMIN) ?? "dev-admin-change-me",
  );
  const [scholarships, setScholarships] = useState<ScholarshipRow[]>([]);
  const [schTotal, setSchTotal] = useState(0);
  const [matches, setMatches] = useState<MatchItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [searchText, setSearchText] = useState("");

  useEffect(() => {
    localStorage.setItem(LS_ADMIN, adminToken);
  }, [adminToken]);

  const showError = useCallback((msg: string) => {
    setError(msg);
    setMessage(null);
  }, []);

  const showOk = useCallback((msg: string) => {
    setMessage(msg);
    setError(null);
  }, []);

  const pullScholarships = useCallback(async (): Promise<{
    items: ScholarshipRow[];
    total: number;
  } | null> => {
    const res = await apiFetch("/scholarships?skip=0&limit=100");
    if (!res.ok) {
      showError(await res.text());
      return null;
    }
    return (await res.json()) as { items: ScholarshipRow[]; total: number };
  }, [showError]);

  const createUser = async () => {
    setBusy(true);
    setError(null);
    try {
      let profile: Record<string, unknown>;
      try {
        profile = JSON.parse(profileJson) as Record<string, unknown>;
      } catch {
        showError("Profile must be valid JSON");
        setBusy(false);
        return;
      }
      const res = await apiFetch("/users", {
        method: "POST",
        body: JSON.stringify({ profile }),
      });
      if (!res.ok) {
        showError(await res.text());
        setBusy(false);
        return;
      }
      const data = (await res.json()) as { id: string };
      setUserId(data.id);
      localStorage.setItem(LS_USER, data.id);
      showOk(`User created: ${data.id}`);
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const uploadResume = async (file: File | null) => {
    if (!userId) {
      showError("Create or set a user id first");
      return;
    }
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await apiFetch(`/users/${userId}/resume`, {
        method: "POST",
        body: fd,
      });
      if (!res.ok) {
        showError(await res.text());
        setBusy(false);
        return;
      }
      showOk("Resume uploaded and parsed");
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const runScrape = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await apiFetch("/admin/scrape/run", {
        method: "POST",
        adminToken,
      });
      if (!res.ok) {
        showError(await res.text());
        setBusy(false);
        return;
      }
      const data = (await res.json()) as {
        inserted: number;
        updated: number;
        fetched_urls: number;
        errors: string[];
      };
      const errStr = data.errors?.length ? data.errors.join("; ") : "none";
      showOk(
        `Scrape: inserted ${data.inserted}, updated ${data.updated}, scraped pages ${data.fetched_urls}. Errors: ${errStr}`,
      );
      const fresh = await pullScholarships();
      if (fresh) {
        setScholarships(fresh.items);
        setSchTotal(fresh.total);
      }
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const importSample = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await apiFetch("/admin/scholarships/import", {
        method: "POST",
        body: JSON.stringify(SAMPLE_IMPORT),
        adminToken,
      });
      if (!res.ok) {
        showError(await res.text());
        setBusy(false);
        return;
      }
      const data = (await res.json()) as { upserted: number };
      showOk(`Imported ${data.upserted} scholarships`);
      const fresh = await pullScholarships();
      if (fresh) {
        setScholarships(fresh.items);
        setSchTotal(fresh.total);
      }
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const loadScholarships = async () => {
    setBusy(true);
    setError(null);
    try {
      const data = await pullScholarships();
      if (data) {
        setScholarships(data.items);
        setSchTotal(data.total);
        showOk(`Loaded ${data.items.length} of ${data.total} scholarships`);
      }
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const loadMatches = async () => {
    if (!userId) {
      showError("Create or set a user id first");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await apiFetch(`/users/${userId}/matches?limit=50`);
      if (!res.ok) {
        showError(await res.text());
        setBusy(false);
        return;
      }
      const data = (await res.json()) as { items: MatchItem[] };
      setMatches(data.items);
      showOk(`Loaded ${data.items.length} matches`);
    } catch (e) {
      showError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const clearLocalUser = () => {
    setUserId("");
    localStorage.removeItem(LS_USER);
    showOk("Cleared saved user id");
  };

  const filteredScholarships = useMemo(() => {
    const query = searchText.trim().toLowerCase();
    if (!query) {
      return scholarships;
    }
    return scholarships.filter((s) => s.title.toLowerCase().includes(query));
  }, [scholarships, searchText]);

  const topMatches = useMemo(
    () => [...matches].sort((a, b) => b.score - a.score).slice(0, 5),
    [matches],
  );

  const stats = useMemo(
    () => [
      { label: "Total scholarships", value: String(schTotal) },
      { label: "Visible now", value: String(filteredScholarships.length) },
      { label: "Matches", value: String(matches.length) },
      { label: "User ready", value: userId ? "Yes" : "No" },
    ],
    [schTotal, filteredScholarships.length, matches.length, userId],
  );

  const banner = useMemo(() => {
    if (error) {
      return (
        <article className="status status-error">
          <strong>Error</strong>
          <p>{error}</p>
        </article>
      );
    }
    if (message) {
      return (
        <article className="status status-ok">
          <strong>Success</strong>
          <p>{message}</p>
        </article>
      );
    }
    return null;
  }, [error, message]);

  return (
    <main className="container app-shell">
      <header className="hero">
        <div>
          <h1>Scholarship Assistant</h1>
          <p className="hero-sub">
            Scrape scholarship data, create user profiles, and view best matches from one place.
          </p>
        </div>
        <p className="api-base">
          API base: <code>{apiBase()}</code>
        </p>
      </header>
      {banner}

      <section className="stats-grid">
        {stats.map((s) => (
          <article key={s.label} className="stat-card">
            <p>{s.label}</p>
            <h3>{s.value}</h3>
          </article>
        ))}
      </section>

      <section className="card-grid">
        <article>
          <h2>1) User profile</h2>
          <p className="muted">Paste profile JSON and create a user before requesting matches.</p>
          <label>
            Profile JSON
            <textarea
              value={profileJson}
              onChange={(e) => setProfileJson(e.target.value)}
              rows={8}
              className="mono"
            />
          </label>
          <div className="row">
            <button type="button" disabled={busy} onClick={() => void createUser()}>
              {busy ? "Working..." : "Create user"}
            </button>
          </div>
          <label>
            User id (saved in browser)
            <input
              placeholder="Paste user id"
              value={userId}
              onChange={(e) => {
                setUserId(e.target.value);
                localStorage.setItem(LS_USER, e.target.value);
              }}
            />
          </label>
          <button type="button" className="secondary" disabled={busy} onClick={clearLocalUser}>
            Clear saved user id
          </button>
        </article>

        <article>
          <h2>2) Resume</h2>
          <p className="muted">Upload PDF or DOCX resume for smarter matching.</p>
          <input
            type="file"
            accept=".pdf,.docx"
            disabled={busy}
            onChange={(e) => void uploadResume(e.target.files?.[0] ?? null)}
          />
          <h2>3) Admin actions</h2>
          <label>
            X-Admin-Token
            <input
              type="password"
              value={adminToken}
              onChange={(e) => setAdminToken(e.target.value)}
              autoComplete="off"
            />
          </label>
          <div className="row">
            <button type="button" disabled={busy} onClick={() => void runScrape()}>
              Run scrape
            </button>
            <button type="button" className="secondary" disabled={busy} onClick={() => void importSample()}>
              Import sample
            </button>
          </div>
        </article>
      </section>

      <section>
        <h2>4) Scholarships</h2>
        <div className="row">
          <button type="button" disabled={busy} onClick={() => void loadScholarships()}>
            Refresh list
          </button>
          <input
            type="search"
            placeholder="Filter by title"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
          />
        </div>
        <p className="muted">
          Showing <strong>{filteredScholarships.length}</strong> of <strong>{schTotal}</strong>
        </p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Title</th>
                <th>Deadline</th>
                <th>Link</th>
              </tr>
            </thead>
            <tbody>
              {filteredScholarships.map((s) => (
                <tr key={s.id}>
                  <td>{s.title}</td>
                  <td>{s.deadline ?? "—"}</td>
                  <td>
                    <a href={s.source_url} target="_blank" rel="noreferrer">
                      Open
                    </a>
                  </td>
                </tr>
              ))}
              {filteredScholarships.length === 0 ? (
                <tr>
                  <td colSpan={3}>No scholarships found for this filter.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2>5) Matches</h2>
        <div className="row">
          <button type="button" disabled={busy} onClick={() => void loadMatches()}>
            Get matches
          </button>
        </div>
        {topMatches.length > 0 ? (
          <article className="top-matches">
            <h3>Top recommendations</h3>
            <ol>
              {topMatches.map((m) => (
                <li key={m.scholarship.id}>
                  {m.scholarship.title} <strong>({m.score.toFixed(2)})</strong>
                </li>
              ))}
            </ol>
          </article>
        ) : null}
        {matches.map((m) => (
          <details key={m.scholarship.id}>
            <summary>
              <strong>{m.scholarship.title}</strong> - score {m.score.toFixed(2)}
            </summary>
            <ul>
              {m.reasons.map((r, i) => (
                <li key={i}>
                  {r.type}: {r.detail} ({r.weight})
                </li>
              ))}
            </ul>
          </details>
        ))}
      </section>
    </main>
  );
}
