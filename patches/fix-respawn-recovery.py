from pathlib import Path

p = Path('project/runtime/src/main/kotlin/dev/pylarl/runtime/BotRuntimeCoordinator.kt')
s = p.read_text()

# Add respawn tracking fields.
anchor = '''    private var metricsStartedNanos = 0L\n'''
replacement = '''    private var metricsStartedNanos = 0L\n    private var lastPlayerSeenNanos = 0L\n    private var playerWasMissing = false\n    private val respawnGraceNanos = 8_000_000_000L\n'''
if anchor not in s:
    raise SystemExit('metrics field anchor not found')
s = s.replace(anchor, replacement, 1)

# Reset tracking on start.
anchor = '''        metricsStartedNanos = 0L\n        resumeRequested = false\n'''
if anchor in s:
    s = s.replace(anchor, '''        metricsStartedNanos = 0L\n        lastPlayerSeenNanos = 0L\n        playerWasMissing = false\n        resumeRequested = false\n''', 1)
else:
    anchor = '''        metricsStartedNanos = System.nanoTime()\n'''
    if anchor not in s:
        raise SystemExit('start metrics anchor not found')
    s = s.replace(anchor, '''        metricsStartedNanos = System.nanoTime()\n        lastPlayerSeenNanos = 0L\n        playerWasMissing = false\n''', 1)

old = '''                val signal = if (result.detections.any { it.className.equals("player", true) }) {\n                    StateSignal(GameState.MATCH, 1f)\n                } else {\n                    stateRecognizer.recognize(frame)\n                }\n                gameContext = StateTransitionReducer.reduce(gameContext, signal)\n'''
new = '''                val hasPlayer = result.detections.any { it.className.equals("player", true) }\n                val signal = if (hasPlayer) {\n                    val respawned = playerWasMissing || gameContext.state != GameState.MATCH\n                    lastPlayerSeenNanos = frame.timestampNanos\n                    playerWasMissing = false\n                    if (respawned) {\n                        // A fresh player detection is authoritative: this is a live match again.\n                        // Reset sticky result/lobby flags from the death/respawn gap.\n                        gameContext = RuntimeGameContext(state = GameState.MATCH)\n                        runCatching { inputController.releaseAll() }\n                        pointersReleased = false\n                    }\n                    StateSignal(GameState.MATCH, 1f)\n                } else {\n                    playerWasMissing = true\n                    val withinRespawnGrace = gameContext.state == GameState.MATCH &&\n                        lastPlayerSeenNanos > 0L &&\n                        frame.timestampNanos >= lastPlayerSeenNanos &&\n                        frame.timestampNanos - lastPlayerSeenNanos < respawnGraceNanos\n                    if (withinRespawnGrace) StateSignal(GameState.MATCH, 1f) else stateRecognizer.recognize(frame)\n                }\n                gameContext = StateTransitionReducer.reduce(gameContext, signal)\n'''
if old not in s:
    raise SystemExit('processFrames player signal block not found')
s = s.replace(old, new, 1)

p.write_text(s)
print('respawn recovery patch applied')
