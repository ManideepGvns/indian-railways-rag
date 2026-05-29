import React, { useCallback, useRef, useState, useEffect } from "react";
import { Upload, X, FileText, CheckCircle, AlertCircle, Trash2, Loader2 } from "lucide-react";
import api from "../api/client";

interface FileRecord {
  id: number;
  file_id: string;
  filename: string;
  chunk_count: number;
  status: string;
}

interface UploadResult {
  filename: string;
  status: "uploading" | "done" | "duplicate" | "error";
  message?: string;
  file?: File;   // kept for "replace" action
}

interface Props {
  onClose: () => void;
}

export default function UploadModal({ onClose }: Props) {
  const [files, setFiles] = useState<FileRecord[]>([]);
  const [uploadResults, setUploadResults] = useState<UploadResult[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<FileRecord | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const fetchFiles = useCallback(async () => {
    try {
      const { data } = await api.get<{ files: FileRecord[] }>("/upload");
      setFiles(data.files);
    } catch { /* keep stale list */ }
  }, []);

  useEffect(() => { fetchFiles(); }, [fetchFiles]);

  // Upload a single File object; returns the result
  const uploadOne = async (file: File): Promise<UploadResult> => {
    const form = new FormData();
    form.append("file", file);
    try {
      await api.post("/upload", form, { headers: { "Content-Type": "multipart/form-data" } });
      return { filename: file.name, status: "done" };
    } catch (e: any) {
      const status = e?.response?.status;
      const detail: string = e?.response?.data?.detail ?? "Upload failed";
      if (status === 409) {
        return { filename: file.name, status: "duplicate", message: detail, file };
      }
      return { filename: file.name, status: "error", message: detail };
    }
  };

  const handleFiles = async (fileList: FileList | null) => {
    if (!fileList || fileList.length === 0) return;

    // Snapshot File objects BEFORE resetting the input — clearing input.value
    // invalidates the live FileList reference in some browsers.
    const incoming = Array.from(fileList);

    // Reset input AFTER snapshotting so re-selecting the same file works
    if (inputRef.current) inputRef.current.value = "";

    // Initialise all as "uploading"
    setUploadResults(incoming.map((f) => ({ filename: f.name, status: "uploading" })));

    const results: UploadResult[] = [];
    for (const file of incoming) {
      const result = await uploadOne(file);
      results.push(result);
      setUploadResults([...results, ...incoming.slice(results.length).map((f) => ({ filename: f.name, status: "uploading" as const }))]);
    }

    setUploadResults(results);
    fetchFiles();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    handleFiles(e.dataTransfer.files);
  };

  // Delete file from both SQLite and Qdrant vector store
  const doDelete = async (file_id: string) => {
    setDeletingId(file_id);
    try {
      await api.delete(`/upload/${file_id}`);
      setFiles((prev) => prev.filter((f) => f.file_id !== file_id));
    } catch { /* surface via re-fetch */ }
    setDeletingId(null);
    setConfirmDelete(null);
    fetchFiles();
  };

  // "Replace": delete old chunks then re-upload the new file
  const replaceFile = async (result: UploadResult) => {
    if (!result.file) return;
    // Find any existing file with the same name to delete first
    const existing = files.find((f) => f.filename === result.filename);
    if (existing) {
      await api.delete(`/upload/${existing.file_id}`);
      setFiles((prev) => prev.filter((f) => f.file_id !== existing.file_id));
    }
    // Clear the duplicate banner for this file and re-upload
    setUploadResults((prev) => prev.map((r) => r.filename === result.filename ? { ...r, status: "uploading" } : r));
    const fresh = await uploadOne(result.file);
    setUploadResults((prev) => prev.map((r) => r.filename === result.filename ? fresh : r));
    fetchFiles();
  };

  const statusIcon = (status: string) => {
    if (status === "ready") return <CheckCircle className="w-4 h-4 text-green-400 shrink-0" />;
    if (status === "error") return <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />;
    return <Loader2 className="w-4 h-4 text-blue-400 shrink-0 animate-spin" />;
  };

  const anyUploading = uploadResults.some((r) => r.status === "uploading");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="glass rounded-2xl w-full max-w-lg mx-4 p-6 shadow-2xl animate-fadeInUp">

        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <div>
            <h2 className="text-lg font-semibold text-white">Manage Documents</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Upload PDFs, DOCX, TXT, or Markdown · max 50 MB · duplicates auto-detected
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-slate-500 hover:text-white hover:bg-slate-700 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Drop zone */}
        <div
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={() => !anyUploading && inputRef.current?.click()}
          className={`border-2 border-dashed rounded-xl p-8 text-center transition-all mb-4 ${
            anyUploading
              ? "border-blue-800/50 bg-blue-950/10 cursor-wait"
              : dragOver
              ? "border-blue-400 bg-blue-950/30 cursor-copy"
              : "border-slate-700 hover:border-slate-500 bg-slate-900/30 hover:bg-slate-800/30 cursor-pointer"
          }`}
        >
          {anyUploading
            ? <Loader2 className="w-8 h-8 mx-auto mb-3 text-blue-400 animate-spin" />
            : <Upload className={`w-8 h-8 mx-auto mb-3 ${dragOver ? "text-blue-400" : "text-slate-600"}`} />
          }
          <p className="text-sm text-slate-400">
            {anyUploading ? "Embedding chunks…" : "Drop files here or click to browse"}
          </p>
          <p className="text-xs text-slate-600 mt-1">.pdf  .docx  .txt  .md</p>
          <input
            ref={inputRef}
            type="file"
            className="hidden"
            multiple
            accept=".pdf,.docx,.txt,.md"
            onChange={(e) => handleFiles(e.target.files)}
          />
        </div>

        {/* Per-file upload result banners */}
        {uploadResults.length > 0 && (
          <div className="space-y-2 mb-4">
            {uploadResults.map((r) => (
              <div
                key={r.filename}
                className={`flex items-start gap-2 rounded-lg px-3 py-2 border text-xs ${
                  r.status === "done"
                    ? "bg-green-950/40 border-green-800/40"
                    : r.status === "duplicate"
                    ? "bg-amber-950/40 border-amber-800/40"
                    : r.status === "error"
                    ? "bg-red-950/40 border-red-800/40"
                    : "bg-slate-900/40 border-slate-700/40"
                }`}
              >
                <span className="mt-0.5 shrink-0">
                  {r.status === "done" && <CheckCircle className="w-3.5 h-3.5 text-green-400" />}
                  {r.status === "duplicate" && <AlertCircle className="w-3.5 h-3.5 text-amber-400" />}
                  {r.status === "error" && <AlertCircle className="w-3.5 h-3.5 text-red-400" />}
                  {r.status === "uploading" && <Loader2 className="w-3.5 h-3.5 text-blue-400 animate-spin" />}
                </span>
                <div className="flex-1 min-w-0">
                  <span className="font-medium text-slate-200 truncate block">{r.filename}</span>
                  {r.status === "done" && <span className="text-green-400">Indexed successfully</span>}
                  {r.status === "uploading" && <span className="text-slate-400">Embedding…</span>}
                  {r.status === "error" && <span className="text-red-300">{r.message}</span>}
                  {r.status === "duplicate" && (
                    <span className="text-amber-300">
                      Already in knowledge base.{" "}
                      <button
                        onClick={() => replaceFile(r)}
                        className="underline text-amber-200 hover:text-white font-medium"
                      >
                        Delete existing & re-upload
                      </button>
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Indexed files list */}
        <div className="flex items-center justify-between mb-2">
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wide">
            Knowledge Base ({files.length} {files.length === 1 ? "file" : "files"})
          </p>
          {files.length > 0 && (
            <p className="text-xs text-slate-600">
              {files.reduce((s, f) => s + f.chunk_count, 0)} total chunks
            </p>
          )}
        </div>

        <div className="space-y-1.5 max-h-52 overflow-y-auto">
          {files.length === 0 && (
            <p className="text-center text-xs text-slate-600 py-4">No documents in knowledge base yet</p>
          )}
          {files.map((f) => (
            <div
              key={f.file_id}
              className="flex items-center gap-3 bg-slate-900/50 rounded-lg px-3 py-2.5 border border-slate-800/50 group"
            >
              <FileText className="w-4 h-4 text-slate-500 shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-xs text-slate-200 truncate font-medium">{f.filename}</p>
                <p className="text-xs text-slate-600 mt-0.5">
                  {f.chunk_count} chunks&nbsp;·&nbsp;
                  <span className={
                    f.status === "ready" ? "text-green-500"
                    : f.status === "error" ? "text-red-400"
                    : "text-blue-400"
                  }>
                    {f.status}
                  </span>
                </p>
              </div>
              {statusIcon(f.status)}
              {/* Delete button — shows on hover with confirmation */}
              <button
                disabled={deletingId === f.file_id}
                onClick={() => setConfirmDelete(f)}
                className="p-1.5 text-slate-600 hover:text-red-400 hover:bg-red-950/30 rounded-lg transition-colors disabled:opacity-40"
                title="Delete file and remove all its chunks from the knowledge base"
              >
                {deletingId === f.file_id
                  ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  : <Trash2 className="w-3.5 h-3.5" />}
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Delete confirmation dialog */}
      {confirmDelete && (
        <div className="fixed inset-0 z-60 flex items-center justify-center bg-black/70">
          <div className="glass rounded-2xl w-full max-w-sm mx-4 p-6 animate-fadeInUp shadow-2xl">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2.5 rounded-xl bg-red-950/60 border border-red-800/40">
                <Trash2 className="w-5 h-5 text-red-400" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-white">Delete document?</h3>
                <p className="text-xs text-slate-400 mt-0.5">This cannot be undone</p>
              </div>
            </div>

            <div className="bg-slate-900/60 rounded-lg px-3 py-2.5 mb-4 border border-slate-800/50">
              <p className="text-xs text-slate-300 font-medium truncate">{confirmDelete.filename}</p>
              <p className="text-xs text-slate-500 mt-0.5">
                {confirmDelete.chunk_count} chunks will be permanently removed from the knowledge base
              </p>
            </div>

            <div className="flex gap-2">
              <button
                onClick={() => setConfirmDelete(null)}
                className="flex-1 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-sm font-medium transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => doDelete(confirmDelete.file_id)}
                className="flex-1 py-2.5 rounded-xl bg-red-700 hover:bg-red-600 text-white text-sm font-medium transition-colors"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
