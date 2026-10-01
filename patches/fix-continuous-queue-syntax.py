from pathlib import Path
p=Path('project/input/src/main/kotlin/dev/pylarl/input/GestureDispatchQueue.kt')
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(r'''package dev.pylarl.input

import android.os.SystemClock
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

internal object GestureDispatchQueue {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val lock = Any()
    private val controls = ArrayDeque<GesturePlan.Stroke>()
    private var latestMove: GesturePlan.Stroke? = null
    private var lastMoveAt = 0L
    private var draining = false
    private var generation = 0L

    fun offer(plan: GesturePlan): Result<Unit> {
        synchronized(lock) {
            when (plan) {
                GesturePlan.Cancel -> return Result.failure(IllegalArgumentException("cancel must use cancel()"))
                is GesturePlan.Stroke -> {
                    if (plan.pointerId == 1) {
                        latestMove = plan.copy(durationMs = 140L)
                        lastMoveAt = SystemClock.uptimeMillis()
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
            lastMoveAt = 0L
            draining = false
        }
        service.finishContinuousMove()
        return service.execute(GesturePlan.Cancel)
    }

    private suspend fun drain(myGeneration: Long) {
        var heldMove: GesturePlan.Stroke? = null
        try {
            while (true) {
                val packet: Pair<GesturePlan.Stroke?, GesturePlan.Stroke?>? = synchronized(lock) {
                    if (generation != myGeneration) return

                    latestMove?.let {
                        heldMove = it
                        latestMove = null
                    }

                    val keepMoving = heldMove != null &&
                        SystemClock.uptimeMillis() - lastMoveAt <= 520L
                    val control = if (controls.isNotEmpty()) controls.removeFirst() else null

                    if (!keepMoving && control == null) {
                        draining = false
                        null
                    } else {
                        Pair(if (keepMoving) heldMove else null, control)
                    }
                }

                if (packet == null) break
                val service = PylaAccessibilityService.instance ?: break
                val move = packet.first
                val control = packet.second

                if (move != null) {
                    val result = service.executeContinuousMoveWithControl(
                        move.copy(durationMs = 140L),
                        control,
                    )
                    if (result.isFailure) {
                        service.finishContinuousMove()
                        heldMove = null
                    }
                } else {
                    service.finishContinuousMove()
                    if (control != null) service.execute(control)
                }
            }
        } finally {
            PylaAccessibilityService.instance?.finishContinuousMove()
            synchronized(lock) {
                if (generation == myGeneration) draining = false
            }
        }
    }
}
''', encoding='utf-8')
print('continuous movement queue syntax fix applied')
