/**
 * useVoiceInput: ChatGPT-style audio recording, level analysis, and transcription.
 *
 * Encapsulates the complete recording lifecycle:
 *   - Secure context detection: navigator.mediaDevices.getUserMedia requires HTTPS or
 *     localhost (http://localhost / http://127.0.0.1).
 *   - AudioContext + AnalyserNode for live VU meter frequency bars (60fps, throttled).
 *   - MediaRecorder with feature-detected MIME type (audio/webm;codecs=opus -> audio/mp4).
 *   - Dual-path transcription: POST to backend /v1/transcribe, with automatic fallback
 *     to browser Web Speech API (webkitSpeechRecognition) when backend STT is not configured.
 *   - Zero leaked tracks: all MediaStream tracks and AudioContext nodes are closed on
 *     stop, cancel, and component unmount.
 *   - StrictMode & double-start guards.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../services/api'

export type VoiceState = 'idle' | 'requesting' | 'recording' | 'transcribing' | 'error'
export type VoiceErrorType = 'micDenied' | 'micNotFound' | 'transcribeFailed' | 'noSpeech'

interface UseVoiceInputOptions {
  lang?: string
  onTranscribed: (text: string) => void
  maxDurationSeconds?: number
}

interface SpeechRecognitionEventLike {
  resultIndex: number
  results: {
    length: number
    [index: number]: {
      isFinal: boolean
      [index: number]: { transcript: string }
    }
  }
}

interface SpeechRecognitionLike {
  continuous: boolean
  interimResults: boolean
  lang: string
  onresult: ((event: SpeechRecognitionEventLike) => void) | null
  onerror: ((event: unknown) => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
  abort: () => void
}

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike

function getSpeechRecognitionConstructor(): SpeechRecognitionConstructor | null {
  if (typeof window === 'undefined') return null
  const win = window as unknown as {
    SpeechRecognition?: SpeechRecognitionConstructor
    webkitSpeechRecognition?: SpeechRecognitionConstructor
  }
  return win.SpeechRecognition || win.webkitSpeechRecognition || null
}

function getSupportedMimeType(): string {
  if (typeof window === 'undefined' || typeof MediaRecorder === 'undefined') return ''
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/mp4',
    'audio/aac',
    'audio/ogg',
  ]
  for (const candidate of candidates) {
    if (typeof MediaRecorder.isTypeSupported === 'function' && MediaRecorder.isTypeSupported(candidate)) {
      return candidate
    }
  }
  return ''
}

const BAR_COUNT = 18

export function useVoiceInput({
  lang = 'en',
  onTranscribed,
  maxDurationSeconds = 300, // 5 minutes max
}: UseVoiceInputOptions) {
  const [state, setState] = useState<VoiceState>('idle')
  const [error, setError] = useState<VoiceErrorType | null>(null)
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const [levels, setLevels] = useState<number[]>(() => Array(BAR_COUNT).fill(0.08))

  // Refs for audio hardware and recording pipelines
  const streamRef = useRef<MediaStream | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const lastBlobRef = useRef<Blob | null>(null)
  const animFrameRef = useRef<number | null>(null)
  const timerRef = useRef<number | null>(null)
  const speechRecognitionRef = useRef<SpeechRecognitionLike | null>(null)
  const speechTextRef = useRef<string>('')
  const maxVolumeRef = useRef<number>(0)
  const isOperatingRef = useRef(false)
  const isMountedRef = useRef(true)

  // Check hardware & browser support
  const isSupported =
    typeof window !== 'undefined' &&
    !!(
      (navigator.mediaDevices && typeof navigator.mediaDevices.getUserMedia === 'function') ||
      getSpeechRecognitionConstructor()
    )

  const cleanupAudioPipeline = useCallback(() => {
    if (animFrameRef.current !== null) {
      cancelAnimationFrame(animFrameRef.current)
      animFrameRef.current = null
    }
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current)
      timerRef.current = null
    }
    if (recorderRef.current && recorderRef.current.state !== 'inactive') {
      try {
        recorderRef.current.stop()
      } catch {
        /* ignore if already stopped */
      }
    }
    recorderRef.current = null

    if (streamRef.current) {
      for (const track of streamRef.current.getTracks()) {
        track.stop()
      }
      streamRef.current = null
    }

    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      try {
        audioContextRef.current.close()
      } catch {
        /* ignore if already closed */
      }
      audioContextRef.current = null
    }
    analyserRef.current = null

    if (speechRecognitionRef.current) {
      try {
        speechRecognitionRef.current.abort()
      } catch {
        /* ignore */
      }
      speechRecognitionRef.current = null
    }

    setLevels(Array(BAR_COUNT).fill(0.08))
    isOperatingRef.current = false
  }, [])

  // Auto-cleanup on unmount to prevent leaked microphone indicators in the browser tab
  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
      cleanupAudioPipeline()
    }
  }, [cleanupAudioPipeline])

  // Stop recording and transcribe the captured audio
  const stopAndTranscribe = useCallback(async () => {
    if (state !== 'recording' && state !== 'requesting') return
    setState('transcribing')

    const duration = elapsedSeconds
    const mimeType = recorderRef.current?.mimeType || getSupportedMimeType()

    // Stop live recording tracks & timers
    cleanupAudioPipeline()

    // Minimum duration check for accidental tap or empty audio
    if (duration < 0.4 && chunksRef.current.length === 0 && !speechTextRef.current.trim()) {
      if (isMountedRef.current) {
        setError('noSpeech')
        setState('error')
      }
      return
    }

    const audioBlob =
      chunksRef.current.length > 0
        ? new Blob(chunksRef.current, { type: mimeType || 'audio/webm' })
        : null
    lastBlobRef.current = audioBlob

    let transcribedText = ''
    let hadBackendError = false

    // Primary path: Backend /v1/transcribe endpoint
    if (audioBlob && audioBlob.size > 200) {
      try {
        const res = await api.transcribe(audioBlob, lang)
        transcribedText = res.text.trim()
      } catch (err) {
        hadBackendError = true
        // If 503 or unreachable, fallback will be evaluated below
        if (!(err instanceof ApiError && err.status === 503)) {
          // Log other server errors silently while checking speech fallback
        }
      }
    }

    // Fallback path: Web Speech API result if backend didn't supply text
    if (!transcribedText && speechTextRef.current.trim()) {
      transcribedText = speechTextRef.current.trim()
    }

    if (!isMountedRef.current) return

    if (transcribedText) {
      onTranscribed(transcribedText)
      setError(null)
      setState('idle')
    } else if (maxVolumeRef.current < 0.02 && !hadBackendError) {
      // Audio was essentially silent
      setError('noSpeech')
      setState('error')
    } else {
      // Transcription failed and no speech could be recognized
      setError('transcribeFailed')
      setState('error')
    }
  }, [state, elapsedSeconds, lang, onTranscribed, cleanupAudioPipeline])

  // Auto-stop at max duration (e.g. 5 minutes)
  useEffect(() => {
    if (state === 'recording' && elapsedSeconds >= maxDurationSeconds) {
      void stopAndTranscribe()
    }
  }, [state, elapsedSeconds, maxDurationSeconds, stopAndTranscribe])

  // Start recording
  const startRecording = useCallback(async () => {
    if (isOperatingRef.current || state === 'recording' || state === 'transcribing') return
    isOperatingRef.current = true

    setError(null)
    setState('requesting')
    setElapsedSeconds(0)
    chunksRef.current = []
    speechTextRef.current = ''
    maxVolumeRef.current = 0

    // Note: navigator.mediaDevices.getUserMedia requires HTTPS or a secure context (localhost / 127.0.0.1).
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error('getUserMedia not available')
      }

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      })

      if (!isMountedRef.current) {
        for (const track of stream.getTracks()) track.stop()
        return
      }

      streamRef.current = stream

      // 1. Setup Web Audio AnalyserNode for live level visualization
      const AudioContextClass =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
      if (AudioContextClass) {
        const audioCtx = new AudioContextClass()
        audioContextRef.current = audioCtx
        if (audioCtx.state === 'suspended') {
          await audioCtx.resume()
        }
        const analyser = audioCtx.createAnalyser()
        analyser.fftSize = 64
        analyser.smoothingTimeConstant = 0.75
        analyserRef.current = analyser

        const source = audioCtx.createMediaStreamSource(stream)
        source.connect(analyser)

        const frequencyData = new Uint8Array(analyser.frequencyBinCount)

        const updateLevels = () => {
          if (!analyserRef.current) return
          analyserRef.current.getByteFrequencyData(frequencyData)

          // Sample BAR_COUNT bins across speech spectrum (~100Hz - 4000Hz)
          const step = Math.max(1, Math.floor(frequencyData.length / BAR_COUNT))
          const nextLevels: number[] = []
          let totalEnergy = 0

          for (let i = 0; i < BAR_COUNT; i++) {
            const val = frequencyData[Math.min(i * step, frequencyData.length - 1)] || 0
            const norm = val / 255
            totalEnergy += norm
            // Ensure small visual minimum (0.08) so bars remain visible
            nextLevels.push(Math.max(0.08, Math.min(1.0, norm)))
          }

          const avg = totalEnergy / BAR_COUNT
          if (avg > maxVolumeRef.current) {
            maxVolumeRef.current = avg
          }

          setLevels(nextLevels)
          animFrameRef.current = requestAnimationFrame(updateLevels)
        }
        animFrameRef.current = requestAnimationFrame(updateLevels)
      }

      // 2. Setup MediaRecorder
      const mimeType = getSupportedMimeType()
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
      recorderRef.current = recorder

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          chunksRef.current.push(event.data)
        }
      }

      recorder.start(100) // Collect 100ms chunks

      // 3. Fallback Web Speech API listener (if supported in browser)
      const SpeechRecognitionClass = getSpeechRecognitionConstructor()
      if (SpeechRecognitionClass) {
        try {
          const recognition = new SpeechRecognitionClass()
          speechRecognitionRef.current = recognition
          recognition.continuous = true
          recognition.interimResults = true
          recognition.lang = lang === 'hi' ? 'hi-IN' : lang === 'auto' ? 'en-IN' : `${lang}-IN`

          recognition.onresult = (event: SpeechRecognitionEventLike) => {
            let combined = ''
            for (let i = 0; i < event.results.length; i++) {
              combined += event.results[i][0].transcript + ' '
            }
            speechTextRef.current = combined.trim()
          }

          recognition.onerror = () => {
            /* Speech recognition error, backend audio recording remains primary */
          }

          recognition.start()
        } catch {
          /* ignore Web Speech startup error */
        }
      }

      // 4. Elapsed time ticker
      timerRef.current = window.setInterval(() => {
        setElapsedSeconds((sec) => sec + 1)
      }, 1000)

      setState('recording')
    } catch (err: unknown) {
      cleanupAudioPipeline()
      if (!isMountedRef.current) return

      const errorObj = err as { name?: string }
      if (errorObj.name === 'NotAllowedError' || errorObj.name === 'PermissionDeniedError') {
        setError('micDenied')
      } else if (errorObj.name === 'NotFoundError' || errorObj.name === 'DevicesNotFoundError') {
        setError('micNotFound')
      } else {
        setError('transcribeFailed')
      }
      setState('error')
    }
  }, [state, lang, cleanupAudioPipeline])

  // Cancel recording and discard audio
  const cancelRecording = useCallback(() => {
    cleanupAudioPipeline()
    chunksRef.current = []
    speechTextRef.current = ''
    lastBlobRef.current = null
    setError(null)
    setElapsedSeconds(0)
    setState('idle')
  }, [cleanupAudioPipeline])

  // Retry transcription using the stored audio blob
  const retryTranscription = useCallback(async () => {
    if (!lastBlobRef.current || state === 'recording' || state === 'transcribing') return
    setState('transcribing')
    setError(null)

    try {
      const res = await api.transcribe(lastBlobRef.current, lang)
      const text = res.text.trim()
      if (text) {
        onTranscribed(text)
        setState('idle')
      } else {
        setError('noSpeech')
        setState('error')
      }
    } catch {
      if (isMountedRef.current) {
        setError('transcribeFailed')
        setState('error')
      }
    }
  }, [state, lang, onTranscribed])

  const clearError = useCallback(() => {
    setError(null)
  }, [])

  return {
    state,
    error,
    clearError,
    isSupported,
    elapsedSeconds,
    levels,
    startRecording,
    stopAndTranscribe,
    cancelRecording,
    retryTranscription,
    canRetry: !!lastBlobRef.current,
  }
}
