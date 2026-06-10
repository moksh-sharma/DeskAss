import { useCallback, useRef, useState } from "react";
import { mergeFloat32, pcmToWavBlob, resamplePcm, VOSK_SAMPLE_RATE } from "@/lib/audio";

interface RecorderState {
  isRecording: boolean;
  start: () => Promise<string | null>;
  stop: () => Promise<Blob | null>;
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

/**
 * Records lossless PCM directly from the microphone (no WebM/Opus compression),
 * then encodes 16 kHz mono WAV - the format Vosk expects for best accuracy.
 */
export function useRecorder(): RecorderState {
  const [isRecording, setIsRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const contextRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const chunksRef = useRef<Float32Array[]>([]);
  const sampleRateRef = useRef(48000);

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
    chunksRef.current = [];
  }, []);

  const start = useCallback(async (): Promise<string | null> => {
    setError(null);
    cleanup();
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        const msg = "Microphone access is not available in this environment.";
        setError(msg);
        return msg;
      }

      const stream = await navigator.mediaDevices.getUserMedia({ audio: SPEECH_CONSTRAINTS });
      streamRef.current = stream;

      const context = new AudioContext({ sampleRate: 48000 });
      contextRef.current = context;
      sampleRateRef.current = context.sampleRate;

      const source = context.createMediaStreamSource(stream);
      // ScriptProcessor gives raw PCM without lossy codec compression.
      const processor = context.createScriptProcessor(4096, 1, 1);
      const mute = context.createGain();
      mute.gain.value = 0;

      chunksRef.current = [];
      processor.onaudioprocess = (event) => {
        const input = event.inputBuffer.getChannelData(0);
        chunksRef.current.push(new Float32Array(input));
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
      const msg = (e as Error).message || "Microphone permission denied.";
      setError(msg);
      return msg;
    }
  }, [cleanup]);

  const stop = useCallback((): Promise<Blob | null> => {
    return new Promise((resolve) => {
      const processor = processorRef.current;
      const captureRate = sampleRateRef.current;

      if (!processor || chunksRef.current.length === 0) {
        cleanup();
        setIsRecording(false);
        resolve(null);
        return;
      }

      processor.onaudioprocess = null;
      const pcm = mergeFloat32(chunksRef.current);
      cleanup();
      setIsRecording(false);

      if (pcm.length < captureRate * 0.4) {
        // Less than ~400 ms of audio - too short for reliable STT.
        resolve(null);
        return;
      }

      const resampled = resamplePcm(pcm, captureRate, VOSK_SAMPLE_RATE);
      resolve(pcmToWavBlob(resampled, VOSK_SAMPLE_RATE));
    });
  }, [cleanup]);

  return { isRecording, start, stop, error };
}
