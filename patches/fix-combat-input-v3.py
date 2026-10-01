from pathlib import Path

ROOT = Path('project')

def write(rel: str, content: str) -> None:
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding='utf-8')

write('bot-core/src/main/kotlin/dev/pylarl/botcore/decision/EnemyTracker.kt', r'''package dev.pylarl.botcore.decision

import dev.pylarl.botcore.vision.Vector2
import java.util.ArrayDeque
import kotlin.math.abs
import kotlin.math.sqrt

/**
 * Tracks one already-associated target in PLAYER-RELATIVE screen coordinates.
 * Large frame-to-frame jumps are treated as target association changes instead
 * of target velocity.  This prevents predictive aim from being poisoned when
 * the nearest-enemy detector swaps identities.
 */
class EnemyTracker {
    private data class Sample(val position: Vector2, val timestampNanos: Long)

    private val samples = ArrayDeque<Sample>(7)
    private var velocity = Vector2(0f, 0f)
    private var lastPosition: Vector2? = null
    private var lastTimestampNanos: Long = 0L

    fun update(target: Vector2?, timestampNanos: Long): Vector2 {
        if (target == null) {
            reset()
            return velocity
        }

        val previous = lastPosition
        val previousTime = lastTimestampNanos
        if (previous != null && previousTime > 0L) {
            val dt = (timestampNanos - previousTime) / 1_000_000_000f
            if (dt <= 0f || dt > 0.55f) {
                reset()
            } else {
                // A real brawler cannot teleport this far between ordinary inference frames.
                // A jump above this envelope is almost always a detector/identity swap.
                val maxDelta = (62f + 650f * dt).coerceIn(90f, 175f)
                if (previous.distanceTo(target) > maxDelta) reset()
            }
        }

        lastPosition = target
        lastTimestampNanos = timestampNanos
        samples.addLast(Sample(target, timestampNanos))
        while (samples.size > 6) samples.removeFirst()
        while (samples.size >= 2 && timestampNanos - samples.first().timestampNanos > 500_000_000L) {
            samples.removeFirst()
        }

        // Two points are too noisy for a lead shot.  Wait for a third consistent observation.
        if (samples.size < 3) {
            if (samples.size <= 1) velocity = Vector2(0f, 0f)
            return velocity
        }

        val list = samples.toList()
        var vx = 0f
        var vy = 0f
        var weightSum = 0f
        for (i in 1 until list.size) {
            val a = list[i - 1]
            val b = list[i]
            val dt = (b.timestampNanos - a.timestampNanos) / 1_000_000_000f
            if (dt !in 0.015f..0.30f) continue
            var step = (b.position - a.position) * (1f / dt)
            val speed = step.length()
            if (speed > 950f) step = step * (950f / speed)
            val weight = i.toFloat() // favor recent consistent motion
            vx += step.x * weight
            vy += step.y * weight
            weightSum += weight
        }
        if (weightSum <= 0f) return velocity

        val raw = Vector2(vx / weightSum, vy / weightSum)
        val alpha = if (samples.size >= 5) 0.42f else 0.32f
        velocity = velocity * (1f - alpha) + raw * alpha
        if (velocity.length() < 18f) velocity = Vector2(0f, 0f)
        return velocity
    }

    fun confidence(): Float = ((samples.size - 1) / 3f).coerceIn(0f, 1f)
    fun reset() {
        samples.clear()
        velocity = Vector2(0f, 0f)
        lastPosition = null
        lastTimestampNanos = 0L
    }
    fun currentVelocity(): Vector2 = velocity

    companion object {
        data class Intercept(val point: Vector2, val flightSeconds: Float)

        /** Kept for API/test compatibility. Gameplay uses the more conservative capped lead below. */
        fun predictIntercept(
            shooter: Vector2,
            target: Vector2,
            targetVelocity: Vector2,
            projectileSpeedPxPerSecond: Float,
            fireDelaySeconds: Float = 0f,
            leadScale: Float = 1f,
        ): Intercept {
            if (projectileSpeedPxPerSecond <= 1f) return Intercept(target, 0f)
            val r = target - shooter
            val v = targetVelocity
            val s = projectileSpeedPxPerSecond
            val a = v.x * v.x + v.y * v.y - s * s
            val b = 2f * (r.x * v.x + r.y * v.y)
            val c = r.x * r.x + r.y * r.y
            val t = when {
                abs(a) < 1e-5f -> if (abs(b) < 1e-5f) 0f else (-c / b).coerceAtLeast(0f)
                else -> {
                    val d = b * b - 4f * a * c
                    if (d < 0f) 0f else {
                        val q = sqrt(d)
                        listOf((-b - q) / (2f * a), (-b + q) / (2f * a))
                            .filter { it > 0f }
                            .minOrNull() ?: 0f
                    }
                }
            }.coerceIn(0f, 1.0f)
            val total = (fireDelaySeconds + t * leadScale).coerceIn(0f, 0.75f)
            return Intercept(target + v * total, t)
        }

        fun leadShotAngle(
            shooter: Vector2,
            target: Vector2,
            targetVelocity: Vector2,
            projectileSpeedPxPerSecond: Float,
            fireDelaySeconds: Float = 0f,
            leadScale: Float = 1f,
        ): Float = (predictIntercept(
            shooter,
            target,
            targetVelocity,
            projectileSpeedPxPerSecond,
            fireDelaySeconds,
            leadScale,
        ).point - shooter).angleDegrees()
    }
}
''')

