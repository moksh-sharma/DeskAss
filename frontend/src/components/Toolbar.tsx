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

  return (
    <div className="border-t border-base-700/60 bg-base-850 px-6 py-4 shadow-[0_-4px_12px_rgba(0,0,0,0.15)] backdrop-blur-md bg-opacity-98">
      {pendingOcrText && (
        <div className="mb-3 flex items-start gap-2.5 rounded-lg border border-severity-info/20 bg-severity-info/5 px-4 py-2.5 text-xs text-severity-info shadow-inner">
          <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-severity-info/10">
            <CameraIcon className="h-3 w-3 text-severity-info" />
          </div>
          <span className="flex-1 line-clamp-2 leading-relaxed">
            <strong className="font-bold">Screenshot attached:</strong> {pendingOcrText.slice(0, 180)}
            {pendingOcrText.length > 180 ? "…" : ""}
          </span>
          <button
            onClick={() => setPendingOcrText(null)}
            className="shrink-0 px-2 py-0.5 rounded bg-severity-info/10 text-[10px] font-bold uppercase hover:bg-severity-info/20 transition-colors"
          >
            Remove
          </button>
        </div>
      )}

      <div className="flex items-end gap-3 max-w-4xl mx-auto">
        <input ref={fileRef} type="file" accept="image/*" hidden onChange={handleScreenshot} />

        {/* Voice language: Hindi + English auto, or fixed EN / HI */}
        <div
          className="flex shrink-0 items-center gap-0.5 rounded-xl border border-base-700/50 bg-base-900/50 p-0.5"
          title="Voice language — Auto detects Hindi and English (Hinglish)"
        >
          {(["multi", "en", "hi"] as const).map((lang) => (
            <button
              key={lang}
              type="button"
              disabled={recorder.isRecording}
              onClick={() => setVoiceLanguage(lang)}
              className={`rounded-lg px-2 py-1.5 text-[9px] font-bold uppercase tracking-wider transition-colors ${voiceLanguage === lang
                  ? "bg-accent/25 text-accent shadow-sm"
                  : "text-content-muted hover:text-content-secondary"
                } disabled:opacity-40`}
            >
              {lang === "multi" ? "Auto" : lang === "en" ? "EN" : "हि"}
            </button>
          ))}
        </div>

        {/* Action Button: Voice Input */}
        <button
          onClick={handleMic}
          title={
            recorder.isRecording
              ? "Stop recording"
              : voiceLanguage === "multi"
                ? "Voice input — Hindi & English (auto)"
                : voiceLanguage === "hi"
                  ? "Voice input — Hindi"
                  : "Voice input — English"
          }
          className={`h-11 w-11 shrink-0 flex items-center justify-center rounded-xl transition-all duration-200 relative ${recorder.isRecording
              ? "bg-severity-critical text-white shadow-lg shadow-severity-critical/30 animate-pulse scale-105"
              : "bg-base-700 hover:bg-base-600 text-gray-300 hover:text-white border border-base-600/30"
            }`}
        >
          {recorder.isRecording ? (
            <MicOffIcon className="h-5 w-5" />
          ) : (
            <MicIcon className="h-5 w-5" />
          )}
          {recorder.isRecording && (
            <span className="absolute -top-1 -right-1 h-3 w-3 rounded-full bg-red-400 animate-ping" />
          )}
        </button>

        {/* Action Button: Add Screenshot */}
        <button
          onClick={() => fileRef.current?.click()}
          title="Upload screenshot for OCR analysis"
          className="h-11 w-11 shrink-0 flex items-center justify-center rounded-xl bg-base-700 hover:bg-base-600 text-gray-300 hover:text-white border border-base-600/30 transition-all duration-150"
        >
          <CameraIcon className="h-5 w-5" />
        </button>

        {/* Message Input Box */}
        <div className="flex-1 relative flex items-center">
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
            className="max-h-32 min-h-[44px] w-full resize-none rounded-xl border border-base-700 bg-base-900 px-4 py-3 pr-10 text-sm text-content-primary placeholder:text-content-muted focus:border-accent focus:ring-1 focus:ring-accent/30 focus:outline-none transition-all duration-150 leading-relaxed shadow-inner"
          />
          {text.trim() && (
            <button
              onClick={handleSend}
              className="absolute right-3 bottom-2.5 h-6 w-6 flex items-center justify-center rounded-lg bg-accent text-white hover:bg-accent-hover transition-all active:scale-95 duration-100"
              title="Send message"
            >
              <SendIcon className="h-3.5 w-3.5" />
            </button>
          )}
        </div>

        {/* Quick Send/Diagnostic Actions */}
        {!text.trim() && (
          <button
            onClick={runMachineScan}
            disabled={isMachineScanning}
            title="Run full system scan with troubleshooter"
            className="h-11 px-4 rounded-xl font-semibold text-xs tracking-wider uppercase flex items-center justify-center gap-1.5 transition-all duration-150 border border-accent/20 bg-accent/10 hover:bg-accent/20 text-accent disabled:opacity-50"
          >
            <SparklesIcon className={`h-4 w-4 ${isMachineScanning ? "animate-spin text-accent" : ""}`} />
            {isMachineScanning ? "Scanning…" : "Full Scan"}
          </button>
        )}
      </div>
    </div>
  );
}
