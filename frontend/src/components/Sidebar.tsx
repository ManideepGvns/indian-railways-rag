import React, { useState } from "react";
import {
  MessageSquare, Plus, Trash2, Edit2, Check, X, Train, LogOut, Upload,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";

export interface Session {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
}

interface Props {
  sessions: Session[];
  activeId: number | null;
  onSelect: (id: number) => void;
  onNew: () => void;
  onDelete: (id: number) => void;
  onRename: (id: number, title: string) => void;
  onUploadOpen: () => void;
  isAdmin: boolean;
}

export default function Sidebar({ sessions, activeId, onSelect, onNew, onDelete, onRename, onUploadOpen, isAdmin }: Props) {
  const { user, logout } = useAuth();
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editTitle, setEditTitle] = useState("");

  const startEdit = (s: Session, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(s.id);
    setEditTitle(s.title);
  };

  const confirmEdit = (id: number, e: React.MouseEvent) => {
    e.stopPropagation();
    if (editTitle.trim()) onRename(id, editTitle.trim());
    setEditingId(null);
  };

  const cancelEdit = (e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(null);
  };

  return (
    <div className="flex flex-col h-full w-64 bg-[#0d1526] border-r border-slate-800/60">
      {/* Logo */}
      <div className="p-4 border-b border-slate-800/60">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-xl bg-gradient-to-br from-blue-600 to-blue-800">
            <Train className="w-5 h-5 text-white" />
          </div>
          <div>
            <div className="text-sm font-bold text-white">IR Assistant</div>
            <div className="text-xs text-orange-400">Indian Railways RAG</div>
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="p-3 space-y-2">
        <button
          onClick={onNew}
          className="w-full flex items-center gap-2 px-3 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium transition-colors"
        >
          <Plus className="w-4 h-4" />
          New Chat
        </button>
        {isAdmin && (
          <button
            onClick={onUploadOpen}
            className="w-full flex items-center gap-2 px-3 py-2.5 rounded-xl bg-slate-800/80 hover:bg-slate-700/80 text-slate-300 text-sm transition-colors border border-slate-700/40"
          >
            <Upload className="w-4 h-4 text-orange-400" />
            Upload Documents
          </button>
        )}
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto px-2 pb-2">
        {sessions.length === 0 && (
          <div className="text-center text-slate-600 text-xs mt-8 px-4">
            No chats yet. Start a new conversation!
          </div>
        )}
        <div className="space-y-0.5">
          {sessions.map((s) => (
            <div
              key={s.id}
              onClick={() => onSelect(s.id)}
              className={`group relative flex items-center gap-2 px-3 py-2.5 rounded-lg cursor-pointer transition-all ${
                activeId === s.id
                  ? "bg-blue-950/70 border border-blue-800/50"
                  : "hover:bg-slate-800/50 border border-transparent"
              }`}
            >
              <MessageSquare className={`w-3.5 h-3.5 shrink-0 ${activeId === s.id ? "text-blue-400" : "text-slate-600"}`} />

              {editingId === s.id ? (
                <div className="flex items-center gap-1 flex-1 min-w-0" onClick={(e) => e.stopPropagation()}>
                  <input
                    autoFocus
                    className="flex-1 min-w-0 bg-slate-900 border border-blue-600 rounded px-2 py-0.5 text-xs text-white focus:outline-none"
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") confirmEdit(s.id, e as any);
                      if (e.key === "Escape") cancelEdit(e as any);
                    }}
                  />
                  <button onClick={(e) => confirmEdit(s.id, e)} className="p-0.5 text-green-400 hover:text-green-300">
                    <Check className="w-3 h-3" />
                  </button>
                  <button onClick={cancelEdit} className="p-0.5 text-red-400 hover:text-red-300">
                    <X className="w-3 h-3" />
                  </button>
                </div>
              ) : (
                <>
                  <span className="flex-1 min-w-0 text-xs text-slate-300 truncate">{s.title}</span>
                  <div className="hidden group-hover:flex items-center gap-1 shrink-0">
                    <button
                      onClick={(e) => startEdit(s, e)}
                      className="p-1 rounded text-slate-500 hover:text-slate-300 hover:bg-slate-700"
                    >
                      <Edit2 className="w-3 h-3" />
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); onDelete(s.id); }}
                      className="p-1 rounded text-slate-500 hover:text-red-400 hover:bg-red-950/40"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Footer: user + logout */}
      <div className="p-3 border-t border-slate-800/60">
        <div className="flex items-center gap-2 px-2">
          <div className="w-7 h-7 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-white text-xs font-bold shrink-0">
            {user?.username?.[0]?.toUpperCase()}
          </div>
          <span className="flex-1 text-sm text-slate-300 truncate">{user?.username}</span>
          <button onClick={logout} className="p-1.5 text-slate-500 hover:text-red-400 hover:bg-red-950/30 rounded-lg transition-colors" title="Sign out">
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
