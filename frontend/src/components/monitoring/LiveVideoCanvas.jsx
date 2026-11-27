import React, { useEffect, useRef } from 'react';

const MAX_FRAME_AGE_MS = 80;

function getLiveFeedWsUrl() {
  const apiBase = import.meta.env.VITE_API_URL;
  if (apiBase) {
    return `${apiBase.replace(/^http/i, 'ws')}/ws/live-feed`;
  }
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const host = window.location.hostname || 'localhost';
  return `${proto}://${host}:8000/ws/live-feed`;
}

/**
 * Hardware-accelerated HTML5 <canvas> video player backed by /ws/live-feed.
 * Bypasses React state/Virtual DOM during 20 FPS rendering, enforces
 * timestamp age-gating (>80ms dropped), and explicitly closes ImageBitmaps
 * to prevent Chromium GPU memory leaks.
 */
const LiveVideoCanvas = ({
  reconnectKey = 0,
  onFpsUpdate,
  onStreamError,
  onStreamReady,
  className = 'w-full h-full object-contain',
}) => {
  const canvasRef = useRef(null);
  const onFpsRef = useRef(onFpsUpdate);
  const onErrorRef = useRef(onStreamError);
  const onReadyRef = useRef(onStreamReady);

  useEffect(() => {
    onFpsRef.current = onFpsUpdate;
    onErrorRef.current = onStreamError;
    onReadyRef.current = onStreamReady;
  }, [onFpsUpdate, onStreamError, onStreamReady]);

  useEffect(() => {
    let unmounted = false;
    let ws = null;
    let reconnectTimer = null;
    let errorGraceTimer = null;
    let isDecoding = false;
    let pendingJpeg = null;
    let minClockOffset = null;
    let renderedFrames = 0;
    let lastFpsTick = performance.now();
    let hasReceivedFrame = false;
    let failedAttempts = 0;

    const renderBuffer = async (jpegBytes) => {
      if (unmounted) return;
      isDecoding = true;
      let bitmap = null;

      try {
        const blob = new Blob([jpegBytes], { type: 'image/jpeg' });
        bitmap = await createImageBitmap(blob);

        if (unmounted || !canvasRef.current) return;

        const canvas = canvasRef.current;
        if (canvas.width !== bitmap.width || canvas.height !== bitmap.height) {
          canvas.width = bitmap.width;
          canvas.height = bitmap.height;
        }

        const ctx = canvas.getContext('2d', { alpha: false });
        if (ctx) {
          ctx.drawImage(bitmap, 0, 0);
        }

        if (!hasReceivedFrame) {
          hasReceivedFrame = true;
          onReadyRef.current?.();
        }

        renderedFrames += 1;
        const nowPerf = performance.now();
        if (nowPerf - lastFpsTick >= 1000) {
          const fps = Math.round((renderedFrames * 1000) / (nowPerf - lastFpsTick));
          renderedFrames = 0;
          lastFpsTick = nowPerf;
          onFpsRef.current?.(fps);
        }
      } catch (err) {
        // Ignore transient decode errors on interrupted frames
      } finally {
        if (bitmap) {
          bitmap.close(); // Mandatory GPU texture memory release
        }
        isDecoding = false;

        // If a newer frame arrived while GPU was busy, immediately draw the newest one
        if (!unmounted && pendingJpeg) {
          const next = pendingJpeg;
          pendingJpeg = null;
          renderBuffer(next);
        }
      }
    };

    const connect = () => {
      if (unmounted) return;
      const wsUrl = getLiveFeedWsUrl();

      try {
        ws = new WebSocket(wsUrl);
        ws.binaryType = 'arraybuffer';

        ws.onopen = () => {
          if (unmounted) return;
          failedAttempts = 0;
          if (errorGraceTimer) {
            clearTimeout(errorGraceTimer);
            errorGraceTimer = null;
          }
          minClockOffset = null;
          onErrorRef.current?.(false);
          onReadyRef.current?.();
        };

        ws.onmessage = (event) => {
          if (unmounted || !(event.data instanceof ArrayBuffer)) return;
          if (event.data.byteLength <= 8) return;

          // Read 8-byte big-endian float64 server capture timestamp (ms)
          const serverTs = new DataView(event.data).getFloat64(0, false);
          const localNow = Date.now();
          const rawOffset = localNow - serverTs;

          // Track baseline clock offset to measure true transit delay without clock-skew bugs
          if (minClockOffset === null || rawOffset < minClockOffset) {
            minClockOffset = rawOffset;
          } else {
            minClockOffset += 0.25; // Gentle drift tracking
          }

          const transitDelayMs = rawOffset - minClockOffset;
          if (transitDelayMs > MAX_FRAME_AGE_MS) {
            // Drop stale delayed frame instead of playing out buffered lag
            return;
          }

          const jpegSlice = event.data.slice(8);
          if (isDecoding) {
            // Overwrite older unrendered frame; keep queue strictly at size 1
            pendingJpeg = jpegSlice;
          } else {
            renderBuffer(jpegSlice);
          }
        };

        ws.onerror = () => {
          if (unmounted) return;
          failedAttempts += 1;
          // Grace period avoids false "Offline" flicker during React StrictMode double-mount or 1s reload
          if (!hasReceivedFrame && failedAttempts >= 2) {
            onErrorRef.current?.(true);
          } else if (!hasReceivedFrame && !errorGraceTimer) {
            errorGraceTimer = setTimeout(() => {
              if (!unmounted && !hasReceivedFrame) {
                onErrorRef.current?.(true);
              }
            }, 1500);
          }
        };

        ws.onclose = () => {
          if (unmounted) return;
          reconnectTimer = setTimeout(connect, 1200);
        };
      } catch (e) {
        if (!unmounted) {
          onErrorRef.current?.(true);
          reconnectTimer = setTimeout(connect, 1500);
        }
      }
    };

    connect();

    return () => {
      unmounted = true;
      pendingJpeg = null;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (errorGraceTimer) clearTimeout(errorGraceTimer);
      if (ws) {
        ws.onopen = null;
        ws.onmessage = null;
        ws.onerror = null;
        ws.onclose = null;
        if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
          ws.close();
        }
      }
    };
  }, [reconnectKey]);

  return (
    <canvas
      ref={canvasRef}
      width={640}
      height={480}
      aria-label="Live Video Stream Feed"
      className={className}
    />
  );
};

export default React.memo(LiveVideoCanvas);
