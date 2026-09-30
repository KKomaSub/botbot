from pathlib import Path

p = Path("project/runtime/src/main/kotlin/dev/pylarl/runtime/BotRuntimeCoordinator.kt")
s = p.read_text()
old = '''    private fun isReadyForRunning(): Boolean {
        val geometry = geometryProvider()
        return inputController.status.value == InputStatus.READY &&
            inputController.foregroundPackage.value == PlatformContract.BRAWL_STARS_PACKAGE &&
            geometry.isLandscape
    }
'''
new = '''    private fun isReadyForRunning(): Boolean {
        val geometry = geometryProvider()
        // Accessibility foreground-package reporting is not reliable enough to gate runtime state.
        // Keep running while the input service is available and the device is landscape.
        return inputController.status.value == InputStatus.READY && geometry.isLandscape
    }
'''
if old not in s:
    raise SystemExit("foreground-gated readiness block not found")
p.write_text(s.replace(old, new, 1))
print("foreground package removed from runtime readiness gate")
