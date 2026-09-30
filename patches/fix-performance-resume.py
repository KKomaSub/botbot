from pathlib import Path

# 1) Reduce inference work: MAIN every frame, TILE at a preset-dependent cadence and cache its last detections.
p = Path("project/vision/src/main/kotlin/dev/pylarl/vision/OnnxInferenceEngine.kt")
p.write_text(r'''package dev.pylarl.vision

import dev.pylarl.botcore.config.BotConfig
import dev.pylarl.botcore.config.PerformancePreset
import dev.pylarl.capture.CapturedFrame
import dev.pylarl.vision.model.InferenceSessionFactory
import dev.pylarl.vision.model.ModelId
import dev.pylarl.vision.model.ModelSession

class OnnxInferenceEngine(
    private val factory: InferenceSessionFactory,
    private val models: List<ModelId> = listOf(ModelId.MAIN, ModelId.TILE),
) : InferenceEngine {
    private data class Entry(val model: ModelId, val session: ModelSession)

    private var sessions: List<Entry> = emptyList()
    private var activeProvider: InferenceProvider? = null
    private var fallbackUsed = false
    private var preset: PerformancePreset = PerformancePreset.BALANCED
    private var frameIndex = 0L
    private val cachedDetections = mutableMapOf<ModelId, List<VisionDetection>>()

    @Synchronized override fun initialize(config: BotConfig): InferenceProvider {
        closeSessions()
        fallbackUsed = false
        preset = config.performancePreset
        frameIndex = 0L
        cachedDetections.clear()
        if (config.preferNnapi) {
            try { installProvider(InferenceProvider.NNAPI); return InferenceProvider.NNAPI }
            catch (_: Throwable) { fallbackUsed = true }
        }
        installProvider(InferenceProvider.CPU)
        return InferenceProvider.CPU
    }

    @Synchronized override fun infer(frame: CapturedFrame): VisionFrameResult {
        val started = System.nanoTime()
        val provider = activeProvider ?: error("Inference engine is not initialized")
        return try {
            VisionFrameResult(runScheduled(frame), provider, System.nanoTime() - started)
        } catch (first: Throwable) {
            if (provider != InferenceProvider.NNAPI || fallbackUsed) throw first
            fallbackUsed = true
            installProvider(InferenceProvider.CPU)
            VisionFrameResult(runScheduled(frame), InferenceProvider.CPU, System.nanoTime() - started)
        }
    }

    @Synchronized override fun provider(): InferenceProvider? = activeProvider

    private fun intervalFor(model: ModelId): Long = when (model) {
        ModelId.TILE -> when (preset) {
            PerformancePreset.PERFORMANCE -> 2L
            PerformancePreset.BALANCED -> 4L
            PerformancePreset.BATTERY -> 8L
        }
        else -> 1L
    }

    private fun runScheduled(frame: CapturedFrame): List<VisionDetection> = buildList {
        val currentFrame = frameIndex++
        for (entry in sessions) {
            val interval = intervalFor(entry.model)
            if (currentFrame % interval == 0L || entry.model !in cachedDetections) {
                cachedDetections[entry.model] = entry.session.run(frame)
            }
            addAll(cachedDetections[entry.model].orEmpty())
        }
    }

    private fun installProvider(provider: InferenceProvider) {
        closeSessions()
        cachedDetections.clear()
        frameIndex = 0L
        val opened = mutableListOf<Entry>()
        try {
            for (model in models) {
                val session = factory.create(model, provider)
                session.warmUp()
                opened += Entry(model, session)
            }
            sessions = opened.toList()
            activeProvider = provider
        } catch (t: Throwable) {
            opened.forEach { runCatching { it.session.close() } }
            sessions = emptyList()
            activeProvider = null
            throw t
        }
    }

    private fun closeSessions() {
        sessions.forEach { runCatching { it.session.close() } }
        sessions = emptyList()
        activeProvider = null
        cachedDetections.clear()
    }

    @Synchronized override fun close() = closeSessions()
}
''')

