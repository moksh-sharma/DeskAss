/** 16 kHz mono 16-bit PCM WAV works well for speech capture. */
export const STT_SAMPLE_RATE = 16000;

/** Convert float PCM samples to little-endian int16 bytes for Deepgram live STT. */
export function float32ToInt16(samples: Float32Array): ArrayBuffer {
  const buffer = new ArrayBuffer(samples.length * 2);
  const view = new DataView(buffer);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return buffer;
}

/** Merge captured PCM chunks into one buffer. */
export function mergeFloat32(chunks: Float32Array[]): Float32Array {
  const total = chunks.reduce((n, c) => n + c.length, 0);
  const merged = new Float32Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.length;
  }
  return merged;
}

/** Linear-interpolation resampler (better than browser decode→re-encode round-trip). */
export function resamplePcm(
  input: Float32Array,
  inputRate: number,
  outputRate: number,
): Float32Array {
  if (inputRate === outputRate) return input;
  const ratio = inputRate / outputRate;
  const outputLength = Math.max(1, Math.round(input.length / ratio));
  const output = new Float32Array(outputLength);
  for (let i = 0; i < outputLength; i++) {
    const src = i * ratio;
    const idx = Math.floor(src);
    const frac = src - idx;
    const s0 = input[idx] ?? 0;
    const s1 = input[Math.min(idx + 1, input.length - 1)] ?? s0;
    output[i] = s0 + frac * (s1 - s0);
  }
  return output;
}

/** Peak-normalise quiet speech for a stronger signal (target ~ -3 dBFS). */
export function normalizeGain(samples: Float32Array, targetPeak = 0.85): Float32Array {
  let peak = 0;
  for (let i = 0; i < samples.length; i++) {
    peak = Math.max(peak, Math.abs(samples[i]));
  }
  if (peak < 0.01) return samples; // silence / noise floor
  const gain = Math.min(targetPeak / peak, 4); // cap boost at +12 dB
  if (gain <= 1.05) return samples;
  const out = new Float32Array(samples.length);
  for (let i = 0; i < samples.length; i++) {
    out[i] = Math.max(-1, Math.min(1, samples[i] * gain));
  }
  return out;
}

/** Trim leading/trailing silence so transcription focuses on speech. */
export function trimSilence(
  samples: Float32Array,
  sampleRate: number,
  threshold = 0.012,
  padMs = 120,
): Float32Array {
  let start = 0;
  let end = samples.length - 1;
  for (let i = 0; i < samples.length; i++) {
    if (Math.abs(samples[i]) > threshold) {
      start = i;
      break;
    }
  }
  for (let i = samples.length - 1; i >= 0; i--) {
    if (Math.abs(samples[i]) > threshold) {
      end = i;
      break;
    }
  }
  const pad = Math.floor((padMs / 1000) * sampleRate);
  start = Math.max(0, start - pad);
  end = Math.min(samples.length - 1, end + pad);
  if (end <= start) return samples;
  return samples.slice(start, end + 1);
}

/** Build a transcription-ready WAV blob from raw PCM samples. */
export function pcmToWavBlob(
  samples: Float32Array,
  sampleRate: number = STT_SAMPLE_RATE,
): Blob {
  const processed = normalizeGain(trimSilence(samples, sampleRate));
  return new Blob([encodeWav(processed, sampleRate)], { type: "audio/wav" });
}

/**
 * Legacy path: convert a lossy MediaRecorder blob to WAV.
 * Prefer direct PCM capture in useRecorder when possible.
 */
export async function blobToWav(blob: Blob, targetSampleRate = STT_SAMPLE_RATE): Promise<Blob> {
  const arrayBuffer = await blob.arrayBuffer();
  const audioContext = new AudioContext();
  try {
    const decoded = await audioContext.decodeAudioData(arrayBuffer.slice(0));
    const mono = audioContext.createBuffer(1, decoded.length, decoded.sampleRate);
    const out = mono.getChannelData(0);
    for (let ch = 0; ch < decoded.numberOfChannels; ch++) {
      const channel = decoded.getChannelData(ch);
      for (let i = 0; i < decoded.length; i++) {
        out[i] += channel[i] / decoded.numberOfChannels;
      }
    }
    const resampled = resamplePcm(out, decoded.sampleRate, targetSampleRate);
    return pcmToWavBlob(resampled, targetSampleRate);
  } finally {
    await audioContext.close();
  }
}

function encodeWav(samples: Float32Array, sampleRate: number): ArrayBuffer {
  const numChannels = 1;
  const bytesPerSample = 2;
  const blockAlign = numChannels * bytesPerSample;
  const dataSize = samples.length * bytesPerSample;
  const bufferLength = 44 + dataSize;
  const view = new DataView(new ArrayBuffer(bufferLength));

  writeString(view, 0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  writeString(view, 8, "WAVE");
  writeString(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * blockAlign, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bytesPerSample * 8, true);
  writeString(view, 36, "data");
  view.setUint32(40, dataSize, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i++, offset += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return view.buffer;
}

function writeString(view: DataView, offset: number, text: string): void {
  for (let i = 0; i < text.length; i++) {
    view.setUint8(offset + i, text.charCodeAt(i));
  }
}
