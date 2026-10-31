// A permission prompt may stay unanswered indefinitely. Release late streams
// after a timeout so a retry cannot leave a hidden microphone running.
export function requestMicrophone(timeoutMs = 20000) {
  return new Promise((resolve, reject) => {
    let expired = false;
    const timer = window.setTimeout(() => {
      expired = true;
      reject(
        new Error(
          'Microphone permission is still pending. Allow microphone access in your browser, then try again.',
        ),
      );
    }, timeoutMs);
    navigator.mediaDevices.getUserMedia({ audio: true }).then(
      (stream) => {
        if (expired) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        window.clearTimeout(timer);
        resolve(stream);
      },
      (error) => {
        window.clearTimeout(timer);
        reject(error);
      },
    );
  });
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
