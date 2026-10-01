from pathlib import Path
p=Path('project/bot-core/src/test/kotlin/dev/pylarl/botcore/decision/AttackRegressionV5Test.kt')
p.parent.mkdir(parents=True,exist_ok=True)
p.write_text(r'''package dev.pylarl.botcore.decision

import dev.pylarl.botcore.action.AttackVector
import dev.pylarl.botcore.config.BotConfig
import dev.pylarl.botcore.vision.BotObservation
import dev.pylarl.botcore.vision.EntityBox
import org.junit.Assert.assertTrue
import org.junit.Test

class AttackRegressionV5Test {
    @Test fun shellyFiresInsideNominalWeaponRange() {
        val player = EntityBox(0f, 0f, 100f, 100f, 1f)
        // Ground anchor distance = 450 canonical px. Shelly's nominal attack range is 490 px.
        val enemy = EntityBox(450f, 0f, 550f, 100f, 1f)
        val observation = BotObservation(
            1_000_000_000L,
            player,
            listOf(enemy),
            emptyList(),
            emptyList(),
            emptyList(),
            null,
            false,
            false,
            false,
            "shelly",
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
}
''', encoding='utf-8')
print('attack regression v5 test installed')
