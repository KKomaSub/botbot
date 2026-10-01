from pathlib import Path

p=Path('project/bot-core/src/main/kotlin/dev/pylarl/botcore/decision/EnemyTracker.kt')
s=p.read_text()
old='''        val dt=dn/1_000_000_000f
        val delta=relativeWorld-old
        mark=relativeWorld;markTs=now
        if(delta.length()<WorldCombatModel.MOTION_STRIDE_WORLD){velocity=velocity*.55f;if(velocity.length()<35f)velocity=Vector2(0f,0f);stable++;return velocity}
        var raw=delta*(1f/dt)+ownVelocityWorld
'''
new='''        val dt=dn/1_000_000_000f
        val delta=relativeWorld-old
        mark=relativeWorld;markTs=now
        // Treat physically implausible one-frame jumps as detector identity swaps.
        // Do not clamp them into a fake velocity, because that poisons lead aim.
        val plausibleTravel = targetMaxSpeedWorld.coerceAtLeast(300f) * 1.35f * dt + WorldCombatModel.BODY_RADIUS_WORLD * 1.5f
        if (delta.length() > plausibleTravel.coerceAtLeast(120f)) {
            velocity=Vector2(0f,0f);stable=0;return velocity
        }
        if(delta.length()<WorldCombatModel.MOTION_STRIDE_WORLD){velocity=velocity*.55f;if(velocity.length()<35f)velocity=Vector2(0f,0f);stable++;return velocity}
        var raw=delta*(1f/dt)+ownVelocityWorld
'''
if old not in s: raise SystemExit('EnemyTracker anchor not found')
p.write_text(s.replace(old,new,1))
print('world tracker jump reset patch applied')
