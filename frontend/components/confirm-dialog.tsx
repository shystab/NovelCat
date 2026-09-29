"use client";

import { AlertTriangle, X } from "lucide-react";
import type { Theme } from "@/hooks/use-theme";
import ModalSurface from "@/components/modal-surface";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: "danger" | "default";
  theme: Theme;
  busy?: boolean;
  onConfirm: () => void | Promise<void>;
  onCancel: () => void;
}

export default function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "确认",
  cancelLabel = "取消",
  tone = "default",
  theme,
  busy = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  if (!open) return null;

  const isDark = theme === "dark";
  const isSepia = theme === "sepia";
  const panelBg = isDark ? "bg-slate-900 border-slate-700" : isSepia ? "bg-[#fbf7ed] border-amber-200" : "bg-white border-slate-200";
  const headingTxt = isDark ? "text-slate-100" : isSepia ? "text-amber-950" : "text-slate-900";
  const bodyTxt = isDark ? "text-slate-400" : isSepia ? "text-amber-700" : "text-slate-500";
  const cancelBtn = isDark ? "bg-slate-800 text-slate-300 hover:bg-slate-700 border-slate-700" : isSepia ? "bg-amber-50 text-amber-800 hover:bg-amber-100 border-amber-200" : "bg-white text-slate-700 hover:bg-slate-50 border-slate-200";
  const confirmBtn = tone === "danger"
    ? "bg-red-600 hover:bg-red-700 text-white"
    : isDark
      ? "bg-slate-200 hover:bg-white text-slate-950"
      : isSepia
        ? "bg-amber-900 hover:bg-amber-800 text-white"
        : "bg-slate-900 hover:bg-slate-800 text-white";
  const iconTone = tone === "danger"
    ? "bg-red-50 text-red-600 border-red-100"
    : isDark
      ? "bg-slate-800 text-slate-300 border-slate-700"
      : isSepia
        ? "bg-amber-100 text-amber-800 border-amber-200"
        : "bg-slate-100 text-slate-700 border-slate-200";

  return (
    <ModalSurface open={open} onClose={onCancel} label={title} busy={busy}>
      <div className={`w-full rounded-lg border ${panelBg} overflow-hidden`}>
        <div className="p-5">
          <div className="flex items-start gap-3">
            <div className={`shrink-0 p-2 rounded-md border ${iconTone}`}>
              <AlertTriangle size={18} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-start justify-between gap-3">
                <h2 className={`text-sm font-semibold ${headingTxt}`}>{title}</h2>
                <button
                  type="button"
                  onClick={onCancel}
                  disabled={busy}
                  className={`p-1 rounded-md transition-colors ${bodyTxt} hover:bg-black/5 disabled:opacity-50`}
                  aria-label="关闭"
                >
                  <X size={15} />
                </button>
              </div>
              <p className={`mt-2 text-xs leading-relaxed ${bodyTxt}`}>{description}</p>
            </div>
          </div>
        </div>
        <div className={`px-5 py-3 border-t ${isDark ? "border-slate-800 bg-slate-950/40" : isSepia ? "border-amber-200 bg-amber-50/50" : "border-slate-100 bg-slate-50/80"} flex justify-end gap-2`}>
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className={`px-3 py-2 rounded-md border text-xs font-semibold transition-colors disabled:opacity-50 ${cancelBtn}`}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className={`px-3 py-2 rounded-md text-xs font-semibold transition-colors disabled:opacity-50 ${confirmBtn}`}
          >
            {busy ? "处理中..." : confirmLabel}
          </button>
        </div>
      </div>
    </ModalSurface>
  );
}
