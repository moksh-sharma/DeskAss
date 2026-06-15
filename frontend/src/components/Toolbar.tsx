import { useRef, useState } from "react";
import { useStore } from "@/store/useStore";
import { useRecorder } from "@/hooks/useRecorder";
import { api, type VoiceLanguage } from "@/api/client";

function MicIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 2a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z" />
      <path d="M19 10v1a7 7 0 0 1-14 0v-1" />
      <line x1="12" y1="18" x2="12" y2="22" />
      <line x1="8" y1="22" x2="16" y2="22" />
    </svg>
  );
}

function MicOffIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <line x1="2" y1="2" x2="22" y2="22" />
      <path d="M9 9v3a3 3 0 0 0 5.12 2.12" />
      <path d="M15 9.34V5a3 3 0 0 0-5.94-.6" />
      <path d="M17 16.95A7 7 0 0 1 5 12v-2m14 0v2a7 7 0 0 1-.11 1.23" />
      <line x1="12" y1="19" x2="12" y2="22" />
      <line x1="8" y1="22" x2="16" y2="22" />
    </svg>
  );
}

function CameraIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
      <circle cx="12" cy="13" r="4" />
    </svg>
  );
}

function SendIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  );
}

function SparklesIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364-6.364l-.707.707M6.343 17.657l-.707.707m0-12.728l.707.707m11.314 11.314l.707-.707M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10z" />
    </svg>
  );
}

