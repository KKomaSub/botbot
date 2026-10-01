from pathlib import Path

ROOT = Path('project')

def write(rel, text):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding='utf-8')

write('bot-core/src/main/kotlin/dev/pylarl/botcore/combat/BrawlerCombatProfile.kt', r'''package dev.pylarl.botcore.combat

enum class CombatRangeClass { CLOSE, MID, LONG, ULTRA_LONG }

data class BrawlerCombatProfile(
    val key: String,
    val displayName: String,
    val safeRange: Float,
    val attackRange: Float,
    val projectileSpeedPxPerSecond: Float,
    val fireDelaySeconds: Float,
    val ignoreWallsForAttacks: Boolean = false,
) {
    val rangeClass: CombatRangeClass = when {
        attackRange <= 260f -> CombatRangeClass.CLOSE
        attackRange <= 450f -> CombatRangeClass.MID
        attackRange <= 575f -> CombatRangeClass.LONG
        else -> CombatRangeClass.ULTRA_LONG
    }
    val preferredRange: Float = when (rangeClass) {
        CombatRangeClass.CLOSE -> attackRange * 0.68f
        CombatRangeClass.MID -> if (safeRange > 0f) safeRange + (attackRange - safeRange) * 0.45f else attackRange * 0.68f
        CombatRangeClass.LONG -> if (safeRange > 0f) safeRange + (attackRange - safeRange) * 0.58f else attackRange * 0.75f
        CombatRangeClass.ULTRA_LONG -> if (safeRange > 0f) safeRange + (attackRange - safeRange) * 0.66f else attackRange * 0.80f
    }
}

object BrawlerCombatProfiles {
    private fun p(key: String, name: String, safe: Float, attack: Float, ignoreWalls: Boolean = false): BrawlerCombatProfile {
        val klass = when {
            attack <= 260f -> CombatRangeClass.CLOSE
            attack <= 450f -> CombatRangeClass.MID
            attack <= 575f -> CombatRangeClass.LONG
            else -> CombatRangeClass.ULTRA_LONG
        }
        val speed = when (klass) {
            CombatRangeClass.CLOSE -> 2300f
            CombatRangeClass.MID -> 1550f
            CombatRangeClass.LONG -> 1280f
            CombatRangeClass.ULTRA_LONG -> 1120f
        }
        val delay = when (klass) {
            CombatRangeClass.CLOSE -> 0.045f
            CombatRangeClass.MID -> 0.075f
            CombatRangeClass.LONG -> 0.095f
            CombatRangeClass.ULTRA_LONG -> 0.115f
        }
        return BrawlerCombatProfile(key, name, safe, attack, speed, delay, ignoreWalls)
    }

    private val profiles = listOf(
        p("shelly", "Shelly", 301f, 490f), p("colt", "Colt", 324f, 546f),
        p("bull", "Bull", 210f, 341f), p("brock", "Brock", 354f, 576f),
        p("rico", "Rico", 380f, 618f), p("spike", "Spike", 301f, 490f),
        p("barley", "Barley", 288f, 469f, true), p("jessie", "Jessie", 354f, 576f),
        p("nita", "Nita", 236f, 384f), p("dynamike", "Dynamike", 288f, 469f, true),
        p("elprimo", "El Primo", 0f, 192f), p("mortis", "Mortis", 0f, 170f),
        p("crow", "Crow", 341f, 554f), p("poco", "Poco", 275f, 448f),
        p("bo", "Bo", 341f, 554f), p("piper", "Piper", 393f, 640f),
        p("pam", "Pam", 354f, 576f), p("tara", "Tara", 315f, 512f),
        p("darryl", "Darryl", 236f, 384f), p("penny", "Penny", 315f, 512f),
        p("frank", "Frank", 236f, 384f), p("tick", "Tick", 341f, 554f, true),
        p("leon", "Leon", 380f, 618f), p("rosa", "Rosa", 0f, 234f),
        p("carl", "Carl", 328f, 533f), p("bibi", "Bibi", 0f, 234f),
        p("8bit", "8-Bit", 393f, 640f), p("sandy", "Sandy", 236f, 384f),
        p("bea", "Bea", 393f, 640f), p("emz", "Emz", 262f, 426f),
        p("mrp", "Mr. P", 275f, 448f), p("max", "Max", 328f, 533f),
        p("jacky", "Jacky", 0f, 213f, true), p("gale", "Gale", 328f, 533f),
        p("nani", "Nani", 341f, 554f), p("sprout", "Sprout", 196f, 320f, true),
        p("surge", "Surge", 200f, 426f), p("colette", "Colette", 341f, 554f),
        p("amber", "Amber", 328f, 533f), p("lou", "Lou", 367f, 597f),
        p("byron", "Byron", 393f, 640f), p("edgar", "Edgar", 0f, 128f),
        p("stu", "Stu", 301f, 490f), p("belle", "Belle", 393f, 640f),
        p("squeak", "Squeak", 301f, 490f), p("grom", "Grom", 301f, 490f, true),
        p("buzz", "Buzz", 0f, 170f), p("griff", "Griff", 328f, 533f)
    )
    private val byKey = profiles.associateBy { it.key }
    val all: List<BrawlerCombatProfile> get() = profiles
    val names: List<String> get() = profiles.map { it.key }
    fun forName(name: String?): BrawlerCombatProfile = byKey[name?.lowercase()] ?: byKey.getValue("shelly")
}
''')

