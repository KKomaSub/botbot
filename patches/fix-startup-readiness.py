from pathlib import Path

path = Path("project/runtime/src/main/kotlin/dev/pylarl/runtime/BotRuntimeCoordinator.kt")
text = path.read_text()

old_start = '''        if (isReadyForRunning()) {
            pointersReleased = false
            mutableSnapshot.value = mutableSnapshot.value.copy(phase = RuntimePhase.RUNNING)
        } else {
            mutableSnapshot.value = mutableSnapshot.value.copy(phase = RuntimePhase.PAUSED)
            releasePointersOnce()
        }
'''
new_start = '''        if (isReadyForRunning()) {
            pointersReleased = false
            mutableSnapshot.value = mutableSnapshot.value.copy(phase = RuntimePhase.RUNNING)
        } else {
            // During startup the Pyla UI / MediaProjection consent screen is normally foreground.
            // This is not a user pause. Keep capture alive and wait for Brawl Stars to become ready.
            mutableSnapshot.value = mutableSnapshot.value.copy(phase = RuntimePhase.CAPTURING)
        }
'''

old_readiness = '''        if (mutableSnapshot.value.phase == RuntimePhase.RUNNING && !isReadyForRunning()) {
            enterPausedForReadiness()
        } else if (mutableSnapshot.value.phase == RuntimePhase.PAUSED && resumeRequested) {
            resumeIfReady()
        }
'''
new_readiness = '''        if (mutableSnapshot.value.phase == RuntimePhase.RUNNING && !isReadyForRunning()) {
            enterPausedForReadiness()
        } else if (mutableSnapshot.value.phase == RuntimePhase.CAPTURING && isReadyForRunning()) {
            pointersReleased = false
            mutableSnapshot.value = mutableSnapshot.value.copy(phase = RuntimePhase.RUNNING, lastError = null)
        } else if (mutableSnapshot.value.phase == RuntimePhase.PAUSED && resumeRequested) {
            resumeIfReady()
        }
'''

if old_start not in text:
    raise SystemExit("startup state block not found")
if old_readiness not in text:
    raise SystemExit("readiness state block not found")

text = text.replace(old_start, new_start, 1)
text = text.replace(old_readiness, new_readiness, 1)
path.write_text(text)
print("startup readiness patch applied")