export function Toolbar() {
  const [text, setText] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const sendMessage = useStore((s) => s.sendMessage);
  const runMachineScan = useStore((s) => s.runMachineScan);
  const isMachineScanning = useStore((s) => s.isMachineScanning);
  const notify = useStore((s) => s.notify);
  const setPendingOcrText = useStore((s) => s.setPendingOcrText);
  const pendingOcrText = useStore((s) => s.pendingOcrText);
  const recorder = useRecorder();
  const prefixRef = useRef("");
  const [voiceLanguage, setVoiceLanguage] = useState<VoiceLanguage>("multi");

  const handleSend = async () => {
    if (!text.trim()) return;
    const value = text;
    setText("");
    await sendMessage(value);
  };

  const handleMic = async () => {
    if (recorder.isRecording) {
      await recorder.stop();
      return;
    }

    prefixRef.current = text.trim();
    const err = await recorder.start((streamText) => {
      const prefix = prefixRef.current;
      const spoken = streamText.trim();
      if (!spoken) {
        setText(prefix);
        return;
      }
      setText(prefix ? `${prefix} ${spoken}` : spoken);
    }, voiceLanguage);
    if (err) notify("error", err);
  };

  const handleScreenshot = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    try {
      const result = await api.ocr(file);
      if (!result.text) {
        notify("info", "No text detected in the screenshot.");
        return;
      }
      setPendingOcrText(result.text);
      const codes = result.detected_error_codes.length
        ? ` (codes: ${result.detected_error_codes.join(", ")})`
        : "";
      notify("success", `Screenshot text extracted${codes}. It will be included with your next message.`);
    } catch (err) {
      notify("error", `OCR failed: ${(err as Error).message}`);
    }
  };

  const iconBtn =
    "flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-white/70 bg-white/50 text-content-muted backdrop-blur-md transition-all duration-200 hover:bg-white/80 hover:text-accent hover:shadow-glass-sm";

  return (
    <div className="glass border-t border-white/50 px-6 py-4">
      {pendingOcrText && (
        <div className="mx-auto mb-3 flex max-w-4xl items-start gap-2.5 rounded-xl border border-sky-200/60 bg-sky-50/60 px-4 py-2.5 text-xs text-sky-800 backdrop-blur-md">
          <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-sky-200/60">
            <CameraIcon className="h-3 w-3 text-sky-700" />
          </div>
          <span className="flex-1 line-clamp-2 leading-relaxed">
            <strong className="font-bold">Screenshot attached:</strong> {pendingOcrText.slice(0, 180)}
            {pendingOcrText.length > 180 ? "…" : ""}
          </span>
          <button
            onClick={() => setPendingOcrText(null)}
            className="shrink-0 rounded-lg bg-white/60 px-2 py-0.5 text-[10px] font-bold uppercase transition-colors hover:bg-white/90"
          >
            Remove
          </button>
        </div>
      )}

      <div className="mx-auto flex max-w-4xl items-end gap-3">
        <input ref={fileRef} type="file" accept="image/*" hidden onChange={handleScreenshot} />

        <div
          className="flex shrink-0 items-center gap-0.5 rounded-xl border border-white/70 bg-white/40 p-0.5 backdrop-blur-md"
          title="Voice language - Auto detects Hindi and English (Hinglish)"
        >
          {(["multi", "en", "hi"] as const).map((lang) => (
            <button
              key={lang}
              type="button"
              disabled={recorder.isRecording}
              onClick={() => setVoiceLanguage(lang)}
              className={`rounded-lg px-2 py-1.5 text-[9px] font-bold uppercase tracking-wider transition-all duration-200 ${
                voiceLanguage === lang
                  ? "bg-white/80 text-accent shadow-glass-sm"
                  : "text-content-muted hover:text-content-secondary"
              } disabled:opacity-40`}
            >
              {lang === "multi" ? "Auto" : lang === "en" ? "EN" : "हि"}
            </button>
          ))}
        </div>

        <button
          onClick={handleMic}
          title={
            recorder.isRecording
              ? "Stop recording"
              : voiceLanguage === "multi"
                ? "Voice input - Hindi & English (auto)"
                : voiceLanguage === "hi"
                  ? "Voice input - Hindi"
                  : "Voice input - English"
          }
          className={`relative shrink-0 rounded-xl transition-all duration-200 ${
            recorder.isRecording
              ? "flex h-11 w-11 items-center justify-center bg-gradient-to-br from-red-500 to-rose-600 text-white shadow-lg shadow-red-300/40 animate-pulse scale-105"
              : iconBtn
          }`}
        >
          {recorder.isRecording ? <MicOffIcon className="h-5 w-5" /> : <MicIcon className="h-5 w-5" />}
          {recorder.isRecording && (
            <span className="absolute -top-1 -right-1 h-3 w-3 rounded-full bg-red-400 animate-ping" />
          )}
        </button>

        <button
          onClick={() => fileRef.current?.click()}
          title="Upload screenshot for OCR analysis"
          className={iconBtn}
        >
          <CameraIcon className="h-5 w-5" />
        </button>

        <div className="relative flex flex-1 items-center">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            rows={1}
            placeholder="Describe your issue in English or Hindi…"
            className="glass-input max-h-32 min-h-[44px] w-full resize-none rounded-2xl px-4 py-3 pr-12 text-sm text-content-primary placeholder:text-content-faint leading-relaxed"
          />
          {text.trim() && (
            <button
              onClick={handleSend}
              className="absolute right-3 bottom-2.5 flex h-7 w-7 items-center justify-center rounded-xl bg-accent-shine text-white shadow-glow-sm transition-all hover:scale-105 active:scale-95"
              title="Send message"
            >
              <SendIcon className="h-3.5 w-3.5" />
            </button>
          )}
        </div>

        {!text.trim() && (
          <button
            onClick={runMachineScan}
            disabled={isMachineScanning}
            title="Run full system scan with troubleshooter"
            className="flex h-11 shrink-0 items-center justify-center gap-1.5 rounded-xl border border-accent/25 bg-accent/10 px-4 text-xs font-bold uppercase tracking-wider text-accent backdrop-blur-md transition-all hover:bg-accent/18 hover:shadow-glow-sm disabled:opacity-50"
          >
            <SparklesIcon className={`h-4 w-4 ${isMachineScanning ? "animate-spin" : ""}`} />
            {isMachineScanning ? "Scanning…" : "Full Scan"}
          </button>
        )}
      </div>
    </div>
  );
}
