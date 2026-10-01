from pathlib import Path
p=Path('project/bot-core/src/test/kotlin/dev/pylarl/botcore/decision/NavigationTeamV6Test.kt')
p.parent.mkdir(parents=True,exist_ok=True)
p.write_text(r'''package dev.pylarl.botcore.decision

import dev.pylarl.botcore.action.AttackVector
import dev.pylarl.botcore.action.MoveVector
import dev.pylarl.botcore.config.BotConfig
import dev.pylarl.botcore.vision.BotObservation
import dev.pylarl.botcore.vision.EntityBox
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.*

class NavigationTeamV6Test {
    private fun obs(
        ts: Long,
        player: EntityBox = EntityBox(500f, 450f, 600f, 600f, 1f),
        enemies: List<EntityBox> = emptyList(),
        teammates: List<EntityBox> = emptyList(),
        walls: List<EntityBox> = emptyList(),
    ) = BotObservation(ts, player, enemies, teammates, walls, emptyList(), null, false, false, false, "shelly")

    @Test fun oneFrameEnemyFlipOfRecentTeammateMustNotFire() {
        val engine = GameplayDecisionEngine()
        val actor = EntityBox(790f, 450f, 890f, 600f, .93f)
        engine.decide(obs(1_000_000_000L, teammates = listOf(actor)), BotConfig(alwaysMove = false))
        val actions = engine.decide(
            obs(1_100_000_000L, enemies = listOf(actor)),
            BotConfig(alwaysMove = false, attackMinIntervalSeconds = .01f),
        )
        assertFalse("a recent teammate classification flip must never create a shot: $actions", actions.any { it is AttackVector })
    }

    @Test fun tenSecondsOfNoTargetRoamMustMakeNetProgressInsteadOfOrbitingSpawn() {
        val engine = GameplayDecisionEngine()
        val config = BotConfig(alwaysMove = true, aimedAttacks = false)
        var x = 0.0
        var y = 0.0
        var path = 0.0
        var ts = 5_400_000_000L
        repeat(41) {
            val move = engine.decide(obs(ts), config).filterIsInstance<MoveVector>().firstOrNull()
            assertTrue("no-target roaming must keep moving", move != null)
            val r = Math.toRadians(move!!.angleDegrees.toDouble())
            x += cos(r); y += sin(r); path += 1.0
            ts += 250_000_000L
        }
        val net = hypot(x, y)
        assertTrue("roaming should traverse the map, not orbit spawn: net=$net path=$path", net / path >= .60)
    }

    @Test fun wallFartherAheadMustBeDetectedBeforeBotCommitsStraightIntoIt() {
        val engine = GameplayDecisionEngine()
        val player = EntityBox(500f, 450f, 600f, 600f, 1f)
        // Player ground point is (550,600). A long vertical wall begins ~230 px to the right.
        // v5 only probes about 55 px, so it commits right when the seeded roam heading is 0 degrees.
        val wall = EntityBox(780f, 250f, 940f, 900f, 1f)
        val move = engine.decide(
            obs(5_400_000_000L, player = player, walls = listOf(wall)),
            BotConfig(alwaysMove = true, aimedAttacks = false),
        ).filterIsInstance<MoveVector>().first()
        val angle = ((move.angleDegrees % 360f) + 360f) % 360f
        val deviationFromRight = min(angle, 360f - angle)
        assertTrue("multi-probe wall avoidance must turn before reaching a wall, angle=$angle", deviationFromRight >= 22.5f)
    }
}
''', encoding='utf-8')
print('navigation/team v6 RED tests installed')