write('bot-core/src/main/kotlin/dev/pylarl/botcore/decision/EnemyTracker.kt', r'''package dev.pylarl.botcore.decision

import dev.pylarl.botcore.vision.Vector2
import java.util.ArrayDeque
import kotlin.math.abs
import kotlin.math.sqrt

class EnemyTracker {
    private data class Sample(val position: Vector2, val timestampNanos: Long)
    private val samples = ArrayDeque<Sample>(6)
    private var velocity = Vector2(0f, 0f)
    private var lastPosition: Vector2? = null

    fun update(target: Vector2?, timestampNanos: Long): Vector2 {
        if (target == null) { reset(); return velocity }
        val previous = lastPosition
        if (previous != null && previous.distanceTo(target) > 340f) reset()
        lastPosition = target
        samples.addLast(Sample(target, timestampNanos))
        while (samples.size > 5) samples.removeFirst()
        while (samples.size >= 2 && timestampNanos - samples.first().timestampNanos > 650_000_000L) samples.removeFirst()
        if (samples.size < 2) return velocity
        val first = samples.first(); val last = samples.last()
        val dt = (last.timestampNanos - first.timestampNanos) / 1_000_000_000f
        if (dt <= 0.008f || dt > 0.8f) return velocity
        var raw = (last.position - first.position) * (1f / dt)
        val speed = raw.length()
        if (speed > 1750f) raw = raw * (1750f / speed)
        val alpha = if (samples.size >= 4) 0.38f else 0.55f
        velocity = velocity * (1f - alpha) + raw * alpha
        return velocity
    }
    fun reset() { samples.clear(); velocity = Vector2(0f, 0f); lastPosition = null }
    fun currentVelocity(): Vector2 = velocity

    companion object {
        data class Intercept(val point: Vector2, val flightSeconds: Float)
        fun predictIntercept(shooter: Vector2, target: Vector2, targetVelocity: Vector2, projectileSpeedPxPerSecond: Float, fireDelaySeconds: Float = 0f, leadScale: Float = 1f): Intercept {
            if (projectileSpeedPxPerSecond <= 1f) return Intercept(target, 0f)
            val r = target - shooter; val v = targetVelocity; val s = projectileSpeedPxPerSecond
            val a = v.x * v.x + v.y * v.y - s * s
            val b = 2f * (r.x * v.x + r.y * v.y)
            val c = r.x * r.x + r.y * r.y
            val t = when {
                abs(a) < 1e-5f -> if (abs(b) > 1e-5f) (-c / b).takeIf { it > 0f } ?: 0f else 0f
                else -> { val d = b * b - 4f * a * c; if (d < 0f) 0f else { val q = sqrt(d); listOf((-b-q)/(2f*a), (-b+q)/(2f*a)).filter { it > 0f }.minOrNull() ?: 0f } }
            }.coerceIn(0f, 1.25f)
            val total = (fireDelaySeconds + t * leadScale).coerceIn(0f, 1.35f)
            return Intercept(target + v * total, t)
        }
        fun leadShotAngle(shooter: Vector2, target: Vector2, targetVelocity: Vector2, projectileSpeedPxPerSecond: Float, fireDelaySeconds: Float = 0f, leadScale: Float = 1f): Float = (predictIntercept(shooter, target, targetVelocity, projectileSpeedPxPerSecond, fireDelaySeconds, leadScale).point - shooter).angleDegrees()
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
    private val tracker = EnemyTracker(); private val wallEscape = WallEscape()
    private var lastAttack = Long.MIN_VALUE / 2; private var lastSuper = 0L
    private var strafeSide = 1f; private var strafeSwitchAtNanos = 0L; private var smoothedMoveAngle: Float? = null

    fun decide(observation: BotObservation, config: BotConfig): List<BotAction> {
        FogAvoidance.action(observation.fogEscapeVector)?.let { return listOf(it) }
        wallEscape.update(observation, config)?.let { return listOf(it) }
        val player = observation.player ?: run { tracker.reset(); return emptyList() }
        val p = player.footPosition(); val profile = BrawlerCombatProfiles.forName(observation.currentBrawler ?: config.selectedBrawler)
        val target = observation.enemies.minByOrNull { p.distanceTo(it.center()) }
        if (target == null) { tracker.update(null, observation.timestampNanos); smoothedMoveAngle = null; return listOfNotNull(TeamFollow.action(player, observation.teammates, config) ?: if (config.alwaysMove) MoveVector(0f,35f,260L) else null) }
        val t = target.center(); val distance = p.distanceTo(t); val blocked = blocked(p,t,observation.walls); val hittable = !blocked || profile.ignoreWallsForAttacks
        val velocity = tracker.update(t, observation.timestampNanos); val actions = mutableListOf<BotAction>()
        AbilityPolicy.superAction(observation.superReady,!blocked,distance,observation.timestampNanos,lastSuper,config)?.let { actions += it; lastSuper = observation.timestampNanos }
        if (hittable && config.aimedAttacks && distance <= profile.attackRange * 1.03f) {
            val interval = max(config.attackMinIntervalSeconds, when(profile.rangeClass){ CombatRangeClass.CLOSE->.22f; CombatRangeClass.MID->.28f; CombatRangeClass.LONG->.32f; CombatRangeClass.ULTRA_LONG->.36f })
            val cooldown = (interval * 1_000_000_000L).toLong()
            if (observation.timestampNanos - lastAttack >= cooldown) {
                val ratio=(distance/profile.attackRange.coerceAtLeast(1f)).coerceIn(0f,1.2f)
                val leadScale=if(profile.rangeClass==CombatRangeClass.CLOSE) .12f else when { ratio<.35f->.28f; ratio<.62f->.62f; ratio<.86f->.95f; else->1.12f }
                val angle=if(config.smartAimEnabled&&config.leadShots) EnemyTracker.leadShotAngle(p,t,velocity,profile.projectileSpeedPxPerSecond,profile.fireDelaySeconds,leadScale) else (t-p).angleDegrees()
                actions += AttackVector(angle,config.aimSwipeRadius.coerceIn(205f,250f),(config.aimSwipeDurationSeconds*1000f).roundToLong().coerceAtLeast(45L)); lastAttack=observation.timestampNanos
            }
        }
        if(config.alwaysMove){ val desired=movementAngle(p,t,distance,profile,observation,config); actions += MoveVector(smoothAngle(bestClearAngle(p,desired,observation.walls)),150f,220L) }
        return actions
    }

    private fun movementAngle(player:Vector2,target:Vector2,distance:Float,profile:BrawlerCombatProfile,observation:BotObservation,config:BotConfig):Float {
        val now=observation.timestampNanos; if(strafeSwitchAtNanos==0L) strafeSwitchAtNanos=now+1_150_000_000L
        if(now>=strafeSwitchAtNanos){ strafeSide=-strafeSide; strafeSwitchAtNanos=now+1_150_000_000L }
        val toward=normalized(target-player); val tangent=Vector2(-toward.y*strafeSide,toward.x*strafeSide)
        val tolerance=when(profile.rangeClass){ CombatRangeClass.CLOSE->24f; CombatRangeClass.MID->34f; CombatRangeClass.LONG->42f; CombatRangeClass.ULTRA_LONG->48f }
        val radial=when { distance>profile.preferredRange+tolerance->toward; distance<profile.preferredRange-tolerance->toward*-1f; else->Vector2(0f,0f) }
        val tw=if(config.combatLosDodgeEnabled) when(profile.rangeClass){ CombatRangeClass.CLOSE->.34f; CombatRangeClass.MID->.62f; CombatRangeClass.LONG->.76f; CombatRangeClass.ULTRA_LONG->.82f } else .12f
        var force=radial*(if(radial.length()>.01f)1f else .16f)+tangent*tw
        for(enemy in observation.enemies){ val ep=enemy.center(); if(ep.distanceTo(target)<8f) continue; val d=player.distanceTo(ep); val radius=max(150f,profile.preferredRange*.72f); if(d<radius&&d>1f) force += normalized(player-ep)*((radius-d)/radius*.9f) }
        if(force.length()<.05f) force=tangent; return force.angleDegrees()
    }
    private fun smoothAngle(target:Float):Float { val prev=smoothedMoveAngle ?: target.also{smoothedMoveAngle=it}; val delta=(((target-prev+540f)%360f)-180f).coerceIn(-22f,22f); val next=((prev+delta*.72f)%360f+360f)%360f; smoothedMoveAngle=next; return next }
    private fun normalized(v:Vector2):Vector2 { val l=v.length(); return if(l<1e-4f) Vector2(0f,0f) else v*(1f/l) }
    private fun bestClearAngle(player:Vector2,desired:Float,walls:List<EntityBox>):Float { if(walls.isEmpty()) return desired; fun clear(a:Float):Boolean { val r=Math.toRadians(a.toDouble()); val end=Vector2(player.x+cos(r).toFloat()*135f,player.y+sin(r).toFloat()*135f); return walls.none{segmentIntersectsBox(player,end,it)} }; if(clear(desired)) return desired; for(o in listOf(18f,-18f,36f,-36f,54f,-54f,72f,-72f,90f,-90f)){ val c=((desired+o)%360f+360f)%360f; if(clear(c)) return c }; return (desired+180f)%360f }
    private fun blocked(a:Vector2,b:Vector2,walls:List<EntityBox>)=walls.any{segmentIntersectsBox(a,b,it)}
    private fun segmentIntersectsBox(a:Vector2,b:Vector2,r:EntityBox):Boolean { var t0=0f; var t1=1f; val dx=b.x-a.x; val dy=b.y-a.y; fun clip(p:Float,q:Float):Boolean{ if(abs(p)<1e-6f)return q>=0f; val v=q/p; if(p<0){if(v>t1)return false;if(v>t0)t0=v}else{if(v<t0)return false;if(v<t1)t1=v};return true }; return clip(-dx,a.x-r.left)&&clip(dx,r.right-a.x)&&clip(-dy,a.y-r.top)&&clip(dy,r.bottom-a.y) }
}
''')