# 2) Reuse the large CHW float buffer instead of allocating FloatArray + direct buffer on every model invocation.
p = Path("project/vision/src/main/kotlin/dev/pylarl/vision/TensorPreprocessor.kt")
p.write_text(r'''package dev.pylarl.vision

import dev.pylarl.capture.CapturedFrame
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.FloatBuffer

object TensorPreprocessor {
    private data class Scratch(val width: Int, val height: Int, val buffer: FloatBuffer)
    private val scratch = ThreadLocal<Scratch>()

    fun prepareRgba(frame: CapturedFrame, inputWidth: Int = 640, inputHeight: Int = 640): FloatBuffer {
        require(frame.width > 0 && frame.height > 0 && inputWidth > 0 && inputHeight > 0)
        val count = inputWidth * inputHeight * 3
        var local = scratch.get()
        if (local == null || local.width != inputWidth || local.height != inputHeight) {
            local = Scratch(
                inputWidth,
                inputHeight,
                ByteBuffer.allocateDirect(count * 4).order(ByteOrder.nativeOrder()).asFloatBuffer(),
            )
            scratch.set(local)
        }
        val out = local.buffer
        out.clear()
        val src = frame.rgba.duplicate()
        val plane = inputWidth * inputHeight
        for (y in 0 until inputHeight) {
            val sy = (y.toLong() * frame.height / inputHeight).toInt().coerceAtMost(frame.height - 1)
            for (x in 0 until inputWidth) {
                val sx = (x.toLong() * frame.width / inputWidth).toInt().coerceAtMost(frame.width - 1)
                val pixel = (sy * frame.width + sx) * 4
                val offset = y * inputWidth + x
                out.put(offset, (src.get(pixel).toInt() and 0xff) / 255f)
                out.put(plane + offset, (src.get(pixel + 1).toInt() and 0xff) / 255f)
                out.put(2 * plane + offset, (src.get(pixel + 2).toInt() and 0xff) / 255f)
            }
        }
        out.position(0)
        out.limit(count)
        return out
    }
}
''')

