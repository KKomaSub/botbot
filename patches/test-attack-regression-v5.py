from pathlib import Path
p=Path('project/bot-core/src/test/kotlin/dev/pylarl/botcore/decision/AttackRegressionV5Test.kt')
p.parent.mkdir(parents=True,exist_ok=True)
p.write_text(r'''package dev.pylarl.botcore.decision

import dev.pylarl.botcore.action.AttackVector
import dev.pylarl.botcore.action.MoveVector
import dev.pylarl.botcore.config.BotConfig
import dev.pylarl.botcore.vision.BotObservation
import dev.pylarl.botcore.vision.EntityBox
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.cos

class AttackRegressionV5Test {
    @Test fun shellyFiresInsideNominalWeaponRange() {
        val player = EntityBox(0f, 0f, 100f, 100f, 1f)
        val enemy = EntityBox(450f, 0f, 550f, 100f, 1f)
        val observation = BotObservation(
            1_000_000_000L, player, listOf(enemy), emptyList(), emptyList(), emptyList(),
            null, false, false, false, "shelly",
        )
        val actions = GameplayDecisionEngine().decide(
            observation,
            BotConfig(selectedBrawler = "shelly", attackMinIntervalSeconds = .01f),
        )
        assertTrue(
            "an enemy inside Shelly's nominal weapon range must produce an AttackVector: $actions",
            actions.any { it is AttackVector },
        )
    }

    @Test fun noVisibleEnemyStillProducesExplorationMovement() {
        val player = EntityBox(500f, 450f, 600f, 600f, 1f)
        val observation = BotObservation(
            2_000_000_000L, player, emptyList(), emptyList(), emptyList(), emptyList(),
            null, false, false, false, "shelly",
        )
        val actions = GameplayDecisionEngine().decide(observation, BotConfig(alwaysMove = true))
        assertTrue(
            "when no enemy is visible the bot should explore instead of freezing: $actions",
            actions.any { it is MoveVector },
        )
    }

    @Test fun nearbyRightWallRepelsMovementInsteadOfHuggingIt() {
        val player = EntityBox(500f, 450f, 600f, 600f, 1f)
        val enemy = EntityBox(500f, 50f, 600f, 200f, 1f)
        val wall = EntityBox(600f, 300f, 900f, 850f, 1f)
        val observation = BotObservation(
            1_000_000_000L, player, listOf(enemy), emptyList(), listOf(wall), emptyList(),
            null, false, false, false, "shelly",
        )
        val move = GameplayDecisionEngine().decide(
            observation,
            BotConfig(selectedBrawler = "shelly", aimedAttacks = false),
        ).filterIsInstance<MoveVector>().first()
        val xComponent = cos(Math.toRadians(move.angleDegrees.toDouble()))
        assertTrue(
            "a close wall on the right should repel movement left/neutral, angle=${move.angleDegrees}",
            xComponent <= 0.0,
        )
    }
}
''', encoding='utf-8')
print('attack/exploration/wall regression v5 tests installed')