write('bot-core/src/main/kotlin/dev/pylarl/botcore/config/BotConfig.kt', r'''package dev.pylarl.botcore.config

data class BotConfig(
    val performancePreset: PerformancePreset = PerformancePreset.BALANCED, val targetInferenceFps: Int = 15, val preferNnapi: Boolean = true, val debugOverlay: Boolean = false,
    val selectedBrawler: String = "shelly", val minimumMovementDelaySeconds: Float = 0.1f, val attackCooldownSeconds: Float = 0.16f, val gadgetCooldownSeconds: Float = 8.0f, val superCooldownSeconds: Float = 1.0f,
    val wallStuckEnabled: Boolean = true, val wallStuckShiftThreshold: Float = 3.0f, val wallStuckTimeoutSeconds: Float = 3.0f, val wallStuckMinWalls: Int = 3, val fogCheckEveryNFrames: Int = 1,
    val entityDetectionConfidence: Float = 0.55f, val wallDetectionConfidence: Float = 0.75f, val teammateFollowMinDistance: Float = 180f, val teammateFollowMaxDistance: Float = 520f, val teammateCombatRegroupDistance: Float = 650f,
    val leadShots: Boolean = true, val aimedAttacks: Boolean = true, val smartAimEnabled: Boolean = true, val projectileSpeedPxPerSecond: Float = 900f, val aimSwipeRadius: Float = 250f, val aimSwipeDurationSeconds: Float = 0.09f,
    val attackMinIntervalSeconds: Float = 0.35f, val combatLosDodgeEnabled: Boolean = true, val combatDodgeBlend: Float = 1.0f, val strafeWhileAttacking: Boolean = true, val alwaysMove: Boolean = true,
)
''')