# 3) Replace per-pixel screen copy with row bulk-copy and recycle direct buffers after the runtime closes a frame.
p = Path("project/capture/src/main/java/dev/pylarl/capture/MediaProjectionFrameSource.kt")
p.write_text(r'''package dev.pylarl.capture

import android.content.Context
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Handler
import android.os.HandlerThread
import java.nio.ByteBuffer
import java.util.ArrayDeque
import java.util.concurrent.atomic.AtomicBoolean

class MediaProjectionFrameSource(
    context: Context,
    private val factory: ProjectionResourceFactory = AndroidProjectionResourceFactory(context),
) : FrameSource {
    private var mailbox = LatestFrameMailbox()
    private var resources: ProjectionResources? = null
    private val stopped = AtomicBoolean(true)
    override val frames get() = mailbox.frames

    override suspend fun start(grant: ProjectionGrant) {
        if (!stopped.compareAndSet(true, false)) return
        mailbox = LatestFrameMailbox()
        resources = factory.create(
            grant,
            onProjectionStopped = {
                if (stopped.compareAndSet(false, true)) {
                    mailbox.close()
                    resources?.close()
                    resources = null
                }
            },
            onFrame = { mailbox.offer(it) },
        )
    }

    override suspend fun stop() {
        if (!stopped.compareAndSet(false, true)) return
        resources?.close()
        resources = null
        mailbox.close()
    }
}

private class AndroidProjectionResourceFactory(context: Context) : ProjectionResourceFactory {
    private val appContext = context.applicationContext

    override fun create(
        grant: ProjectionGrant,
        onProjectionStopped: () -> Unit,
        onFrame: (CapturedFrame) -> Unit,
    ): ProjectionResources {
        val manager = appContext.getSystemService(MediaProjectionManager::class.java)
        val projection = requireNotNull(manager.getMediaProjection(grant.resultCode, requireNotNull(grant.data) { "Projection intent is required" }))
        val metrics = appContext.resources.displayMetrics
        val width = maxOf(metrics.widthPixels, metrics.heightPixels)
        val height = minOf(metrics.widthPixels, metrics.heightPixels)
        val frameBytes = width * height * 4
        val pool = ArrayDeque<ByteBuffer>(3)
        fun obtainBuffer(): ByteBuffer = synchronized(pool) {
            (if (pool.isEmpty()) null else pool.removeFirst()) ?: ByteBuffer.allocateDirect(frameBytes)
        }.apply { clear() }
        fun recycleBuffer(buffer: ByteBuffer) {
            buffer.clear()
            synchronized(pool) { if (pool.size < 3) pool.addLast(buffer) }
        }

        val thread = HandlerThread("pyla-capture").apply { start() }
        val handler = Handler(thread.looper)
        val reader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2)
        val resources = AndroidProjectionResources(projection, reader, thread)
        projection.registerCallback(object : MediaProjection.Callback() {
            override fun onStop() = onProjectionStopped()
        }, handler)
        reader.setOnImageAvailableListener({ source ->
            val image = source.acquireLatestImage() ?: return@setOnImageAvailableListener
            var frame: CapturedFrame? = null
            try {
                val plane = image.planes.firstOrNull() ?: return@setOnImageAvailableListener
                val pixelStride = plane.pixelStride
                val rowStride = plane.rowStride
                val src = plane.buffer
                val packed = obtainBuffer()
                if (pixelStride == 4) {
                    val rowBytes = width * 4
                    for (y in 0 until height) {
                        val rowStart = y * rowStride
                        if (rowStart + rowBytes > src.limit()) break
                        val row = src.duplicate()
                        row.position(rowStart)
                        row.limit(rowStart + rowBytes)
                        packed.put(row)
                    }
                } else {
                    for (y in 0 until height) {
                        val rowStart = y * rowStride
                        for (x in 0 until width) {
                            val pos = rowStart + x * pixelStride
                            if (pos + 3 < src.limit()) {
                                packed.put(src.get(pos))
                                packed.put(src.get(pos + 1))
                                packed.put(src.get(pos + 2))
                                packed.put(src.get(pos + 3))
                            }
                        }
                    }
                }
                packed.flip()
                val captured = CapturedFrame(width, height, image.timestamp, packed) { recycleBuffer(packed) }
                frame = captured
                onFrame(captured)
                frame = null // mailbox owns it now and will close/recycle it.
            } finally {
                frame?.close()
                image.close()
            }
        }, handler)
        val display = projection.createVirtualDisplay(
            "Pyla-RL Capture", width, height, metrics.densityDpi,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            reader.surface, null, handler,
        )
        resources.virtualDisplay = display
        return resources
    }
}

private class AndroidProjectionResources(
    private val projection: MediaProjection,
    private val reader: ImageReader,
    private val thread: HandlerThread,
) : ProjectionResources {
    @Volatile var virtualDisplay: android.hardware.display.VirtualDisplay? = null
    private val closed = AtomicBoolean(false)
    override fun close() {
        if (!closed.compareAndSet(false, true)) return
        reader.setOnImageAvailableListener(null, null)
        virtualDisplay?.release(); virtualDisplay = null
        reader.close()
        runCatching { projection.stop() }
        thread.quitSafely()
    }
}
''')

# 4) Foreground tracking: only window changes should change the package used by the runtime safety gate.
p = Path("project/input/src/main/java/dev/pylarl/input/PylaAccessibilityService.kt")
s = p.read_text()
old = '''    override fun onAccessibilityEvent(event: AccessibilityEvent?) {\n        event?.packageName?.toString()?.let { _foreground.value = it }\n    }'''
new = '''    override fun onAccessibilityEvent(event: AccessibilityEvent?) {\n        event ?: return\n        if (event.eventType != AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED &&\n            event.eventType != AccessibilityEvent.TYPE_WINDOWS_CHANGED\n        ) return\n        val activePackage = rootInActiveWindow?.packageName?.toString()\n            ?: event.packageName?.toString()\n        if (!activePackage.isNullOrBlank()) _foreground.value = activePackage\n    }'''
if old not in s:
    raise SystemExit("accessibility foreground block not found")
p.write_text(s.replace(old, new, 1))

# 5) Runtime: exclude model warm-up from FPS and debounce transient foreground/input noise.
p = Path("project/runtime/src/main/kotlin/dev/pylarl/runtime/BotRuntimeCoordinator.kt")
s = p.read_text()
if 'import kotlinx.coroutines.delay\n' not in s:
    s = s.replace('import kotlinx.coroutines.channels.ClosedReceiveChannelException\n', 'import kotlinx.coroutines.channels.ClosedReceiveChannelException\nimport kotlinx.coroutines.delay\n')