write('bot-core/src/main/kotlin/dev/pylarl/botcore/decision/GameplayDecisionEngine.kt', r'''package dev.pylarl.botcore.decision

import dev.pylarl.botcore.action.*
import dev.pylarl.botcore.combat.*
import dev.pylarl.botcore.config.BotConfig
import dev.pylarl.botcore.vision.*
import kotlin.math.*

class GameplayDecisionEngine {
    private val tracker = EnemyTracker()
    private val wallEscape = WallEscape()
    private var lastAttack = Long.MIN_VALUE / 2
    private var lastSuper = 0L
    private var strafeSide = 0f
    private var strafeSwitchAtNanos = 0L
    private var smoothedMoveAngle: Float? = null

    // Target association and dropout continuity.
    private var lockedTargetRelative: Vector2? = null
    private var lastTargetSeenNanos = 0L
    private var lastStableMoveAngle: Float? = null
    private var lastStableMoveAtNanos = 0L

    fun decide(observation: BotObservation, config: BotConfig): List<BotAction> {
        FogAvoidance.action(observation.fogEscapeVector)?.let { action ->
            rememberMove(action.angleDegrees, observation.timestampNanos)
            return listOf(action)
        }
        wallEscape.update(observation, config)?.let { action ->
            rememberMove(action.angleDegrees, observation.timestampNanos)
            return listOf(action)
        }

        val player = observation.player ?: run {
            clearTracking()
            return emptyList()
        }
        val p = player.footPosition()
        val profile = BrawlerCombatProfiles.forName(observation.currentBrawler ?: config.selectedBrawler)
        val target = selectTarget(p, observation.enemies, observation.timestampNanos)

        if (target == null) {
            val follow = TeamFollow.action(player, observation.teammates, config)
            if (follow != null) {
                rememberMove(follow.angleDegrees, observation.timestampNanos)
                return listOf(follow)
            }

            // A one/few-frame detector dropout must never invent 0 degrees (hard-right).
            // Keep the last legitimate direction briefly so the joystick remains continuous.
            val last = lastStableMoveAngle
            val age = observation.timestampNanos - lastStableMoveAtNanos
            if (config.alwaysMove && last != null && age in 0L..900_000_000L) {
                return listOf(MoveVector(last, 145f, 320L))
            }

            if (lastTargetSeenNanos > 0L && observation.timestampNanos - lastTargetSeenNanos > 900_000_000L) {
                lockedTargetRelative = null
                tracker.reset()
                smoothedMoveAngle = null
            }
            return emptyList()
        }

        val t = target.center()
        val relative = t - p
        val distance = relative.length()
        val blocked = blocked(p, t, observation.walls)
        val hittable = !blocked || profile.ignoreWallsForAttacks
        lastTargetSeenNanos = observation.timestampNanos

        // IMPORTANT: track enemy motion relative to the player, not absolute screen motion.
        // This removes our own movement/camera translation from lead estimation.
        val velocity = tracker.update(relative, observation.timestampNanos)
        val actions = mutableListOf<BotAction>()

        AbilityPolicy.superAction(
            observation.superReady,
            !blocked,
            distance,
            observation.timestampNanos,
            lastSuper,
            config,
        )?.let {
            actions += it
            lastSuper = observation.timestampNanos
        }

        if (hittable && config.aimedAttacks && distance <= profile.attackRange * 1.03f) {
            val interval = max(
                config.attackMinIntervalSeconds,
                when (profile.rangeClass) {
                    CombatRangeClass.CLOSE -> .22f
                    CombatRangeClass.MID -> .28f
                    CombatRangeClass.LONG -> .32f
                    CombatRangeClass.ULTRA_LONG -> .36f
                },
            )
            val cooldown = (interval * 1_000_000_000L).toLong()
            if (observation.timestampNanos - lastAttack >= cooldown) {
                val angle = stableAimAngle(relative, velocity, profile, config)
                actions += AttackVector(
                    angle,
                    config.aimSwipeRadius.coerceIn(215f, 250f),
                    (config.aimSwipeDurationSeconds * 1000f).roundToLong().coerceIn(55L, 110L),
                )
                lastAttack = observation.timestampNanos
            }
        }

        if (config.alwaysMove) {
            val desired = movementAngle(p, t, distance, profile, observation, config)
            val angle = smoothAngle(bestClearAngle(p, desired, observation.walls))
            rememberMove(angle, observation.timestampNanos)
            actions += MoveVector(angle, 150f, 320L)
        }
        return actions
    }

    private fun selectTarget(player: Vector2, enemies: List<EntityBox>, now: Long): EntityBox? {
        if (enemies.isEmpty()) return null
        val oldRelative = lockedTargetRelative
        if (oldRelative != null && lastTargetSeenNanos > 0L) {
            val dt = ((now - lastTargetSeenNanos).coerceAtLeast(0L) / 1_000_000_000f).coerceAtMost(.5f)
            val associationRadius = (75f + 650f * dt).coerceIn(115f, 220f)
            val candidate = enemies.minByOrNull { (it.center() - player).distanceTo(oldRelative) }
            if (candidate != null) {
                val candidateRelative = candidate.center() - player
                if (candidateRelative.distanceTo(oldRelative) <= associationRadius) {
                    lockedTargetRelative = candidateRelative
                    return candidate
                }
            }
            // Identity changed. Do not carry old velocity into the new opponent.
            tracker.reset()
        }

        val fresh = enemies.minByOrNull { player.distanceTo(it.center()) } ?: return null
        lockedTargetRelative = fresh.center() - player
        tracker.reset()
        return fresh
    }

    private fun stableAimAngle(
        relativeTarget: Vector2,
        relativeVelocity: Vector2,
        profile: BrawlerCombatProfile,
        config: BotConfig,
    ): Float {
        val direct = relativeTarget.angleDegrees()
        if (!config.smartAimEnabled || !config.leadShots) return direct
        if (tracker.confidence() < 0.58f || relativeVelocity.length() < 32f) return direct

        val speed = profile.projectileSpeedPxPerSecond.coerceAtLeast(450f)
        val rawFlight = relativeTarget.length() / speed + profile.fireDelaySeconds.coerceAtLeast(0f)
        val maxFlight = when (profile.rangeClass) {
            CombatRangeClass.CLOSE -> .10f
            CombatRangeClass.MID -> .17f
            CombatRangeClass.LONG -> .24f
            CombatRangeClass.ULTRA_LONG -> .29f
        }
        val strength = when (profile.rangeClass) {
            CombatRangeClass.CLOSE -> .18f
            CombatRangeClass.MID -> .32f
            CombatRangeClass.LONG -> .42f
            CombatRangeClass.ULTRA_LONG -> .48f
        }
        val maxLeadPixels = when (profile.rangeClass) {
            CombatRangeClass.CLOSE -> 20f
            CombatRangeClass.MID -> 44f
            CombatRangeClass.LONG -> 72f
            CombatRangeClass.ULTRA_LONG -> 92f
        }
        val maxCorrectionDegrees = when (profile.rangeClass) {
            CombatRangeClass.CLOSE -> 3f
            CombatRangeClass.MID -> 5.5f
            CombatRangeClass.LONG -> 8f
            CombatRangeClass.ULTRA_LONG -> 10f
        }

        var offset = relativeVelocity * (rawFlight.coerceIn(0f, maxFlight) * strength)
        val leadLength = offset.length()
        if (leadLength > maxLeadPixels) offset = offset * (maxLeadPixels / leadLength)
        val predicted = relativeTarget + offset
        val predictedAngle = predicted.angleDegrees()
        val delta = shortestAngleDelta(direct, predictedAngle)
        return normalizeAngle(direct + delta.coerceIn(-maxCorrectionDegrees, maxCorrectionDegrees))
    }

    private fun movementAngle(
        player: Vector2,
        target: Vector2,
        distance: Float,
        profile: BrawlerCombatProfile,
        observation: BotObservation,
        config: BotConfig,
    ): Float {
        val now = observation.timestampNanos
        if (strafeSide == 0f) {
            // Do not always initialize to the same side. That created a persistent directional bias.
            strafeSide = if (((now / 10_000_000L) and 1L) == 0L) 1f else -1f
            strafeSwitchAtNanos = now + 1_350_000_000L
        }
        if (now >= strafeSwitchAtNanos) {
            strafeSide = -strafeSide
            strafeSwitchAtNanos = now + 1_350_000_000L
        }

        val toward = normalized(target - player)
        val tangent = Vector2(-toward.y * strafeSide, toward.x * strafeSide)
        val tolerance = when (profile.rangeClass) {
            CombatRangeClass.CLOSE -> 24f
            CombatRangeClass.MID -> 34f
            CombatRangeClass.LONG -> 42f
            CombatRangeClass.ULTRA_LONG -> 48f
        }
        val radial = when {
            distance > profile.preferredRange + tolerance -> toward
            distance < profile.preferredRange - tolerance -> toward * -1f
            else -> Vector2(0f, 0f)
        }
        val tangentWeight = if (config.combatLosDodgeEnabled) {
            when (profile.rangeClass) {
                CombatRangeClass.CLOSE -> .30f
                CombatRangeClass.MID -> .56f
                CombatRangeClass.LONG -> .68f
                CombatRangeClass.ULTRA_LONG -> .74f
            }
        } else .10f

        var force = radial * (if (radial.length() > .01f) 1f else .18f) + tangent * tangentWeight
        for (enemy in observation.enemies) {
            val ep = enemy.center()
            if (ep.distanceTo(target) < 8f) continue
            val d = player.distanceTo(ep)
            val radius = max(150f, profile.preferredRange * .72f)
            if (d < radius && d > 1f) {
                force += normalized(player - ep) * ((radius - d) / radius * .9f)
            }
        }
        if (force.length() < .05f) force = tangent
        return force.angleDegrees()
    }

    private fun rememberMove(angle: Float, now: Long) {
        lastStableMoveAngle = normalizeAngle(angle)
        lastStableMoveAtNanos = now
    }

    private fun clearTracking() {
        tracker.reset()
        lockedTargetRelative = null
        lastTargetSeenNanos = 0L
        lastStableMoveAngle = null
        lastStableMoveAtNanos = 0L
        smoothedMoveAngle = null
        strafeSide = 0f
        strafeSwitchAtNanos = 0L
    }

    private fun smoothAngle(target: Float): Float {
        val prev = smoothedMoveAngle ?: target.also { smoothedMoveAngle = it }
        val delta = shortestAngleDelta(prev, target).coerceIn(-18f, 18f)
        val next = normalizeAngle(prev + delta * .70f)
        smoothedMoveAngle = next
        return next
    }

    private fun shortestAngleDelta(from: Float, to: Float): Float = ((to - from + 540f) % 360f) - 180f
    private fun normalizeAngle(angle: Float): Float = ((angle % 360f) + 360f) % 360f
    private fun normalized(v: Vector2): Vector2 {
        val l = v.length()
        return if (l < 1e-4f) Vector2(0f, 0f) else v * (1f / l)
    }

    private fun bestClearAngle(player: Vector2, desired: Float, walls: List<EntityBox>): Float {
        if (walls.isEmpty()) return desired
        fun clear(a: Float): Boolean {
            val r = Math.toRadians(a.toDouble())
            val end = Vector2(player.x + cos(r).toFloat() * 135f, player.y + sin(r).toFloat() * 135f)
            return walls.none { segmentIntersectsBox(player, end, it) }
        }
        if (clear(desired)) return desired
        for (offset in listOf(18f, -18f, 36f, -36f, 54f, -54f, 72f, -72f, 90f, -90f)) {
            val candidate = normalizeAngle(desired + offset)
            if (clear(candidate)) return candidate
        }
        return normalizeAngle(desired + 180f)
    }

    private fun blocked(a: Vector2, b: Vector2, walls: List<EntityBox>) = walls.any { segmentIntersectsBox(a, b, it) }

    private fun segmentIntersectsBox(a: Vector2, b: Vector2, r: EntityBox): Boolean {
        var t0 = 0f
        var t1 = 1f
        val dx = b.x - a.x
        val dy = b.y - a.y
        fun clip(p: Float, q: Float): Boolean {
            if (abs(p) < 1e-6f) return q >= 0f
            val v = q / p
            if (p < 0) {
                if (v > t1) return false
                if (v > t0) t0 = v
            } else {
                if (v < t0) return false
                if (v < t1) t1 = v
            }
            return true
        }
        return clip(-dx, a.x - r.left) && clip(dx, r.right - a.x) &&
            clip(-dy, a.y - r.top) && clip(dy, r.bottom - a.y)
    }
}
''')