write('runtime/src/main/kotlin/dev/pylarl/runtime/RuntimeSnapshot.kt', r'''package dev.pylarl.runtime
import dev.pylarl.botcore.model.InputStatus
import dev.pylarl.state.GameState
import dev.pylarl.vision.InferenceProvider
data class RuntimeSnapshot(val phase:RuntimePhase=RuntimePhase.IDLE,val inputStatus:InputStatus=InputStatus.UNAVAILABLE,val foregroundPackage:String?=null,val gameState:GameState=GameState.UNKNOWN,val provider:InferenceProvider?=null,val captureFps:Float=0f,val inferenceIps:Float=0f,val playerDetected:Boolean=false,val enemyCount:Int=0,val wallCount:Int=0,val lastError:RuntimeError?=null)
''')

p=ROOT/'runtime/src/main/kotlin/dev/pylarl/runtime/BotRuntimeCoordinator.kt'; s=p.read_text()
old='        fun VisionDetection.box() = EntityBox(left, top, right, bottom, confidence)'
new='''        val geometry = geometryProvider()\n        val sx = PlatformContract.CANONICAL_WIDTH.toFloat() / geometry.widthPx.coerceAtLeast(1)\n        val sy = PlatformContract.CANONICAL_HEIGHT.toFloat() / geometry.heightPx.coerceAtLeast(1)\n        fun VisionDetection.box() = EntityBox(left * sx, top * sy, right * sx, bottom * sy, confidence)'''
if old not in s: raise SystemExit('runtime box conversion anchor not found')
s=s.replace(old,new,1).replace('            currentBrawler = null,','            currentBrawler = config?.selectedBrawler,',1)
needle='                    gameState = gameContext.state,\n'
if needle in s and 'playerDetected =' not in s: s=s.replace(needle,needle+'                    playerDetected = result.detections.any { it.className.equals("player", true) },\n                    enemyCount = result.detections.count { it.className.equals("enemy", true) },\n                    wallCount = result.detections.count { it.className.equals("wall", true) },\n',1)
p.write_text(s)

write('app/src/main/java/dev/pylarl/android/settings/UserSettings.kt', '''package dev.pylarl.android.settings\nimport dev.pylarl.botcore.config.PerformancePreset\ndata class UserSettings(val performancePreset:PerformancePreset=PerformancePreset.BALANCED,val targetInferenceFps:Int=15,val preferNnapi:Boolean=true,val debugOverlay:Boolean=false,val selectedBrawler:String="shelly")\n''')
write('app/src/main/java/dev/pylarl/android/settings/SettingsStore.kt', '''package dev.pylarl.android.settings\nimport dev.pylarl.botcore.config.PerformancePreset\nimport kotlinx.coroutines.flow.Flow\ninterface SettingsStore { val settings:Flow<UserSettings>; suspend fun setPerformancePreset(value:PerformancePreset); suspend fun setTargetInferenceFps(value:Int); suspend fun setPreferNnapi(value:Boolean); suspend fun setDebugOverlay(value:Boolean); suspend fun setSelectedBrawler(value:String) }\n''')
write('app/src/main/java/dev/pylarl/android/settings/SettingsRepository.kt', r'''package dev.pylarl.android.settings
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.*
import dev.pylarl.botcore.combat.BrawlerCombatProfiles
import dev.pylarl.botcore.config.PerformancePreset
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
class SettingsRepository(private val dataStore:DataStore<Preferences>):SettingsStore {
 private object Keys { val preset=stringPreferencesKey("performance_preset"); val fps=intPreferencesKey("target_inference_fps"); val nnapi=booleanPreferencesKey("prefer_nnapi"); val debug=booleanPreferencesKey("debug_overlay"); val brawler=stringPreferencesKey("selected_brawler") }
 override val settings:Flow<UserSettings> = dataStore.data.map { p -> val b=p[Keys.brawler]?.lowercase().orEmpty(); UserSettings(runCatching{PerformancePreset.valueOf(p[Keys.preset]?:PerformancePreset.BALANCED.name)}.getOrDefault(PerformancePreset.BALANCED),(p[Keys.fps]?:15).coerceIn(1,60),p[Keys.nnapi]?:true,p[Keys.debug]?:false,if(b in BrawlerCombatProfiles.names)b else "shelly") }
 override suspend fun setPerformancePreset(value:PerformancePreset){dataStore.edit{it[Keys.preset]=value.name}}; override suspend fun setTargetInferenceFps(value:Int){dataStore.edit{it[Keys.fps]=value.coerceIn(1,60)}}; override suspend fun setPreferNnapi(value:Boolean){dataStore.edit{it[Keys.nnapi]=value}}; override suspend fun setDebugOverlay(value:Boolean){dataStore.edit{it[Keys.debug]=value}}; override suspend fun setSelectedBrawler(value:String){dataStore.edit{it[Keys.brawler]=value.lowercase()}}
}
''')
write('app/src/main/java/dev/pylarl/android/settings/SettingsSnapshotMapper.kt', '''package dev.pylarl.android.settings\nimport dev.pylarl.botcore.config.BotConfig\nobject SettingsSnapshotMapper { fun toBotConfig(s:UserSettings)=BotConfig(performancePreset=s.performancePreset,targetInferenceFps=s.targetInferenceFps.coerceIn(1,60),preferNnapi=s.preferNnapi,debugOverlay=s.debugOverlay,selectedBrawler=s.selectedBrawler) }\n''')
p=ROOT/'app/src/main/java/dev/pylarl/android/ui/MainViewModel.kt'; s=p.read_text(); a='    fun setDebugOverlay(value: Boolean) = workerScope.launch { settingsStore.setDebugOverlay(value) }\n';
if a not in s: raise SystemExit('viewmodel anchor not found')
p.write_text(s.replace(a,a+'    fun setSelectedBrawler(value: String) = workerScope.launch { settingsStore.setSelectedBrawler(value) }\n',1))

