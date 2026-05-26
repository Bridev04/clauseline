"use client";

import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { uploadContract } from "@/lib/api";

export function UploadContract({ onUploaded }: { onUploaded?: (contractId: string) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastFilename, setLastFilename] = useState<string | null>(null);
  const queryClient = useQueryClient();

  async function handleFile(file: File) {
    setUploading(true);
    setError(null);
    try {
      const contract = await uploadContract(file);
      setLastFilename(contract.filename);
      await queryClient.invalidateQueries({ queryKey: ["contracts"] });
      onUploaded?.(contract.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <div className="space-y-2">
      <label className="block text-xs font-medium text-zinc-500 mb-1">Upload a PDF</label>
      <div className="flex items-center gap-2">
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,application/pdf"
          disabled={uploading}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFile(file);
          }}
          className="block w-full text-sm text-zinc-500 file:mr-3 file:py-1.5 file:px-3 file:rounded file:border-0 file:text-xs file:font-medium file:bg-zinc-100 file:text-zinc-700 hover:file:bg-zinc-200 disabled:opacity-50"
        />
        {uploading && <span className="text-xs text-zinc-400 whitespace-nowrap">Indexing…</span>}
      </div>
      {lastFilename && !uploading && (
        <p className="text-xs text-emerald-600">Indexed: {lastFilename}</p>
      )}
      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  );
}
