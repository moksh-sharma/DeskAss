import { useCallback, useRef, useState } from "react";
import { voiceStreamUrl, type VoiceLanguage } from "@/api/client";
import { float32ToInt16, resamplePcm, STT_SAMPLE_RATE } from "@/lib/audio";

interface RecorderState {
  isRecording: boolean;
  start: (onTranscript?: (text: string) => void, language?: VoiceLanguage) => Promise<string | null>;
  stop: () => Promise<void>;
  error: string | null;
}

/** Speech-optimised microphone constraints for clearer STT input. */
const SPEECH_CONSTRAINTS: MediaTrackConstraints = {
  channelCount: 1,
  echoCancellation: true,
  noiseSuppression: true,
  autoGainControl: true,
  sampleRate: 48000,
};

function waitForTranscriptionSocket(ws: WebSocket): Promise<void> {
  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = (fn: () => void) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      fn();
    };

    const timer = window.setTimeout(() => {
      finish(() =>
        reject(
          new Error(
            "Transcription service did not respond. Restart the backend with: cd backend && .\\run.ps1",
          ),
        ),
      );
    }, 15_000);

    ws.addEventListener("message", (event) => {
      try {
        const data = JSON.parse(String(event.data)) as {
          type?: string;
          message?: string;
        };
        if (data.type === "ready") {
          finish(() => resolve());
        } else if (data.type === "error" && data.message) {
          finish(() => reject(new Error(data.message)));
        }
      } catch {
        /* wait for structured handshake */
      }
    });

    ws.addEventListener("error", () => {
      finish(() =>
        reject(
          new Error(
            "Could not connect to live transcription service. Check that the backend is running.",
          ),
        ),
      );
    });

    ws.addEventListener("close", (event) => {
      if (settled) return;
      const reason = event.reason ? `: ${event.reason}` : "";
      finish(() =>
        reject(
          new Error(
            `Transcription connection closed (${event.code}${reason}). Is the backend running on port 8003?`,
          ),
        ),
      );
    });
  });
}

/**
 * Records PCM from the microphone and streams 16 kHz linear16 audio to the
 * backend ElevenLabs live transcription WebSocket.
 */
export function useRecorder(): RecorderState {
  const [isRecording, setIsRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const contextRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const sampleRateRef = useRef(48000);
  const onTranscriptRef = useRef<((text: string) => void) | undefined>(undefined);

  const cleanup = useCallback(() => {
    processorRef.current?.disconnect();
    sourceRef.current?.disconnect();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    processorRef.current = null;
    sourceRef.current = null;
    streamRef.current = null;
    if (contextRef.current?.state !== "closed") {
      void contextRef.current?.close();
    }
    contextRef.current = null;
  }, []);

  const finalizeSocket = useCallback((): Promise<void> => {
    return new Promise((resolve) => {
      const ws = wsRef.current;
      wsRef.current = null;
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        resolve();
        return;
      }

      ws.send("stop");

      const finish = () => {
        window.clearTimeout(timer);
        ws.removeEventListener("message", onMessage);
        if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CLOSING) {
          ws.close();
        }
        resolve();
      };

      const timer = window.setTimeout(finish, 1500);

      const onMessage = (event: MessageEvent) => {
        try {
          const data = JSON.parse(String(event.data)) as {
            type?: string;
            is_final?: boolean;
          };
          if (data.type === "transcript" && data.is_final) {
            finish();
          }
        } catch {
          /* ignore malformed frames */
        }
      };

      ws.addEventListener("message", onMessage);
    });
  }, []);

  const closeSocket = useCallback(() => {
    void finalizeSocket();
  }, [finalizeSocket]);

  const start = useCallback(
    async (
      onTranscript?: (text: string) => void,
      language: VoiceLanguage = "multi",
    ): Promise<string | null> => {
      setError(null);
      onTranscriptRef.current = onTranscript;
      cleanup();
      closeSocket();

      try {
        if (!navigator.mediaDevices?.getUserMedia) {
          const msg = "Microphone access is not available in this environment.";
          setError(msg);
          return msg;
        }

        const ws = new WebSocket(voiceStreamUrl(language));
        ws.binaryType = "arraybuffer";
        wsRef.current = ws;

        ws.addEventListener("message", (event) => {
          try {
            const data = JSON.parse(String(event.data)) as {
              type?: string;
              text?: string;
              message?: string;
            };
            if (data.type === "transcript" && typeof data.text === "string") {
              onTranscriptRef.current?.(data.text);
            } else if (data.type === "error" && data.message) {
              setError(data.message);
            }
          } catch {
            /* ignore malformed frames */
          }
        });

        await waitForTranscriptionSocket(ws);

        const stream = await navigator.mediaDevices.getUserMedia({ audio: SPEECH_CONSTRAINTS });
        streamRef.current = stream;

        const context = new AudioContext({ sampleRate: 48000 });
        contextRef.current = context;
        sampleRateRef.current = context.sampleRate;

        const source = context.createMediaStreamSource(stream);
        const processor = context.createScriptProcessor(4096, 1, 1);
        const mute = context.createGain();
        mute.gain.value = 0;

        processor.onaudioprocess = (event) => {
          const socket = wsRef.current;
          if (!socket || socket.readyState !== WebSocket.OPEN) return;
          const input = event.inputBuffer.getChannelData(0);
          const resampled = resamplePcm(new Float32Array(input), sampleRateRef.current, STT_SAMPLE_RATE);
          socket.send(float32ToInt16(resampled));
        };

        source.connect(processor);
        processor.connect(mute);
        mute.connect(context.destination);

        sourceRef.current = source;
        processorRef.current = processor;
        setIsRecording(true);
        return null;
      } catch (e) {
        cleanup();
        closeSocket();
        const msg = (e as Error).message || "Microphone permission denied.";
        setError(msg);
        return msg;
      }
    },
    [cleanup, closeSocket],
  );

  const stop = useCallback(async (): Promise<void> => {
    if (processorRef.current) {
      processorRef.current.onaudioprocess = null;
    }
    await finalizeSocket();
    cleanup();
    onTranscriptRef.current = undefined;
    setIsRecording(false);
  }, [cleanup, finalizeSocket]);

  return { isRecording, start, stop, error };
}