write('app/src/main/java/dev/pylarl/android/ui/PylaApp.kt', r'''package dev.pylarl.android.ui
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
private val Bg=Color(0xFF0B0C12); private val Chrome=Color(0xFF11131B); private val Surface=Color(0xFF161925); private val Surface2=Color(0xFF1C2030); private val Accent=Color(0xFFFF9F0A); private val Text=Color(0xFFF5F6FA); private val Muted=Color(0xFFAAB0C0)
enum class AppPage(val label:String){OVERVIEW("Overview"),FARM_PLAN("Farm Plan"),CONTROL("Control"),SETTINGS("Settings"),DEBUG("Debug")}
@Composable fun PylaApp(viewModel:MainViewModel,onEnableInput:()->Unit){ val state by viewModel.uiState.collectAsState(); var page by remember{mutableStateOf(AppPage.OVERVIEW)}; MaterialTheme(colorScheme=darkColorScheme(primary=Accent,secondary=Accent,background=Bg,surface=Surface,surfaceVariant=Surface2,onPrimary=Color.Black,onBackground=Text,onSurface=Text,onSurfaceVariant=Muted,error=Color(0xFFFF5D52))){ Column(Modifier.fillMaxSize().background(Bg)){ Row(Modifier.fillMaxWidth().background(Chrome).padding(18.dp),horizontalArrangement=Arrangement.SpaceBetween){ Column{Text("PYLA-RL",color=Accent,style=MaterialTheme.typography.titleLarge);Text("Android Native",color=Muted)}; Surface(color=if(state.runtime.phase.name=="RUNNING")Color(0xFF15301D)else Surface2,shape=MaterialTheme.shapes.small){Text(state.runtime.phase.name,Modifier.padding(12.dp,7.dp),color=if(state.runtime.phase.name=="RUNNING")Color(0xFF30D158)else Text)} }; ScrollableTabRow(selectedTabIndex=AppPage.entries.indexOf(page),containerColor=Chrome,contentColor=Text,edgePadding=10.dp){AppPage.entries.forEach{p->Tab(selected=page==p,onClick={page=p},text={Text(p.label)})}}; Box(Modifier.fillMaxSize()){when(page){AppPage.OVERVIEW->OverviewHubScreen(state,viewModel::requestStart,viewModel::stop,onEnableInput);AppPage.FARM_PLAN->FarmPlanHubScreen(state,viewModel::setSelectedBrawler);AppPage.CONTROL->ControlHubScreen(state,viewModel::pause,viewModel::resume,viewModel::stop);AppPage.SETTINGS->HubSettingsScreen(state,viewModel::setPerformancePreset,viewModel::setTargetInferenceFps,viewModel::setPreferNnapi,viewModel::setDebugOverlay);AppPage.DEBUG->DebugHubScreen(state)}} } } }
''')