s = s.replace('''    private var readinessJob: Job? = null\n''', '''    private var readinessJob: Job? = null\n    private var readinessGraceJob: Job? = null\n''', 1)
s = s.replace('''        metricsStartedNanos = System.nanoTime()\n        resumeRequested = false\n''', '''        metricsStartedNanos = 0L\n        resumeRequested = false\n        readinessGraceJob?.cancel()\n        readinessGraceJob = null\n''', 1)
s = s.replace('''        mutableSnapshot.value = mutableSnapshot.value.copy(phase = RuntimePhase.CAPTURING)\n\n        val scope = CoroutineScope''', '''        mutableSnapshot.value = mutableSnapshot.value.copy(phase = RuntimePhase.CAPTURING)\n        // Do not count model creation / NNAPI warm-up against the live FPS metric.\n        captureCount = 0\n        inferenceCount = 0\n        metricsStartedNanos = System.nanoTime()\n\n        val scope = CoroutineScope''', 1)
s = s.replace('''    suspend fun pause() = lifecycleMutex.withLock {\n        resumeRequested = false\n''', '''    suspend fun pause() = lifecycleMutex.withLock {\n        resumeRequested = false\n        readinessGraceJob?.cancel()\n        readinessGraceJob = null\n''', 1)
s = s.replace('''        readinessJob = null\n        frameMailbox = null\n''', '''        readinessJob = null\n        readinessGraceJob?.cancel()\n        readinessGraceJob = null\n        frameMailbox = null\n''', 1)
s = s.replace('''        if (!isReadyForRunning()) {\n            enterPausedForReadiness()\n            return\n        }\n''', '''        // Foreground/input readiness is debounced by onReadinessChanged().\n        // A one-off SystemUI/window event must not immediately force PAUSED.\n        if (!isReadyForRunning()) return\n''', 1)
old_readiness = '''    private suspend fun onReadinessChanged(status: InputStatus, foreground: String?) {\n        mutableSnapshot.value = mutableSnapshot.value.copy(inputStatus = status, foregroundPackage = foreground)\n        if (mutableSnapshot.value.phase == RuntimePhase.RUNNING && !isReadyForRunning()) {\n            enterPausedForReadiness()\n        } else if (mutableSnapshot.value.phase == RuntimePhase.CAPTURING && isReadyForRunning()) {\n            pointersReleased = false\n            mutableSnapshot.value = mutableSnapshot.value.copy(phase = RuntimePhase.RUNNING, lastError = null)\n        } else if (mutableSnapshot.value.phase == RuntimePhase.PAUSED && resumeRequested) {\n            resumeIfReady()\n        }\n    }\n'''
new_readiness = '''    private suspend fun onReadinessChanged(status: InputStatus, foreground: String?) {\n        mutableSnapshot.value = mutableSnapshot.value.copy(inputStatus = status, foregroundPackage = foreground)\n        if (isReadyForRunning()) {\n            readinessGraceJob?.cancel()\n            readinessGraceJob = null\n            when (mutableSnapshot.value.phase) {\n                RuntimePhase.CAPTURING -> {\n                    pointersReleased = false\n                    mutableSnapshot.value = mutableSnapshot.value.copy(phase = RuntimePhase.RUNNING, lastError = null)\n                }\n                RuntimePhase.PAUSED -> if (resumeRequested) resumeIfReady()\n                else -> Unit\n            }\n        } else if (mutableSnapshot.value.phase == RuntimePhase.RUNNING) {\n            scheduleReadinessPause()\n        }\n    }\n\n    private fun scheduleReadinessPause() {\n        if (readinessGraceJob?.isActive == true) return\n        val scope = runScope ?: return\n        readinessGraceJob = scope.launch {\n            delay(350L)\n            if (mutableSnapshot.value.phase == RuntimePhase.RUNNING && !isReadyForRunning()) {\n                enterPausedForReadiness()\n            }\n        }\n    }\n'''
if old_readiness not in s:
    raise SystemExit("runtime readiness block not found")
s = s.replace(old_readiness, new_readiness, 1)
p.write_text(s)

print("performance + resume stability patch applied")