write('input/src/main/kotlin/dev/pylarl/input/GestureDispatchQueue.kt', r'''package dev.pylarl.input

import android.os.SystemClock
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

/**
 * Keeps movement as one logical held pointer. New inference frames only update
 * the destination of the next continuation; they do not lift/re-press the
 * joystick. Controls are multiplexed into the movement continuation.
 */
internal object GestureDispatchQueue {
    private const val MOVE_SEGMENT_MS = 280L
    private const val MOVE_HOLD_GRACE_MS = 1_650L

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
                        latestMove = plan.copy(durationMs = MOVE_SEGMENT_MS)
                        lastMoveAt = SystemClock.uptimeMillis()
                    } else {
                        // Keep controls bounded; stale attacks are worse than dropping an old one.
                        if (controls.size >= 3) controls.removeFirst()
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
                        heldMove = it.copy(durationMs = MOVE_SEGMENT_MS)
                        latestMove = null
                    }

                    val keepMoving = heldMove != null &&
                        SystemClock.uptimeMillis() - lastMoveAt <= MOVE_HOLD_GRACE_MS
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
                        move.copy(durationMs = MOVE_SEGMENT_MS),
                        control,
                    )
                    if (result.isFailure) {
                        service.finishContinuousMove()
                        heldMove = null
                    }
                } else {
                    // Only release movement after the grace period or an explicit cancel.
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
''')