write('app/src/main/java/dev/pylarl/android/ui/PylaHubScreens.kt', r'''package dev.pylarl.android.ui
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import dev.pylarl.botcore.combat.BrawlerCombatProfiles
import dev.pylarl.botcore.config.PerformancePreset
private val A=Color(0xFFFF9F0A); private val P=Color(0xFF161925); private val P2=Color(0xFF1C2030); private val M=Color(0xFFAAB0C0); private val OK=Color(0xFF30D158); private val BAD=Color(0xFFFF5D52)
@Composable private fun Page(c:@Composable ColumnScope.()->Unit){Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),verticalArrangement=Arrangement.spacedBy(12.dp),content=c)}
@Composable private fun Card(title:String,sub:String?=null,c:@Composable ColumnScope.()->Unit){Surface(color=P,shape=RoundedCornerShape(14.dp)){Column(Modifier.fillMaxWidth().padding(16.dp),verticalArrangement=Arrangement.spacedBy(10.dp)){Text(title,style=MaterialTheme.typography.titleMedium,fontWeight=FontWeight.SemiBold);if(sub!=null)Text(sub,color=M,style=MaterialTheme.typography.bodySmall);c()}}}
@Composable private fun Status(label:String,value:String,ok:Boolean){Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){Text(label,color=M);Text(value,color=if(ok)OK else BAD,fontWeight=FontWeight.SemiBold)}}
@Composable private fun Metric(l:String,v:String){Column(horizontalAlignment=Alignment.CenterHorizontally){Text(v,color=A,style=MaterialTheme.typography.titleLarge);Text(l,color=M,style=MaterialTheme.typography.labelSmall)}}
@Composable fun OverviewHubScreen(s:MainUiState,start:()->Unit,stop:()->Unit,input:()->Unit)=Page{Text("Overview",style=MaterialTheme.typography.headlineSmall);Text("Pre-flight checks and launch controls",color=M);Card("Pre-flight checks"){Status("Accessibility input",s.inputStatus.name,s.inputStatus.name=="READY");Status("Screen capture",if(s.runtime.phase.name=="IDLE")"Not started" else "Active",s.runtime.phase.name!="ERROR");Status("ONNX provider",s.runtime.provider?.name?:"Pending",s.runtime.provider!=null||s.runtime.phase.name=="IDLE");OutlinedButton(onClick=input,modifier=Modifier.fillMaxWidth()){Text("Open Accessibility Settings")}};Card("Performance"){Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){Metric("Capture FPS","%.1f".format(s.runtime.captureFps));Metric("Inference IPS","%.1f".format(s.runtime.inferenceIps));Metric("Target",s.settings.targetInferenceFps.toString())};Text("Profile ${s.settings.performancePreset.name}",color=M)};Card("Combat profile"){val p=BrawlerCombatProfiles.forName(s.settings.selectedBrawler);Text(p.displayName,color=A,style=MaterialTheme.typography.titleLarge);Text("${p.rangeClass.name.replace('_',' ')} • safe ${p.safeRange.toInt()} • attack ${p.attackRange.toInt()}",color=M)};Button(onClick=start,enabled=s.canStart,modifier=Modifier.fillMaxWidth().height(54.dp)){Text(if(s.projectionPending)"WAITING FOR CAPTURE…" else "START PYLA")};if(s.canStop)OutlinedButton(onClick=stop,modifier=Modifier.fillMaxWidth()){Text("STOP SESSION")}}
@Composable fun FarmPlanHubScreen(s:MainUiState,select:(String)->Unit)=Page{val queue=remember{mutableStateListOf(s.settings.selectedBrawler)};var target by remember{mutableFloatStateOf(1000f)};Text("Farm Plan",style=MaterialTheme.typography.headlineSmall);Text("Queue builder and active combat profile",color=M);Card("Active brawler"){val p=BrawlerCombatProfiles.forName(s.settings.selectedBrawler);Text(p.displayName,color=A,style=MaterialTheme.typography.titleLarge);Text("Target trophies: ${target.toInt()}",color=M);Slider(value=target,onValueChange={target=it},valueRange=100f..1500f,steps=13)};Card("Queue"){queue.forEachIndexed{i,k->val p=BrawlerCombatProfiles.forName(k);Row(Modifier.fillMaxWidth().background(if(k==s.settings.selectedBrawler)P2 else Color.Transparent,RoundedCornerShape(8.dp)).clickable{select(k)}.padding(10.dp),horizontalArrangement=Arrangement.SpaceBetween){Text("${i+1}. ${p.displayName}");Text(p.rangeClass.name.replace('_',' '),color=M)}};Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){OutlinedButton(onClick={if(queue.size<8){BrawlerCombatProfiles.names.firstOrNull{it !in queue}?.let(queue::add)}}){Text("Add")};OutlinedButton(onClick={if(queue.size>1)queue.removeAt(queue.lastIndex)}){Text("Remove")};Button(onClick={target=1000f}){Text("Push All 1K")}}};Card("Brawlers"){BrawlerCombatProfiles.all.chunked(3).forEach{row->Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(6.dp)){row.forEach{p->OutlinedButton(onClick={select(p.key);if(p.key !in queue&&queue.size<8)queue.add(p.key)},modifier=Modifier.weight(1f),colors=ButtonDefaults.outlinedButtonColors(contentColor=if(p.key==s.settings.selectedBrawler)A else MaterialTheme.colorScheme.onSurface)){Text(p.displayName,maxLines=1)}};repeat(3-row.size){Spacer(Modifier.weight(1f))}}}}}
@Composable fun ControlHubScreen(s:MainUiState,pause:()->Unit,resume:()->Unit,stop:()->Unit)=Page{Text("Control",style=MaterialTheme.typography.headlineSmall);Card("Session"){Status("Runtime",s.runtime.phase.name,s.runtime.phase.name=="RUNNING");Status("Game state",s.runtime.gameState.name,s.runtime.gameState.name=="MATCH");Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){Metric("FPS","%.1f".format(s.runtime.captureFps));Metric("IPS","%.1f".format(s.runtime.inferenceIps));Metric("Enemies",s.runtime.enemyCount.toString())}};Card("Controls"){Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(8.dp)){Button(onClick=pause,enabled=s.canPause,modifier=Modifier.weight(1f)){Text("PAUSE")};Button(onClick=resume,enabled=s.canResume,modifier=Modifier.weight(1f)){Text("RESUME")};OutlinedButton(onClick=stop,enabled=s.canStop,modifier=Modifier.weight(1f)){Text("STOP")}}};Card("Live combat"){val p=BrawlerCombatProfiles.forName(s.settings.selectedBrawler);Text("${p.displayName} · ${p.rangeClass.name.replace('_',' ')}",color=A);Text("Predictive lead aim: ON",color=OK);Text("Range gate: ${p.attackRange.toInt()} px canonical",color=M);Text("Continuous joystick: ON",color=OK)}}
@Composable fun HubSettingsScreen(s:MainUiState,preset:(PerformancePreset)->Unit,fps:(Int)->Unit,nnapi:(Boolean)->Unit,debug:(Boolean)->Unit)=Page{Text("Settings",style=MaterialTheme.typography.headlineSmall);Card("Performance profile"){Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(6.dp)){PerformancePreset.entries.forEach{p->OutlinedButton(onClick={preset(p)},modifier=Modifier.weight(1f),colors=ButtonDefaults.outlinedButtonColors(contentColor=if(s.settings.performancePreset==p)A else MaterialTheme.colorScheme.onSurface)){Text(p.name)}}};Text("Target inference FPS ${s.settings.targetInferenceFps}",color=M);Slider(value=s.settings.targetInferenceFps.toFloat(),onValueChange={fps(it.toInt())},valueRange=5f..30f)};Card("Runtime"){Toggle("Prefer NNAPI",s.settings.preferNnapi,nnapi);Toggle("Debug overlay / logging",s.settings.debugOverlay,debug);Text("Theme: Pyla Dark · orange accent",color=M)};Card("Combat"){Text("Smart aim + target movement prediction",color=OK);Text("Brawler range profiles + spacing",color=OK);Text("Locked strafe + turn smoothing",color=OK)}}
@Composable private fun Toggle(l:String,v:Boolean,c:(Boolean)->Unit){Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically){Text(l,Modifier.weight(1f));Switch(checked=v,onCheckedChange=c)}}
@Composable fun DebugHubScreen(s:MainUiState)=Page{Text("Debug",style=MaterialTheme.typography.headlineSmall);Card("Vision"){Status("Player detected",if(s.runtime.playerDetected)"YES" else "NO",s.runtime.playerDetected);Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){Text("Enemies",color=M);Text(s.runtime.enemyCount.toString())};Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){Text("Walls",color=M);Text(s.runtime.wallCount.toString())};Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){Text("Game state",color=M);Text(s.runtime.gameState.name)}};Card("Pipeline"){Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){Text("Capture",color=M);Text("%.1f FPS".format(s.runtime.captureFps))};Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){Text("Inference",color=M);Text("%.1f IPS".format(s.runtime.inferenceIps))};Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){Text("Provider",color=M);Text(s.runtime.provider?.name?:"-")}}}
''')

