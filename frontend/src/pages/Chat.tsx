import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { ApiError, errorMessage } from "../api/client";
import {
  ChatApi,
  validId,
  type Capabilities,
  type Conversation,
  type Detail,
} from "../chat/api";
import { Markdown } from "../chat/Markdown";
import { CopyButton } from "../chat/CopyButton";
import {
  Attachments,
  ImagePreview,
  type Attachment,
} from "../chat/Attachments";
import { downloadPdf } from "../studio/download";

const failureText: Record<string, string> = {
  timeout: "The answer timed out. Your question was saved.",
  interrupted: "This request was interrupted. No answer was saved.",
  unavailable: "Answers were unavailable for this question.",
  rate_limited: "The answer service was busy. No answer was saved.",
  empty_response: "The answer service returned no text.",
  provider_failure: "An answer could not be completed.",
  cancelled: "This request was cancelled.",
};
function friendly(error: unknown) {
  if (error instanceof ApiError && error.status === 404)
    return "This conversation is not available.";
  if (error instanceof ApiError && error.status === 409)
    return "A question may already be processing, or the request has changed. Refresh the conversation and try again.";
  return errorMessage(error);
}
function mergeDetails(
  previous: Detail | null,
  fresh: Detail,
  older: boolean,
): Detail {
  if (!previous || previous.conversation.id !== fresh.conversation.id)
    return fresh;
  const keep = older
    ? previous.messages
    : previous.messages.filter(
        (m) => m.sequence < (fresh.messages[0]?.sequence || Infinity),
      );
  const messages = [
    ...new Map([...keep, ...fresh.messages].map((m) => [m.id, m])).values(),
  ].sort((a, b) => a.sequence - b.sequence);
  const requests = [
    ...new Map(
      [...previous.requests, ...fresh.requests].map((q) => [q.id, q]),
    ).values(),
  ];
  return {
    ...fresh,
    messages,
    requests,
    has_older: older ? fresh.has_older : previous.has_older && fresh.has_older,
  };
}
export default function Chat() {
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const { client } = useAuth();
  const api = useMemo(() => new ChatApi(client), [client]);
  const selected = useRef(conversationId);
  selected.current = conversationId;
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [total, setTotal] = useState(0);
  const [listBusy, setListBusy] = useState(false);
  const [listError, setListError] = useState("");
  const listVersion = useRef(0);
  const [cap, setCap] = useState<Capabilities | null>(null);
  const [capError, setCapError] = useState("");
  const [data, setData] = useState<Detail | null>(null);
  const [loading, setLoading] = useState(false);
  const detailVersion = useRef(0);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [pollFailed, setPollFailed] = useState(false);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [attached, setAttached] = useState<Attachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const attachmentVersion = useRef(0);
  const [exporting, setExporting] = useState(false);
  const sendGuard = useRef(false);
  const attempt = useRef<{
    id: string;
    conversation: string;
    content: string;
    attachmentKey: string;
  } | null>(null);
  const [creating, setCreating] = useState(false);
  const createGuard = useRef(false);
  const creationId = useRef<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const historyToggle = useRef<HTMLButtonElement>(null);
  const [renaming, setRenaming] = useState(false);
  const [title, setTitle] = useState("");
  const [editing, setEditing] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);
  const loadList = useCallback(
    async (offset = 0) => {
      const version = ++listVersion.current;
      setListBusy(true);
      try {
        const page = await api.list(offset);
        if (version !== listVersion.current) return;
        setConversations((old) =>
          offset
            ? [
                ...new Map(
                  [...old, ...page.items].map((c) => [c.id, c]),
                ).values(),
              ]
            : page.items,
        );
        setTotal(page.total);
        setListError("");
      } catch (cause) {
        if (version === listVersion.current) setListError(friendly(cause));
      } finally {
        if (version === listVersion.current) setListBusy(false);
      }
    },
    [api],
  );
  const loadDetail = useCallback(
    async (id: string, before?: number) => {
      const version = ++detailVersion.current;
      const fresh = await api.get(id, before);
      if (selected.current === id && version === detailVersion.current) {
        setData((old) => mergeDetails(old, fresh, !!before));
        setPollFailed(false);
      }
      return fresh;
    },
    [api],
  );
  const loadCapabilities = useCallback(async () => {
    try {
      setCap(await api.capabilities());
      setCapError("");
    } catch (cause) {
      setCapError(friendly(cause));
    }
  }, [api]);
  useEffect(() => {
    void loadList();
    void loadCapabilities();
  }, [loadList, loadCapabilities]);
  useEffect(() => {
    let active = true;
    setData(null);
    setError("");
    setNotice("");
    setDraft("");
    setAttached([]);
    attachmentVersion.current++;
    setUploading(false);
    setRenaming(false);
    setPollFailed(false);
    detailVersion.current++;
    if (!conversationId) {
      setLoading(false);
      return;
    }
    if (!validId(conversationId)) {
      setError("This conversation is not available.");
      setLoading(false);
      return;
    }
    setLoading(true);
    void loadDetail(conversationId)
      .catch((cause) => {
        if (active) setError(friendly(cause));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [conversationId, loadDetail]);
  const pending = !!data?.requests.some((q) => q.status === "pending");
  useEffect(() => {
    if (!conversationId || !cap?.attachments_available) return;
    let active = true;
    const version = attachmentVersion.current;
    void client
      .request(`/conversations/${conversationId}/attachments`)
      .then((value) => {
        if (
          active &&
          version === attachmentVersion.current &&
          Array.isArray(value)
        )
          setAttached(value as Attachment[]);
      })
      .catch(() => {
        /* Uploads still report their own errors. */
      });
    return () => {
      active = false;
    };
  }, [client, conversationId, cap?.attachments_available]);
  useEffect(() => {
    if (!conversationId || !pending || pollFailed) return;
    const timer = setInterval(() => {
      void loadDetail(conversationId).catch((cause) => {
        if (selected.current === conversationId) {
          setError(friendly(cause));
          setPollFailed(true);
        }
      });
    }, 2000);
    return () => clearInterval(timer);
  }, [conversationId, pending, pollFailed, loadDetail]);
  useEffect(() => {
    const focus = () => {
      void loadList();
      if (selected.current && validId(selected.current))
        void loadDetail(selected.current).catch(() => {});
    };
    window.addEventListener("focus", focus);
    return () => window.removeEventListener("focus", focus);
  }, [loadList, loadDetail]);
  useEffect(() => {
    if (sending || pending)
      bottom.current?.scrollIntoView?.({ block: "nearest" });
  }, [data?.messages.length, sending, pending]);
  async function createConversation() {
    if (createGuard.current) return;
    createGuard.current = true;
    setCreating(true);
    setListError("");
    creationId.current ||= crypto.randomUUID();
    try {
      const c = await api.create(creationId.current);
      creationId.current = null;
      setHistoryOpen(false);
      navigate(`/app/chat/${c.id}`);
      await loadList();
    } catch (cause) {
      setListError(friendly(cause));
    } finally {
      createGuard.current = false;
      setCreating(false);
    }
  }
  async function refresh() {
    setError("");
    void loadCapabilities();
    void loadList();
    if (!conversationId || !validId(conversationId)) return;
    setLoading(true);
    try {
      await loadDetail(conversationId);
    } catch (cause) {
      setError(friendly(cause));
    } finally {
      setLoading(false);
    }
  }
  async function send(event: FormEvent) {
    event.preventDefault();
    const content = draft.trim();
    const id = conversationId;
    if (
      !id ||
      !content ||
      !cap?.available ||
      pending ||
      uploading ||
      sendGuard.current
    )
      return;
    sendGuard.current = true;
    setSending(true);
    setError("");
    setNotice("");
    if (
      !attempt.current ||
      attempt.current.conversation !== id ||
      attempt.current.content !== content ||
      attempt.current.attachmentKey !== attached.map((a) => a.id).join(",")
    )
      attempt.current = {
        id: crypto.randomUUID(),
        conversation: id,
        content,
        attachmentKey: attached.map((a) => a.id).join(","),
      };
    const question = attempt.current;
    try {
      await api.send(
        id,
        question.id,
        content,
        cap.timeout_seconds,
        attached.map((a) => a.id),
      );
      const fresh = await loadDetail(id);
      if (
        selected.current === id &&
        fresh.requests.some((q) => q.id === question.id)
      ) {
        setDraft("");
        setAttached([]);
        attempt.current = null;
      }
      void loadList();
    } catch (cause) {
      if (selected.current !== id) return;
      try {
        const fresh = await loadDetail(id);
        const saved = fresh.requests.find((q) => q.id === question.id);
        if (saved) {
          setDraft("");
          setAttached([]);
          attempt.current = null;
          setError("");
          if (saved.status === "succeeded")
            setNotice(
              "Your saved answer was recovered after a connection interruption.",
            );
          if (saved.status === "pending")
            setNotice("Your question was saved and is still processing.");
          return;
        }
      } catch {
        /* Keep the draft and request ID for an explicit safe retry. */
      }
      if (selected.current === id) setError(friendly(cause));
    } finally {
      sendGuard.current = false;
      setSending(false);
    }
  }
  async function rename(event: FormEvent) {
    event.preventDefault();
    if (!conversationId || !title.trim() || editing) return;
    const id = conversationId;
    setEditing(true);
    setError("");
    try {
      await api.rename(id, title.trim());
      if (selected.current === id) {
        setRenaming(false);
        await loadDetail(id);
      }
      void loadList();
    } catch (cause) {
      if (selected.current === id) setError(friendly(cause));
    } finally {
      setEditing(false);
    }
  }
  async function remove() {
    if (
      !data ||
      editing ||
      !window.confirm(
        "Remove this conversation from your history? It will no longer be available in your workspace.",
      )
    )
      return;
    const id = data.conversation.id;
    setEditing(true);
    setError("");
    try {
      await api.remove(id);
      if (selected.current === id) navigate("/app/chat", { replace: true });
      void loadList();
    } catch (cause) {
      if (selected.current === id) setError(friendly(cause));
    } finally {
      setEditing(false);
    }
  }
  async function exportPdf(messageId?: string) {
    if (!conversationId || exporting) return;
    const id = conversationId;
    setExporting(true);
    setError("");
    try {
      const result = await downloadPdf(
        client,
        `/conversations/${id}/export`,
        messageId ? { message_id: messageId } : {},
      );
      if (selected.current === id)
        setNotice(`PDF downloaded: ${result.pages} pages.`);
    } catch (cause) {
      if (selected.current === id) setError(friendly(cause));
    } finally {
      setExporting(false);
    }
  }
  return (
    <main id="main-content" tabIndex={-1} className="chat-workspace">
      <div className="chat-mobile-toolbar">
        <h1>Study chat</h1>
        <button
          ref={historyToggle}
          type="button"
          aria-controls="conversation-history"
          aria-expanded={historyOpen}
          onClick={() => setHistoryOpen(!historyOpen)}
        >
          Conversations {historyOpen ? "−" : "+"}
        </button>
      </div>
      <aside
        id="conversation-history"
        className={historyOpen ? "chat-history is-open" : "chat-history"}
        onKeyDown={(e) => {
          if (e.key === "Escape" && historyOpen) {
            setHistoryOpen(false);
            historyToggle.current?.focus();
          }
        }}
      >
        <div className="history-heading">
          <p className="eyebrow">YOUR CONVERSATIONS</p>
          <button
            className="button button-full"
            disabled={creating}
            onClick={createConversation}
          >
            {creating ? "Creating…" : "New conversation"}
            <span aria-hidden="true">＋</span>
          </button>
        </div>
        {listError && (
          <p role="alert" className="error-banner">
            {listError}
            <button
              className="inline-retry"
              onClick={() => {
                void loadList();
              }}
            >
              Retry history
            </button>
          </p>
        )}
        <nav aria-label="Conversation history">
          {conversations.map((c) => (
            <Link
              key={c.id}
              to={`/app/chat/${c.id}`}
              className={
                c.id === conversationId
                  ? "conversation-link active"
                  : "conversation-link"
              }
              aria-current={c.id === conversationId ? "page" : undefined}
              onClick={() => setHistoryOpen(false)}
            >
              <span>{c.title}</span>
              <small>
                {new Date(c.updated_at).toLocaleDateString(undefined, {
                  month: "short",
                  day: "numeric",
                })}
              </small>
            </Link>
          ))}
        </nav>
        {!listBusy && !conversations.length && !listError && (
          <p className="history-empty">Your conversations will appear here.</p>
        )}
        {listBusy && (
          <p role="status" className="history-empty">
            Loading conversations…
          </p>
        )}
        {conversations.length < total && (
          <button
            className="history-more"
            disabled={listBusy}
            onClick={() => {
              void loadList(conversations.length);
            }}
          >
            Load more conversations
          </button>
        )}
      </aside>
      <section className="chat-panel" aria-label="Study conversation">
        <header className="chat-heading">
          <div>
            <p className="eyebrow">A clearer way to learn</p>
            <h1>{data?.conversation.title || "Study chat"}</h1>
          </div>
          <div className="chat-actions">
            <button
              type="button"
              onClick={() => {
                void refresh();
              }}
              disabled={loading}
            >
              Refresh
            </button>
            {data && (
              <>
                <button
                  type="button"
                  disabled={exporting || !data.messages.length}
                  onClick={() => {
                    void exportPdf();
                  }}
                >
                  {exporting ? "Preparing PDF…" : "Export conversation PDF"}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setTitle(data.conversation.title);
                    setRenaming(true);
                  }}
                  disabled={editing}
                >
                  Rename
                </button>
                <button
                  type="button"
                  onClick={() => {
                    void remove();
                  }}
                  disabled={editing}
                >
                  Remove
                </button>
              </>
            )}
          </div>
        </header>
        {renaming && (
          <form onSubmit={rename} className="rename-form">
            <label htmlFor="conversation-title">Conversation title</label>
            <input
              id="conversation-title"
              maxLength={80}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
            />
            <button type="submit" disabled={editing || !title.trim()}>
              Save title
            </button>
            <button type="button" onClick={() => setRenaming(false)}>
              Cancel
            </button>
          </form>
        )}
        {cap?.mode === "verification" && (
          <p className="chat-mode test-mode">
            Verification mode: responses are scripted test fixtures, not
            academic AI guidance.
          </p>
        )}
        {cap && !cap.available && (
          <p className="chat-mode">
            AI answers aren’t connected yet. You can still create, rename and
            remove conversations.
          </p>
        )}
        {capError && (
          <p role="alert" className="error-banner">
            {capError}
            <button
              className="inline-retry"
              onClick={() => {
                void loadCapabilities();
              }}
            >
              Retry connection
            </button>
          </p>
        )}
        {notice && (
          <p className="notice chat-notice" role="status">
            {notice}
          </p>
        )}
        {error && (
          <p className="error-banner" role="alert">
            {error}
            <button
              className="inline-retry"
              onClick={() => {
                void refresh();
              }}
            >
              Check saved messages
            </button>
          </p>
        )}
        <div className="chat-messages" aria-busy={loading}>
          {loading && !data && <p role="status">Loading this conversation…</p>}
          {!conversationId && (
            <div className="chat-empty">
              <span aria-hidden="true">✦</span>
              <p className="eyebrow">One question at a time</p>
              <h2>
                Make room for
                <br />
                <em>understanding.</em>
              </h2>
              <p>
                Keep your questions and follow-ups together in a personal
                conversation.
              </p>
              <button
                className="button"
                disabled={creating}
                onClick={createConversation}
              >
                Create a conversation <span aria-hidden="true">↗</span>
              </button>
            </div>
          )}
          {data && !data.messages.length && (
            <div className="chat-empty">
              <span aria-hidden="true">?</span>
              <h2>
                Where would you
                <br />
                like to begin?
              </h2>
              <p>
                Ask a question, include the values you know, and say what you’d
                like to understand.
              </p>
            </div>
          )}
          {data?.has_older && (
            <button
              type="button"
              className="load-older"
              disabled={loading}
              onClick={() => {
                if (conversationId && data.messages[0]) {
                  setLoading(true);
                  void loadDetail(conversationId, data.messages[0].sequence)
                    .catch((cause) => setError(friendly(cause)))
                    .finally(() => setLoading(false));
                }
              }}
            >
              Load earlier messages
            </button>
          )}
          {data?.messages.map((m) => {
            const q = data.requests.find((q) => q.id === m.request_id);
            return (
              <article
                key={m.id}
                className={`chat-message ${m.role}`}
                aria-label={
                  m.role === "user" ? "Your question" : "EduMind response"
                }
              >
                <div className="message-meta">
                  <strong>
                    {m.role === "user"
                      ? "You"
                      : m.provider === "verification"
                        ? "Verification response"
                        : "EduMind"}
                  </strong>
                  <CopyButton
                    text={m.content}
                    label={m.role === "user" ? "Copy question" : "Copy answer"}
                  />
                  {m.role === "assistant" && (
                    <button
                      type="button"
                      disabled={exporting}
                      onClick={() => {
                        void exportPdf(m.id);
                      }}
                    >
                      Download answer PDF
                    </button>
                  )}
                </div>
                {!!m.attachments?.length && (
                  <ul
                    className="message-attachments"
                    aria-label="Attached files"
                  >
                    {m.attachments.map((a) => (
                      <li key={a.id}>
                        <span>{a.filename}</span>
                        {a.mime.startsWith("image/") && (
                          <ImagePreview
                            client={client}
                            conversationId={conversationId!}
                            item={a}
                          />
                        )}
                      </li>
                    ))}
                  </ul>
                )}
                {m.role === "user" ? (
                  <p className="question-text">{m.content}</p>
                ) : (
                  <>
                    <Markdown text={m.content} />
                    <p className="source-note">
                      No reference sources are attached to this response.
                    </p>
                  </>
                )}
                {m.role === "user" && q?.status === "failed" && (
                  <p className="failed-answer">
                    {failureText[q.error_code || ""] ||
                      "No answer was saved for this question."}{" "}
                    You can start a new question below.
                  </p>
                )}
              </article>
            );
          })}
          {(pending || sending) && (
            <p className="chat-pending" role="status">
              Working on your question…
            </p>
          )}
          <div ref={bottom} />
        </div>
        {data && (
          <form className="chat-composer" onSubmit={send}>
            <Attachments
              key={conversationId}
              client={client}
              conversationId={conversationId!}
              available={!!cap?.attachments_available}
              disabled={sending || pending}
              value={attached}
              onChange={(items) => {
                if (selected.current === conversationId) {
                  attachmentVersion.current++;
                  setAttached(items);
                }
              }}
              onBusy={(busy) => {
                if (selected.current === conversationId) {
                  if (busy) attachmentVersion.current++;
                  setUploading(busy);
                }
              }}
            />
            <label htmlFor="academic-question">Your question</label>
            <textarea
              id="academic-question"
              rows={3}
              maxLength={4000}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="What would you like to understand?"
              disabled={sending || pending || !cap?.available}
            />
            <div className="composer-bottom">
              <small>
                {Array.from(draft).length}/4000 · Include units and context.
              </small>
              <button
                type="submit"
                className="button"
                disabled={
                  sending ||
                  pending ||
                  uploading ||
                  !cap?.available ||
                  !draft.trim()
                }
              >
                {sending || pending ? "Waiting…" : "Send question"}
                <span aria-hidden="true">↑</span>
              </button>
            </div>
          </form>
        )}
      </section>
    </main>
  );
}
