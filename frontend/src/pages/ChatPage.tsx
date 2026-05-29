import React, { useState, useEffect, useRef, useCallback } from "react";
import { Navigate } from "react-router-dom";
import { Send, Paperclip } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import Sidebar, { type Session } from "../components/Sidebar";
import MessageBubble, { type Msg } from "../components/MessageBubble";
import UploadModal from "../components/UploadModal";
import HeroEmpty from "../components/HeroEmpty";
import api, { BASE } from "../api/client";

// Stable client-side ID counter for optimistic messages (before server assigns an id)
let _msgCounter = 0;
function clientId() { return --_msgCounter; }

export default function ChatPage() {
  const { user, idleWarning, resetIdleTimer } = useAuth();
  const isAdmin = user?.is_admin ?? false;

  // All hooks are declared unconditionally before any early return
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Now safe to guard with early return
  if (!user) return <Navigate to="/login" replace />;

  const fetchSessions = useCallback(async () => {
    try {
      const { data } = await api.get<Session[]>("/chats");
      setSessions(data);
    } catch { /* network error — keep stale list */ }
  }, []);

  useEffect(() => { fetchSessions(); }, [fetchSessions]);

  const loadSession = useCallback(async (id: number) => {
    setActiveId(id);
    try {
      const { data } = await api.get<{ id: number; title: string; messages: Msg[]; total_messages: number }>(
        `/chats/${id}?limit=100&offset=0`
      );
      setMessages(data.messages);
    } catch { setMessages([]); }
  }, []);

  const newSession = useCallback(async () => {
    const { data } = await api.post<Session>("/chats");
    setSessions((prev) => [data, ...prev]);
    setActiveId(data.id);
    setMessages([]);
  }, []);

  const deleteSession = useCallback(async (id: number) => {
    await api.delete(`/chats/${id}`);
    setSessions((prev) => prev.filter((s) => s.id !== id));
    if (activeId === id) {
      setActiveId(null);
      setMessages([]);
    }
  }, [activeId]);

  const renameSession = useCallback(async (id: number, title: string) => {
    await api.patch(`/chats/${id}`, { title });
    setSessions((prev) => prev.map((s) => (s.id === id ? { ...s, title } : s)));
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = useCallback(async (text?: string) => {
    const content = (text ?? input).trim();
    if (!content || streaming) return;
    setInput("");

    let sessionId = activeId;

    if (!sessionId) {
      const { data } = await api.post<Session>("/chats");
      sessionId = data.id;
      setActiveId(sessionId);
      setSessions((prev) => [data, ...prev]);
    }

    // Optimistic user message with stable client-side id
    const userMsgId = clientId();
    setMessages((prev) => [...prev, { id: userMsgId, role: "user", content }]);

    const asstMsgId = clientId();
    setMessages((prev) => [...prev, { id: asstMsgId, role: "assistant", content: "", streaming: true }]);
    setStreaming(true);

    const token = localStorage.getItem("ir_token");
    let fullContent = "";

    try {
      const resp = await fetch(`${BASE}/api/chats/${sessionId}/messages`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        credentials: "include",   // send httpOnly cookie
        body: JSON.stringify({ message: content }),
      });

      if (!resp.ok) {
        throw new Error(`Server error ${resp.status}`);
      }

      if (!resp.body) throw new Error("No response body");

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        for (const line of chunk.split("\n")) {
          if (!line.startsWith("data:")) continue;
          try {
            const json = JSON.parse(line.slice(5).trim());
            if (json.error) throw new Error(json.error);
            if (json.token) {
              fullContent += json.token;
              setMessages((prev) => {
                const next = [...prev];
                const idx = next.findIndex((m) => m.id === asstMsgId);
                if (idx !== -1) next[idx] = { id: asstMsgId, role: "assistant", content: fullContent, streaming: true };
                return next;
              });
            }
            if (json.done) {
              setMessages((prev) => {
                const next = [...prev];
                const idx = next.findIndex((m) => m.id === asstMsgId);
                if (idx !== -1) next[idx] = {
                  id: json.message_id ?? asstMsgId,
                  role: "assistant",
                  content: fullContent,
                  sources: json.sources ?? [],
                  streaming: false,
                };
                return next;
              });
            }
          } catch (parseErr) {
            if (parseErr instanceof Error && parseErr.message !== "SyntaxError") throw parseErr;
          }
        }
      }
    } catch (err) {
      const errText = err instanceof Error ? err.message : "Unknown error";
      setMessages((prev) => {
        const next = [...prev];
        const idx = next.findIndex((m) => m.id === asstMsgId);
        if (idx !== -1) next[idx] = { id: asstMsgId, role: "assistant", content: `⚠ Error: ${errText}`, streaming: false };
        return next;
      });
    } finally {
      setStreaming(false);
      fetchSessions();
    }
  }, [input, activeId, streaming, fetchSessions]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const autoResize = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const ta = e.target;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 160) + "px";
  };

  return (
    <div className="flex h-screen bg-[#0f1117] overflow-hidden" onMouseMove={resetIdleTimer}>
      <Sidebar
        sessions={sessions}
        activeId={activeId}
        onSelect={loadSession}
        onNew={newSession}
        onDelete={deleteSession}
        onRename={renameSession}
        onUploadOpen={() => setUploadOpen(true)}
        isAdmin={isAdmin}
      />

      <div className="flex flex-col flex-1 min-w-0">
        {idleWarning && (
          <div className="flex items-center justify-between px-4 py-2 bg-amber-500/20 border-b border-amber-500/40 text-amber-300 text-xs">
            <span>You will be logged out in 1 minute due to inactivity.</span>
            <button
              onClick={resetIdleTimer}
              className="ml-4 px-3 py-0.5 rounded bg-amber-500/30 hover:bg-amber-500/50 text-amber-200 font-medium transition-colors"
            >
              Stay logged in
            </button>
          </div>
        )}
        <div className="flex items-center justify-between px-6 py-3 border-b border-slate-800/60 bg-[#0f1117]/80 backdrop-blur-sm">
          <div>
            {activeId
              ? <h1 className="text-sm font-medium text-slate-200 truncate max-w-md">
                  {sessions.find((s) => s.id === activeId)?.title ?? "Chat"}
                </h1>
              : <h1 className="text-sm font-medium text-slate-400">Select or start a chat</h1>
            }
          </div>
          {isAdmin && (
            <button
              onClick={() => setUploadOpen(true)}
              className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-white bg-slate-800/60 hover:bg-slate-700/60 border border-slate-700/40 rounded-lg px-3 py-1.5 transition-colors"
            >
              <Paperclip className="w-3.5 h-3.5" />
              Documents
            </button>
          )}
        </div>

        <div className="flex-1 overflow-y-auto px-4 md:px-12 lg:px-20 py-6 space-y-5">
          {messages.length === 0
            ? <HeroEmpty onSend={sendMessage} />
            : messages.map((msg) => <MessageBubble key={msg.id} msg={msg} />)
          }
          <div ref={bottomRef} />
        </div>

        <div className="px-4 md:px-12 lg:px-20 pb-6">
          <div className="glass rounded-2xl p-2 flex items-end gap-2 shadow-lg">
            <textarea
              ref={textareaRef}
              rows={1}
              value={input}
              onChange={autoResize}
              onKeyDown={handleKeyDown}
              placeholder="Ask anything about Indian Railways…"
              disabled={streaming}
              className="flex-1 bg-transparent resize-none text-sm text-white placeholder-slate-600 px-3 py-2.5 focus:outline-none max-h-40 leading-relaxed"
              style={{ overflowY: "auto" }}
            />
            <button
              onClick={() => sendMessage()}
              disabled={!input.trim() || streaming}
              className="shrink-0 w-9 h-9 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center transition-colors mb-0.5"
            >
              {streaming
                ? <svg className="animate-spin w-4 h-4 text-white" viewBox="0 0 24 24" fill="none">
                    <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" strokeDasharray="40" strokeDashoffset="10" />
                  </svg>
                : <Send className="w-4 h-4 text-white" />}
            </button>
          </div>
          <p className="text-center text-xs text-slate-700 mt-2">
            Press Enter to send · Shift+Enter for new line
          </p>
        </div>
      </div>

      {isAdmin && uploadOpen && <UploadModal onClose={() => setUploadOpen(false)} />}
    </div>
  );
}
