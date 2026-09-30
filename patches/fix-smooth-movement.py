from pathlib import Path

# Decouple accessibility gestures from the inference loop. Movement commands are
# coalesced to the newest vector and played back-to-back, eliminating the gap
# where inference used to run after every 220 ms swipe.
p = Path('project/input/src/main/java/dev/pylarl/input/AccessibilityInputController.kt')
p.write_text(r'''package dev.pylarl.input

import dev.pylarl.botcore.action.BotAction
import dev.pylarl.botcore.model.DisplayGeometry
import dev.pylarl.botcore.model.InputStatus
import kotlinx.coroutines.flow.StateFlow

class AccessibilityInputController : InputController {
    override val status: StateFlow<InputStatus> get() = PylaAccessibilityService.status
    override val foregroundPackage: StateFlow<String?> get() = PylaAccessibilityService.foreground

    override suspend fun dispatch(action: BotAction, geometry: DisplayGeometry): Result<Unit> {
        val service = PylaAccessibilityService.instance
            ?: return Result.failure(IllegalStateException("input service unavailable"))
        val plan = GesturePlanCompiler.compile(action, geometry)
            ?: return Result.failure(IllegalArgumentException("unsupported display geometry"))
        return if (plan is GesturePlan.Cancel) {
            GestureDispatchQueue.cancel(service)
        } else {
            GestureDispatchQueue.offer(plan)
        }
    }

    override suspend fun releaseAll() {
        val service = PylaAccessibilityService.instance ?: return
        GestureDispatchQueue.cancel(service)
    }
}
''')

p = Path('project/input/src/main/kotlin/dev/pylarl/input/GestureDispatchQueue.kt')
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(r'''package dev.pylarl.input

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

/**
 * Keeps inference independent from Accessibility gesture duration.
 *
 * Movement is coalesced: while one joystick swipe is active, inference can keep
 * producing newer directions. As soon as the active swipe completes, the latest
 * direction starts immediately instead of waiting for another inference pass.
 */
internal object GestureDispatchQueue {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val lock = Any()
    private val controls = ArrayDeque<GesturePlan>()
    private var latestMove: GesturePlan.Stroke? = null
    private var draining = false
    private var generation = 0L

    fun offer(plan: GesturePlan): Result<Unit> {
        synchronized(lock) {
            when (plan) {
                GesturePlan.Cancel -> return Result.failure(IllegalArgumentException("cancel must use cancel()"))
                is GesturePlan.Stroke -> {
                    if (plan.pointerId == 1) {
                        // Keep the joystick down slightly longer than the source's 220 ms
                        // so a new inference result is normally ready before completion.
                        latestMove = plan.copy(durationMs = maxOf(plan.durationMs, 320L))
                    } else {
                        controls.addLast(plan)
                    }
                }
            }
            if (!draining) {
                draining = true
                val myGeneration = generation
                scope.launch { drain(myGeneration) }
            }
        }
        return Result.success(Unit)
    }

    suspend fun cancel(service: PylaAccessibilityService): Result<Unit> {
        synchronized(lock) {
            generation++
            latestMove = null
            controls.clear()
            draining = false
        }
        // Intentionally dispatch outside the serial queue so an active long move
        // is cancelled immediately on pause/stop/death recovery.
        return service.execute(GesturePlan.Cancel)
    }

    private suspend fun drain(myGeneration: Long) {
        while (true) {
            val next = synchronized(lock) {
                if (generation != myGeneration) return
                when {
                    controls.isNotEmpty() -> controls.removeFirst()
                    latestMove != null -> latestMove.also { latestMove = null }
                    else -> {
                        draining = false
                        null
                    }
                }
            } ?: return

            val service = PylaAccessibilityService.instance
            if (service == null) {
                synchronized(lock) {
                    latestMove = null
                    controls.clear()
                    draining = false
                }
                return
            }

            // Completion/cancellation no longer blocks inference; it only paces
            // this dedicated gesture queue.
            service.execute(next)
        }
    }
}
''')

print('smooth movement queue patch applied')
