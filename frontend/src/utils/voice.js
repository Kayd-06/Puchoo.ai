// Permission prompts cannot be dismissed programmatically; cancel ownership and
// stop every late stream instead. Abort also clears the permission timeout.
export function requestMicrophone(timeoutMs = 20000, { signal } = {}) {
  return new Promise((resolve, reject) => {
    let settled = false;
    let timer;
    const finish = (error, stream) => {
      if (settled) {
        stream?.getTracks().forEach((track) => track.stop());
        return;
      }
      settled = true;
      window.clearTimeout(timer);
      signal?.removeEventListener('abort', abort);
      if (error) reject(error);
      else resolve(stream);
    };
    const abort = () => finish(new DOMException('Recording cancelled', 'AbortError'));
    if (signal?.aborted) {
      abort();
      return;
    }
    signal?.addEventListener('abort', abort, { once: true });
    timer = window.setTimeout(
      () =>
        finish(
          new Error(
            'Microphone permission is still pending. Allow microphone access in your browser, then try again.',
          ),
        ),
      timeoutMs,
    );
    try {
      navigator.mediaDevices.getUserMedia({ audio: true }).then(
        (stream) => finish(null, stream),
        (error) => finish(error),
      );
    } catch (error) {
      finish(error);
    }
  });
}

export function disposeVoiceCapture(operation) {
  if (!operation) return;
  operation.controller.abort();
  const recorder = operation.recorder;
  if (recorder) {
    recorder.onstop = recorder.ondataavailable = recorder.onerror = null;
    try {
      if (recorder.state !== 'inactive') recorder.stop();
    } catch {
      /* Still release tracks. */
    }
  }
  operation.stream?.getTracks().forEach((track) => track.stop());
  operation.stream = null;
  operation.chunks.length = 0;
}

export async function playAnswerAudio(audio) {
  try {
    await audio.play();
    return 'playing';
  } catch (error) {
    // Keep the generated clip so the next explicit tap can play it on mobile.
    if (error.name === 'NotAllowedError') return 'paused';
    throw error;
  }
}