# Permanent focused regressions. They are also injected by the standalone RED/GREEN workflow.
write('bot-core/src/test/kotlin/dev/pylarl/botcore/decision/CombatStabilityRegressionTest.kt', r'''package dev.pylarl.botcore.decision

import dev.pylarl.botcore.action.MoveVector
import dev.pylarl.botcore.config.BotConfig
import dev.pylarl.botcore.vision.BotObservation
import dev.pylarl.botcore.vision.EntityBox
import dev.pylarl.botcore.vision.Vector2
import org.junit.Assert.assertTrue
import org.junit.Test

class CombatStabilityRegressionTest {
    private val player = EntityBox(0f, 0f, 100f, 100f)

    @Test fun detection_dropout_does_not_force_right_movement() {
        val observation = BotObservation(
            1_000_000_000L, player, emptyList(), emptyList(), emptyList(), emptyList(),
            null, false, false, false, "shelly"
        )
        val actions = GameplayDecisionEngine().decide(observation, BotConfig(alwaysMove = true))
        val moves = actions.filterIsInstance<MoveVector>()
        assertTrue("no target must not inject a hard-coded 0-degree/right move", moves.none { kotlin.math.abs(it.angleDegrees) < 0.01f })
    }

    @Test fun target_switch_like_jump_does_not_create_extreme_velocity() {
        val tracker = EnemyTracker()
        tracker.update(Vector2(300f, 100f), 1_000_000_000L)
        tracker.update(Vector2(300f, 130f), 1_100_000_000L)
        val velocity = tracker.update(Vector2(125f, 285f), 1_200_000_000L)
        assertTrue("association jump must reset predictive velocity: $velocity", velocity.length() < 500f)
    }
}
''')

print('combat/input v3 patch applied')
