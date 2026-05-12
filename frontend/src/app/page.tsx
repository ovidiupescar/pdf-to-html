"use client";

import { useState, useRef, useCallback, useEffect } from "react";

type Status = "idle" | "uploading" | "processing" | "done" | "error";

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [progress, setProgress] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const reset = useCallback(() => {
    setFile(null);
    setStatus("idle");
    setProgress("");
    setJobId(null);
    setDownloadUrl(null);
    if (pollRef.current) clearInterval(pollRef.current);
  }, []);

  const handleFile = (f: File) => {
    if (f.type === "application/pdf") {
      setFile(f);
      setStatus("idle");
    }
  };

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  }, []);

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const onDragLeave = useCallback(() => setDragOver(false), []);

  const pollStatus = useCallback((id: string) => {
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`/api/status/${id}`);
        const data = await res.json();
        if (data.status === "completed") {
          setStatus("done");
          setDownloadUrl(data.download_url || `/api/download/${id}`);
          if (pollRef.current) clearInterval(pollRef.current);
        } else if (data.status === "failed") {
          setStatus("error");
          setProgress(data.error || "Conversion failed");
          if (pollRef.current) clearInterval(pollRef.current);
        } else {
          setProgress(data.progress || "Processing...");
        }
      } catch {
        setStatus("error");
        setProgress("Lost connection to server");
        if (pollRef.current) clearInterval(pollRef.current);
      }
    }, 2000);
  }, []);

  const upload = useCallback(async () => {
    if (!file) return;
    setStatus("uploading");
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await fetch("/api/upload", { method: "POST", body: form });
      if (!res.ok) throw new Error("Upload failed");
      const data = await res.json();
      setJobId(data.job_id);
      setStatus("processing");
      setProgress("Queued...");
      pollStatus(data.job_id);
    } catch {
      setStatus("error");
      setProgress("Upload failed");
    }
  }, [file, pollStatus]);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  return (
    <div className="flex flex-col items-center justify-center min-h-screen px-4">
      <div className="w-full max-w-xl">
        <h1 className="text-3xl font-bold text-center mb-2 text-white">
          PDF Tech &rarr; HTML
        </h1>
        <p className="text-center text-zinc-400 mb-10">
          Upload a PDF, get clean HTML back.
        </p>

        {status === "done" && downloadUrl ? (
          <div className="card flex flex-col items-center gap-4 py-10">
            <div className="text-4xl">&#10003;</div>
            <p className="text-green-400 font-semibold text-lg">Conversion complete</p>
            <a
              href={downloadUrl}
              className="mt-2 px-6 py-3 bg-green-500 text-black font-semibold rounded-lg hover:bg-green-400 transition"
            >
              Download HTML
            </a>
            <button onClick={reset} className="text-zinc-400 text-sm hover:text-white mt-4">
              Convert another
            </button>
          </div>
        ) : (
          <div
            onDrop={onDrop}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onClick={() => inputRef.current?.click()}
            className={`card border-2 border-dashed cursor-pointer transition-colors ${
              dragOver ? "border-green-500 bg-green-500/5" : "border-zinc-700 hover:border-zinc-500"
            } ${file ? "!border-solid !border-green-500/40" : ""}`}
          >
            <input
              ref={inputRef}
              type="file"
              accept="application/pdf"
              className="hidden"
              onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
            />
            {file ? (
              <div className="flex flex-col items-center gap-3 py-6">
                <div className="text-3xl">📄</div>
                <p className="text-white font-medium">{file.name}</p>
                <p className="text-zinc-500 text-sm">
                  {(file.size / 1024 / 1024).toFixed(2)} MB
                </p>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-3 py-10">
                <div className="text-3xl">⬆</div>
                <p className="text-zinc-300">Drop a PDF here or click to browse</p>
                <p className="text-zinc-600 text-sm">PDF files only</p>
              </div>
            )}
          </div>
        )}

        {status !== "done" && file && (
          <button
            onClick={upload}
            disabled={status === "uploading" || status === "processing"}
            className="w-full mt-4 py-3 bg-green-500 text-black font-semibold rounded-lg hover:bg-green-400 transition disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {status === "uploading"
              ? "Uploading..."
              : status === "processing"
              ? "Processing..."
              : "Convert to HTML"}
          </button>
        )}

        {(status === "processing" || status === "uploading") && (
          <div className="mt-6 card">
            <div className="flex items-center gap-3">
              <div className="h-4 w-4 border-2 border-green-500 border-t-transparent rounded-full animate-spin" />
              <span className="text-zinc-300">{progress}</span>
            </div>
          </div>
        )}

        {status === "error" && (
          <div className="mt-6 card border border-red-500/30">
            <p className="text-red-400">{progress}</p>
            <button onClick={reset} className="text-zinc-400 text-sm hover:text-white mt-3">
              Try again
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