p=ROOT/'input/src/main/java/dev/pylarl/input/PylaAccessibilityService.kt'; s=p.read_text()
if 'executeContinuousMoveWithControl' not in s:
 ins=r'''
    private var continuedMoveStroke: GestureDescription.StrokeDescription? = null
    private var continuedMoveEndX: Float = 0f
    private var continuedMoveEndY: Float = 0f
    internal suspend fun executeContinuousMoveWithControl(move: GesturePlan.Stroke, control: GesturePlan.Stroke? = null): Result<Unit> = suspendCancellableCoroutine { cont ->
        try { val path=Path(); val previous=continuedMoveStroke; val nextMove=if(previous==null){path.moveTo(move.start.x,move.start.y);path.lineTo(move.end.x,move.end.y);GestureDescription.StrokeDescription(path,0L,move.durationMs,true)}else{path.moveTo(continuedMoveEndX,continuedMoveEndY);path.lineTo(move.end.x,move.end.y);previous.continueStroke(path,0L,move.durationMs,true)}; val builder=GestureDescription.Builder().addStroke(nextMove); control?.let{val cp=Path().apply{moveTo(it.start.x,it.start.y);lineTo(it.end.x,it.end.y)};builder.addStroke(GestureDescription.StrokeDescription(cp,0L,it.durationMs.coerceAtMost(move.durationMs),false))}; val accepted=dispatchGesture(builder.build(),object:GestureResultCallback(){override fun onCompleted(g:GestureDescription?){continuedMoveStroke=nextMove;continuedMoveEndX=move.end.x;continuedMoveEndY=move.end.y;if(cont.isActive)cont.resume(Result.success(Unit))};override fun onCancelled(g:GestureDescription?){continuedMoveStroke=null;if(cont.isActive)cont.resume(Result.failure(IllegalStateException("continuous move cancelled"))) }},null); if(!accepted&&cont.isActive){continuedMoveStroke=null;cont.resume(Result.failure(IllegalStateException("continuous move rejected")))}}catch(t:Throwable){continuedMoveStroke=null;if(cont.isActive)cont.resume(Result.failure(t))}
    }
    internal suspend fun finishContinuousMove():Result<Unit>{val previous=continuedMoveStroke?:return Result.success(Unit);return suspendCancellableCoroutine{cont->try{val path=Path().apply{moveTo(continuedMoveEndX,continuedMoveEndY);lineTo(continuedMoveEndX,continuedMoveEndY)};val finalStroke=previous.continueStroke(path,0L,24L,false);val accepted=dispatchGesture(GestureDescription.Builder().addStroke(finalStroke).build(),object:GestureResultCallback(){override fun onCompleted(g:GestureDescription?){continuedMoveStroke=null;if(cont.isActive)cont.resume(Result.success(Unit))};override fun onCancelled(g:GestureDescription?){continuedMoveStroke=null;if(cont.isActive)cont.resume(Result.success(Unit))}},null);if(!accepted&&cont.isActive){continuedMoveStroke=null;cont.resume(Result.success(Unit))}}catch(_:Throwable){continuedMoveStroke=null;if(cont.isActive)cont.resume(Result.success(Unit))}}}
'''
 idx=s.rfind('\n}');
 if idx<0: raise SystemExit('service end not found')
 s=s[:idx]+ins+s[idx:];p.write_text(s)

