from pathlib import Path

p = Path('project/runtime/src/main/kotlin/dev/pylarl/runtime/BotRuntimeCoordinator.kt')
s = p.read_text()

# Respawn recovery must be able to replace the stateful gameplay engine, just like a fresh app process.
old_ctor = '    private val gameplayDecisionEngine: GameplayDecisionEngine = GameplayDecisionEngine(),\n'
new_ctor = '    private var gameplayDecisionEngine: GameplayDecisionEngine = GameplayDecisionEngine(),\n'
if old_ctor in s:
    s = s.replace(old_ctor, new_ctor, 1)
elif new_ctor not in s:
    raise SystemExit('gameplayDecisionEngine constructor anchor not found')

# Add respawn tracking fields.
anchor = '''    private var metricsStartedNanos = 0L\n'''
replacement = '''    private var metricsStartedNanos = 0L\n    private var lastPlayerSeenNanos = 0L\n    private var playerWasMissing = false\n    private val respawnGraceNanos = 8_000_000_000L\n'''
if 'private var lastPlayerSeenNanos' not in s:
    if anchor not in s:
        raise SystemExit('metrics field anchor not found')
    s = s.replace(anchor, replacement, 1)

# Reset tracking and stateful decision engine on a new Start too.
anchor = '''        lastPlayerSeenNanos = 0L\n        playerWasMissing = false\n'''
if anchor in s:
    s = s.replace(anchor, anchor + '        gameplayDecisionEngine = GameplayDecisionEngine()\n', 1)
else:
    anchor = '''        metricsStartedNanos = 0L\n        resumeRequested = false\n'''
    if anchor in s:
        s = s.replace(anchor, '''        metricsStartedNanos = 0L\n        lastPlayerSeenNanos = 0L\n        playerWasMissing = false\n        gameplayDecisionEngine = GameplayDecisionEngine()\n        resumeRequested = false\n''', 1)
    else:
        anchor = '''        metricsStartedNanos = System.nanoTime()\n'''
        if anchor not in s:
            raise SystemExit('start metrics anchor not found')
        s = s.replace(anchor, '''        metricsStartedNanos = System.nanoTime()\n        lastPlayerSeenNanos = 0L\n        playerWasMissing = false\n        gameplayDecisionEngine = GameplayDecisionEngine()\n''', 1)

old = '''                val signal = if (result.detections.any { it.className.equals("player", true) }) {\n                    StateSignal(GameState.MATCH, 1f)\n                } else {\n                    stateRecognizer.recognize(frame)\n                }\n                gameContext = StateTransitionReducer.reduce(gameContext, signal)\n'''
new = '''                val hasPlayer = result.detections.any { it.className.equals("player", true) }\n                val signal = if (hasPlayer) {\n                    val respawned = playerWasMissing || gameContext.state != GameState.MATCH\n                    lastPlayerSeenNanos = frame.timestampNanos\n                    playerWasMissing = false\n                    if (respawned) {\n                        // A fresh player detection is authoritative: this is a live match again.\n                        // Make respawn equivalent to a fresh process for all sticky gameplay state.\n                        gameContext = RuntimeGameContext(state = GameState.MATCH)\n                        gameplayDecisionEngine = GameplayDecisionEngine()\n                        runCatching { inputController.releaseAll() }\n                        pointersReleased = false\n                    }\n                    StateSignal(GameState.MATCH, 1f)\n                } else {\n                    playerWasMissing = true\n                    val withinRespawnGrace = gameContext.state == GameState.MATCH &&\n                        lastPlayerSeenNanos > 0L &&\n                        frame.timestampNanos >= lastPlayerSeenNanos &&\n                        frame.timestampNanos - lastPlayerSeenNanos < respawnGraceNanos\n                    // Death/respawn animation is not a match result. Keep MATCH alive briefly so\n                    // result templates cannot poison the state machine while the player is absent.\n                    if (withinRespawnGrace) StateSignal(GameState.MATCH, 1f) else stateRecognizer.recognize(frame)\n                }\n                gameContext = StateTransitionReducer.reduce(gameContext, signal)\n'''
if old in s:
    s = s.replace(old, new, 1)
elif 'val hasPlayer = result.detections.any' not in s:
    raise SystemExit('processFrames player signal block not found')

p.write_text(s)
print('respawn recovery patch applied')
