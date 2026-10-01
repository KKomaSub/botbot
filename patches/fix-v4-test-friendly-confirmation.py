from pathlib import Path
p=Path('project/bot-core/src/test/kotlin/dev/pylarl/botcore/decision/WorldCombatV4Test.kt')
s=p.read_text(encoding='utf-8')
old=''' @Test fun aimingUsesSameGroundAnchorForPlayerAndEnemy(){val p=EntityBox(100f,100f,200f,250f,1f);val e=EntityBox(300f,0f,400f,300f,1f);val a=GameplayDecisionEngine().decide(obs(1_000_000_000L,p,listOf(e),"shelly"),BotConfig(selectedBrawler="shelly",attackMinIntervalSeconds=.01f)).filterIsInstance<AttackVector>().first();assertTrue("angle=${a.angleDegrees}",a.angleDegrees in 5f..25f)}'''
new=''' @Test fun aimingUsesSameGroundAnchorForPlayerAndEnemy(){val p=EntityBox(100f,100f,200f,250f,1f);val e=EntityBox(300f,0f,400f,300f,1f);val engine=GameplayDecisionEngine();val cfg=BotConfig(selectedBrawler="shelly",attackMinIntervalSeconds=.01f);engine.decide(obs(1_000_000_000L,p,listOf(e),"shelly"),cfg);val a=engine.decide(obs(1_100_000_000L,p,listOf(e),"shelly"),cfg).filterIsInstance<AttackVector>().first();assertTrue("angle=${a.angleDegrees}",a.angleDegrees in 5f..25f)}'''
if old not in s: raise SystemExit('WorldCombatV4Test anchor not found')
p.write_text(s.replace(old,new,1),encoding='utf-8')
print('WorldCombatV4 ground-anchor test updated for two-frame hostile confirmation')