write('input/src/main/kotlin/dev/pylarl/input/GestureDispatchQueue.kt', r'''package dev.pylarl.input
import android.os.SystemClock
import kotlinx.coroutines.*
internal object GestureDispatchQueue {
 private val scope=CoroutineScope(SupervisorJob()+Dispatchers.Main.immediate);private val lock=Any();private val controls=ArrayDeque<GesturePlan.Stroke>();private var latestMove:GesturePlan.Stroke?=null;private var lastMoveAt=0L;private var draining=false;private var generation=0L
 fun offer(plan:GesturePlan):Result<Unit>{synchronized(lock){when(plan){GesturePlan.Cancel->return Result.failure(IllegalArgumentException("cancel must use cancel()"));is GesturePlan.Stroke->if(plan.pointerId==1){latestMove=plan.copy(durationMs=140L);lastMoveAt=SystemClock.uptimeMillis()}else controls.addLast(plan)};if(!draining){draining=true;val g=generation;scope.launch{drain(g)}}};return Result.success(Unit)}
 suspend fun cancel(service:PylaAccessibilityService):Result<Unit>{synchronized(lock){generation++;latestMove=null;controls.clear();lastMoveAt=0;draining=false};service.finishContinuousMove();return service.execute(GesturePlan.Cancel)}
 private suspend fun drain(g:Long){var held:GesturePlan.Stroke?=null;while(true){val packet=synchronized(lock){if(generation!=g)return;latestMove?.let{held=it;latestMove=null};val keep=held!=null&&SystemClock.uptimeMillis()-lastMoveAt<=520L;val control=if(controls.isNotEmpty())controls.removeFirst()else null;if(!keep&&control==null){draining=false;null}else Pair(if(keep)held else null,control)}}?:break;val service=PylaAccessibilityService.instance?:break;val move=packet.first;val control=packet.second;if(move!=null){if(service.executeContinuousMoveWithControl(move.copy(durationMs=140L),control).isFailure){service.finishContinuousMove();held=null}}else{service.finishContinuousMove();control?.let{service.execute(it)}}};PylaAccessibilityService.instance?.finishContinuousMove();synchronized(lock){if(generation==g)draining=false}}
}
''')

write('bot-core/src/test/kotlin/dev/pylarl/botcore/decision/CombatV2Test.kt', r'''package dev.pylarl.botcore.decision
import dev.pylarl.botcore.action.*
import dev.pylarl.botcore.config.BotConfig
import dev.pylarl.botcore.vision.*
import org.junit.Assert.*
import org.junit.Test
import kotlin.math.abs
class CombatV2Test { private val player=EntityBox(0f,0f,100f,100f);private fun obs(t:Long,e:EntityBox,b:String)=BotObservation(t,player,listOf(e),emptyList(),emptyList(),emptyList(),null,false,false,false,b)
@Test fun close_range_brawler_does_not_fire_from_far_away(){val a=GameplayDecisionEngine().decide(obs(1_000_000_000L,EntityBox(350f,0f,430f,80f),"edgar"),BotConfig(selectedBrawler="edgar"));assertFalse(a.any{it is AttackVector});assertTrue(a.any{it is MoveVector})}
@Test fun lateral_enemy_motion_is_led_ahead(){val e=GameplayDecisionEngine();e.decide(obs(1_000_000_000L,EntityBox(280f,0f,340f,60f),"shelly"),BotConfig(selectedBrawler="shelly",aimedAttacks=false));val a=e.decide(obs(1_120_000_000L,EntityBox(280f,30f,340f,90f),"shelly"),BotConfig(selectedBrawler="shelly",attackMinIntervalSeconds=.01f)).filterIsInstance<AttackVector>().first();assertTrue(a.angleDegrees>2f)}
@Test fun strafe_direction_does_not_flip_every_frame(){val e=GameplayDecisionEngine();val a=e.decide(obs(1_000_000_000L,EntityBox(330f,0f,390f,60f),"shelly"),BotConfig()).filterIsInstance<MoveVector>().first().angleDegrees;val b=e.decide(obs(1_070_000_000L,EntityBox(330f,2f,390f,62f),"shelly"),BotConfig()).filterIsInstance<MoveVector>().first().angleDegrees;val d=abs(((b-a+540f)%360f)-180f);assertTrue(d<28f)} }
''')
print('original UI + combat v2 + predictive aim + continuous movement patch applied')
