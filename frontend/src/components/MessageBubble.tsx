import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Train, User, BookOpen } from "lucide-react";

export interface Msg {
  id?: number;           // server id (positive) or temp client id (negative)
  role: "user" | "assistant";
  content: string;
  sources?: string[];    // source filenames from RAG retrieval
  streaming?: boolean;
}

export default function MessageBubble({ msg }: { msg: Msg }) {
  const isUser = msg.role === "user";
  const hasSources = !isUser && !msg.streaming && msg.sources && msg.sources.length > 0;

  return (
    <div className={`flex gap-3 animate-fadeInUp ${isUser ? "flex-row-reverse" : "flex-row"}`}>
      {/* Avatar */}
      <div className={`shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
        isUser
          ? "bg-gradient-to-br from-slate-600 to-slate-700"
          : "bg-gradient-to-br from-blue-600 to-blue-800"
      }`}>
        {isUser
          ? <User className="w-4 h-4 text-white" />
          : <Train className="w-4 h-4 text-white" />}
      </div>

      {/* Bubble + Sources */}
      <div className="max-w-[78%] flex flex-col gap-1.5">
        <div className={`rounded-2xl px-4 py-3 ${
          isUser
            ? "bg-blue-700/80 text-white rounded-tr-sm"
            : "bg-slate-800/80 text-slate-100 border border-slate-700/40 rounded-tl-sm"
        }`}>
          {isUser ? (
            <p className="text-sm leading-relaxed whitespace-pre-wrap">{msg.content}</p>
          ) : (
            <div className={`prose-chat text-sm ${msg.streaming ? "cursor-blink" : ""}`}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {msg.content || ""}
              </ReactMarkdown>
            </div>
          )}
        </div>

        {/* Source citations — display only, not downloadable */}
        {hasSources && (
          <div className="flex flex-wrap items-center gap-1.5 px-1">
            <BookOpen className="w-3 h-3 text-slate-500 shrink-0" />
            {msg.sources!.map((src) => (
              <span
                key={src}
                title={src}
                className="inline-flex items-center max-w-[200px] truncate rounded-md bg-slate-800/70 border border-slate-700/50 px-2 py-0.5 text-[10px] text-slate-400 select-none"
              >
                {src}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
