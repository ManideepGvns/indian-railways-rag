import { Train, FileText, MessageSquare, Zap } from "lucide-react";

const TIPS = [
  { icon: FileText, text: "Upload circulars, manuals, timetables, or policy documents" },
  { icon: MessageSquare, text: "Ask questions in natural language — get cited, precise answers" },
  { icon: Zap, text: "Each chat remembers context so you can ask follow-up questions" },
];

const STARTERS = [
  "What are the rules for train delay compensation?",
  "Summarise the latest passenger charter guidelines.",
  "What is the procedure for refund on cancellation?",
  "Explain the freight classification system.",
];

interface Props { onSend: (text: string) => void }

export default function HeroEmpty({ onSend }: Props) {
  return (
    <div className="flex flex-col items-center justify-center h-full px-6 py-12 animate-fadeInUp">
      {/* Icon + Headline */}
      <div className="relative mb-6">
        <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-blue-600 to-blue-900 flex items-center justify-center shadow-2xl shadow-blue-900/50">
          <Train className="w-10 h-10 text-white" />
        </div>
        <div className="absolute -bottom-1 -right-1 w-6 h-6 rounded-full bg-orange-500 flex items-center justify-center">
          <Zap className="w-3.5 h-3.5 text-white" />
        </div>
      </div>

      <h2 className="text-2xl font-bold text-white text-center mb-2">
        Indian Railways Knowledge Assistant
      </h2>
      <p className="text-slate-400 text-center text-sm max-w-md mb-8">
        Upload your railway documents and ask anything. Powered by local AI — your data never leaves your infrastructure.
      </p>

      {/* Feature chips */}
      <div className="flex flex-wrap gap-2 justify-center mb-10">
        {TIPS.map(({ icon: Icon, text }) => (
          <div key={text} className="flex items-center gap-2 bg-slate-800/60 border border-slate-700/40 rounded-full px-3 py-1.5">
            <Icon className="w-3.5 h-3.5 text-blue-400 shrink-0" />
            <span className="text-xs text-slate-300">{text}</span>
          </div>
        ))}
      </div>

      {/* Starter questions */}
      <div className="w-full max-w-xl">
        <p className="text-xs text-slate-500 uppercase tracking-wide font-medium mb-3 text-center">Try asking…</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {STARTERS.map((q) => (
            <button
              key={q}
              onClick={() => onSend(q)}
              className="text-left text-xs text-slate-300 bg-slate-800/50 hover:bg-slate-700/60 border border-slate-700/40 hover:border-slate-600/60 rounded-xl px-4 py-3 transition-all leading-relaxed"
            >
              {q}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
