from pathlib import Path

ROOT = Path('project')

def write(rel: str, text: str) -> None:
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding='utf-8')

write('bot-core/src/main/kotlin/dev/pylarl/botcore/combat/WorldCombatModel.kt', r'''package dev.pylarl.botcore.combat

import dev.pylarl.botcore.vision.Vector2
import kotlin.math.round

/**
 * Independent world-coordinate calibration for screen detections.
 * Pyla decisions run in game-like world units and convert to screen direction only at input time.
 */
object WorldCombatModel {
    const val TILE_WORLD = 300f
    const val WORLD_PER_CANONICAL_PX = 75f / 16f
    const val DEFAULT_MOVE_SPEED_WORLD = 720f
    const val MAX_TRACKED_SPEED_WORLD = DEFAULT_MOVE_SPEED_WORLD * 1.35f
    const val BODY_RADIUS_WORLD = 60f
    const val DEFAULT_PROJECTILE_SPEED_WORLD = 4000f
    const val FLIGHT_CAP_SECONDS = 1.15f
    const val MOTION_WATCH_NANOS = 80_000_000L
    const val MOTION_STRIDE_WORLD = 40f
    const val TARGET_STICKY_WORLD = 260f
    const val MOVE_STEP_WORLD = 260f
    const val DIRECTIONS = 48
    const val DIRECTION_LOCK_NANOS = 130_000_000L
    const val KEEP_BAND = 120f
    const val MOMENTUM_WEIGHT = 100f

    fun pxToWorld(v: Float): Float = v * WORLD_PER_CANONICAL_PX
    fun worldToPx(v: Float): Float = v / WORLD_PER_CANONICAL_PX
    fun vecToWorld(v: Vector2): Vector2 = v * WORLD_PER_CANONICAL_PX
    fun vecToPx(v: Vector2): Vector2 = v * (1f / WORLD_PER_CANONICAL_PX)
    fun roundedWorldRange(canonicalPx: Float): Float = round(pxToWorld(canonicalPx) / 100f) * 100f
}
''')

write('bot-core/src/main/kotlin/dev/pylarl/botcore/combat/BrawlerCombatProfile.kt', r'''package dev.pylarl.botcore.combat

enum class CombatRangeClass { CLOSE, MID, LONG, ULTRA_LONG }
enum class AttackStyle { MELEE, DASH, SHOTGUN, LINEAR, BURST, SNIPER, THROWER, SPRAY, WAVE, BOOMERANG }

data class BrawlerCombatProfile(
    val key: String,
    val displayName: String,
    val safeRange: Float,
    val attackRange: Float,
    val attackStyle: AttackStyle,
    val ignoreWallsForAttacks: Boolean = false,
    val moveSpeedWorld: Float = WorldCombatModel.DEFAULT_MOVE_SPEED_WORLD,
) {
    val safeRangeWorld = WorldCombatModel.roundedWorldRange(safeRange)
    val attackRangeWorld = WorldCombatModel.roundedWorldRange(attackRange)
    val rangeClass = when {
        attackRangeWorld <= 1200f -> CombatRangeClass.CLOSE
        attackRangeWorld <= 2100f -> CombatRangeClass.MID
        attackRangeWorld <= 2700f -> CombatRangeClass.LONG
        else -> CombatRangeClass.ULTRA_LONG
    }
    val preferredRangeWorld = when (attackStyle) {
        AttackStyle.MELEE, AttackStyle.DASH -> attackRangeWorld * .60f
        AttackStyle.SHOTGUN -> attackRangeWorld * .56f
        AttackStyle.SPRAY, AttackStyle.WAVE -> attackRangeWorld * .67f
        AttackStyle.BURST, AttackStyle.LINEAR, AttackStyle.BOOMERANG -> attackRangeWorld * .72f
        AttackStyle.THROWER -> attackRangeWorld * .78f
        AttackStyle.SNIPER -> attackRangeWorld * .82f
    }
    val preferredRange = WorldCombatModel.worldToPx(preferredRangeWorld)
    val projectileSpeedWorld = when (attackStyle) {
        AttackStyle.MELEE, AttackStyle.DASH -> 0f
        AttackStyle.THROWER -> 2600f
        AttackStyle.BOOMERANG -> 3000f
        AttackStyle.SPRAY, AttackStyle.WAVE -> 3500f
        AttackStyle.SNIPER -> 4500f
        else -> WorldCombatModel.DEFAULT_PROJECTILE_SPEED_WORLD
    }
    val projectileRadiusWorld = when (attackStyle) {
        AttackStyle.SHOTGUN, AttackStyle.SPRAY, AttackStyle.WAVE -> 250f
        AttackStyle.THROWER -> 180f
        AttackStyle.SNIPER -> 90f
        AttackStyle.MELEE, AttackStyle.DASH -> 60f
        else -> 130f
    }
    val leadStrength = when (attackStyle) {
        AttackStyle.MELEE, AttackStyle.DASH -> 0f
        AttackStyle.SHOTGUN -> .25f
        AttackStyle.SPRAY, AttackStyle.WAVE -> .48f
        AttackStyle.THROWER -> .58f
        AttackStyle.BURST -> .62f
        AttackStyle.LINEAR, AttackStyle.BOOMERANG -> .65f
        AttackStyle.SNIPER -> .56f
    }
}

object BrawlerCombatProfiles {
    private fun p(key:String,name:String,safe:Float,attack:Float,style:AttackStyle,through:Boolean=false,move:Float=WorldCombatModel.DEFAULT_MOVE_SPEED_WORLD)=
        BrawlerCombatProfile(key,name,safe,attack,style,through,move)

    private val profiles = listOf(
        p("shelly","Shelly",301f,490f,AttackStyle.SHOTGUN), p("colt","Colt",324f,546f,AttackStyle.BURST),
        p("bull","Bull",210f,341f,AttackStyle.SHOTGUN,move=770f), p("brock","Brock",354f,576f,AttackStyle.SNIPER),
        p("rico","Rico",380f,618f,AttackStyle.BURST), p("spike","Spike",301f,490f,AttackStyle.LINEAR),
        p("barley","Barley",288f,469f,AttackStyle.THROWER,true), p("jessie","Jessie",354f,576f,AttackStyle.LINEAR),
        p("nita","Nita",236f,384f,AttackStyle.WAVE), p("dynamike","Dynamike",288f,469f,AttackStyle.THROWER,true),
        p("elprimo","El Primo",0f,192f,AttackStyle.MELEE,move=770f), p("mortis","Mortis",0f,170f,AttackStyle.DASH,move=820f),
        p("crow","Crow",341f,554f,AttackStyle.LINEAR,move=820f), p("poco","Poco",275f,448f,AttackStyle.WAVE),
        p("bo","Bo",341f,554f,AttackStyle.BURST), p("piper","Piper",393f,640f,AttackStyle.SNIPER),
        p("pam","Pam",354f,576f,AttackStyle.SPRAY), p("tara","Tara",315f,512f,AttackStyle.WAVE),
        p("darryl","Darryl",236f,384f,AttackStyle.SHOTGUN,move=770f), p("penny","Penny",315f,512f,AttackStyle.LINEAR),
        p("frank","Frank",236f,384f,AttackStyle.WAVE,move=650f), p("tick","Tick",341f,554f,AttackStyle.THROWER,true),
        p("leon","Leon",380f,618f,AttackStyle.BURST,move=820f), p("rosa","Rosa",0f,234f,AttackStyle.MELEE,move=770f),
        p("carl","Carl",328f,533f,AttackStyle.BOOMERANG), p("bibi","Bibi",0f,234f,AttackStyle.MELEE,move=820f),
        p("8bit","8-Bit",393f,640f,AttackStyle.BURST,move=580f), p("sandy","Sandy",236f,384f,AttackStyle.WAVE),
        p("bea","Bea",393f,640f,AttackStyle.SNIPER), p("emz","Emz",262f,426f,AttackStyle.SPRAY),
        p("mrp","Mr. P",275f,448f,AttackStyle.LINEAR), p("max","Max",328f,533f,AttackStyle.BURST,move=820f),
        p("jacky","Jacky",0f,213f,AttackStyle.MELEE,true), p("gale","Gale",328f,533f,AttackStyle.WAVE),
        p("nani","Nani",341f,554f,AttackStyle.SNIPER), p("sprout","Sprout",196f,320f,AttackStyle.THROWER,true),
        p("surge","Surge",200f,426f,AttackStyle.LINEAR), p("colette","Colette",341f,554f,AttackStyle.LINEAR),
        p("amber","Amber",328f,533f,AttackStyle.SPRAY), p("lou","Lou",367f,597f,AttackStyle.BURST),
        p("byron","Byron",393f,640f,AttackStyle.SNIPER), p("edgar","Edgar",0f,128f,AttackStyle.MELEE,move=820f),
        p("stu","Stu",301f,490f,AttackStyle.BURST,move=770f), p("belle","Belle",393f,640f,AttackStyle.SNIPER),
        p("squeak","Squeak",301f,490f,AttackStyle.THROWER), p("grom","Grom",301f,490f,AttackStyle.THROWER,true),
        p("buzz","Buzz",0f,170f,AttackStyle.MELEE,move=770f), p("griff","Griff",328f,533f,AttackStyle.BURST)
    )
    private val byKey=profiles.associateBy{it.key}
    private val aliases=mapOf("8-bit" to "8bit","el_primo" to "elprimo","el primo" to "elprimo","mr_p" to "mrp","mr. p" to "mrp")
    val all:List<BrawlerCombatProfile> get()=profiles
    val names:List<String> get()=profiles.map{it.key}
    fun forName(name:String?):BrawlerCombatProfile { val raw=name?.trim()?.lowercase().orEmpty(); return byKey[aliases[raw]?:raw]?:byKey.getValue("shelly") }
}
''')

write('bot-core/src/main/kotlin/dev/pylarl/botcore/decision/EnemyTracker.kt', r'''package dev.pylarl.botcore.decision

import dev.pylarl.botcore.combat.WorldCombatModel
import dev.pylarl.botcore.vision.Vector2

class EnemyTracker {
    private var mark:Vector2?=null
    private var markTs=0L
    private var velocity=Vector2(0f,0f)
    private var stable=0

    fun update(relativeWorld:Vector2?,now:Long,ownVelocityWorld:Vector2=Vector2(0f,0f),targetMaxSpeedWorld:Float=WorldCombatModel.DEFAULT_MOVE_SPEED_WORLD):Vector2 {
        if(relativeWorld==null){reset();return velocity}
        val old=mark
        if(old==null||markTs<=0L){mark=relativeWorld;markTs=now;velocity=Vector2(0f,0f);return velocity}
        val dn=now-markTs
        if(dn<=0L)return velocity
        if(dn>650_000_000L){mark=relativeWorld;markTs=now;velocity=Vector2(0f,0f);stable=0;return velocity}
        if(dn<WorldCombatModel.MOTION_WATCH_NANOS)return velocity
        val dt=dn/1_000_000_000f
        val delta=relativeWorld-old
        mark=relativeWorld;markTs=now
        if(delta.length()<WorldCombatModel.MOTION_STRIDE_WORLD){velocity=velocity*.55f;if(velocity.length()<35f)velocity=Vector2(0f,0f);stable++;return velocity}
        var raw=delta*(1f/dt)+ownVelocityWorld
        val cap=targetMaxSpeedWorld.coerceAtLeast(300f)*1.35f
        val speed=raw.length();if(speed>cap)raw=raw*(cap/speed)
        velocity=if(stable==0)raw else velocity*.48f+raw*.52f;stable++
        return velocity
    }
    fun confidence()=(stable/3f).coerceIn(0f,1f)
    fun currentVelocity()=velocity
    fun reset(){mark=null;markTs=0L;velocity=Vector2(0f,0f);stable=0}

    fun predicted(relativeWorld:Vector2,projectileSpeedWorld:Float,strength:Float,targetRadiusWorld:Float,projectileRadiusWorld:Float,maxRangeWorld:Float):Vector2 {
        if(projectileSpeedWorld<=1f||confidence()<.5f||velocity.length()<20f)return relativeWorld
        var point=relativeWorld
        var flight=(relativeWorld.length()/projectileSpeedWorld).coerceIn(0f,WorldCombatModel.FLIGHT_CAP_SECONDS)
        val pocket=targetRadiusWorld+projectileRadiusWorld
        if(velocity.length()*flight<=pocket)return relativeWorld
        repeat(3){flight=(point.length()/projectileSpeedWorld).coerceIn(0f,WorldCombatModel.FLIGHT_CAP_SECONDS);point=relativeWorld+velocity*(flight*strength.coerceIn(0f,1f))}
        val max=maxRangeWorld+targetRadiusWorld;val d=point.length();if(max>0f&&d>max)point=point*(max/d)
        return point
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
    private val tracker=EnemyTracker();private val wallEscape=WallEscape();private var lastAttack=Long.MIN_VALUE/2;private var lastSuper=0L
    private var lockedRelativeWorld:Vector2?=null;private var lastTargetNanos=0L;private var lastMoveDir:Vector2?=null;private var lastMoveAngle:Float?=null;private var lastMoveNanos=0L
    private var moveLockUntil=0L;private var lastMoveIndex=-1;private var strafeSide=1f;private var strafeFlipAt=0L

    fun decide(o:BotObservation,c:BotConfig):List<BotAction>{
        FogAvoidance.action(o.fogEscapeVector)?.let{rememberMove(it.angleDegrees,o.timestampNanos);return listOf(it)}
        wallEscape.update(o,c)?.let{rememberMove(it.angleDegrees,o.timestampNanos);return listOf(it)}
        val player=o.player?:run{clear();return emptyList()};val pg=ground(player);val profile=BrawlerCombatProfiles.forName(o.currentBrawler?:c.selectedBrawler);val target=selectTarget(pg,o.enemies,o.timestampNanos)
        if(target==null){tracker.update(null,o.timestampNanos);TeamFollow.action(player,o.teammates,c)?.let{rememberMove(it.angleDegrees,o.timestampNanos);return listOf(it)};val age=o.timestampNanos-lastMoveNanos;return if(c.alwaysMove&&lastMoveAngle!=null&&age in 0L..350_000_000L&&lastTargetNanos>0L&&o.timestampNanos-lastTargetNanos<350_000_000L)listOf(MoveVector(lastMoveAngle!!,145f,320L))else emptyList()}
        val tg=ground(target);val relWorld=WorldCombatModel.vecToWorld(tg-pg);val distWorld=relWorld.length();val blocked=blocked(pg,tg,o.walls);val hittable=!blocked||profile.ignoreWallsForAttacks;lastTargetNanos=o.timestampNanos
        tracker.update(relWorld,o.timestampNanos,ownVelocity(profile,o.timestampNanos),WorldCombatModel.DEFAULT_MOVE_SPEED_WORLD)
        val actions=mutableListOf<BotAction>()
        AbilityPolicy.superAction(o.superReady,!blocked,WorldCombatModel.worldToPx(distWorld),o.timestampNanos,lastSuper,c)?.let{actions+=it;lastSuper=o.timestampNanos}
        if(hittable&&c.aimedAttacks&&inRange(profile,distWorld)){val cooldown=(attackInterval(profile,c)*1_000_000_000L).toLong();if(o.timestampNanos-lastAttack>=cooldown){val aim=if(c.smartAimEnabled&&c.leadShots)tracker.predicted(relWorld,profile.projectileSpeedWorld,profile.leadStrength,WorldCombatModel.BODY_RADIUS_WORLD,profile.projectileRadiusWorld,profile.attackRangeWorld)else relWorld;actions+=AttackVector(aim.angleDegrees(),attackRadius(profile,c),attackDuration(profile,c));lastAttack=o.timestampNanos}}
        if(c.alwaysMove){val a=chooseMovement(pg,relWorld,profile,o);rememberMove(a,o.timestampNanos);actions+=MoveVector(a,150f,320L)}
        return actions
    }

    private fun ground(b:EntityBox)=Vector2((b.left+b.right)/2f,b.bottom)
    private fun selectTarget(player:Vector2,enemies:List<EntityBox>,now:Long):EntityBox?{if(enemies.isEmpty())return null;val old=lockedRelativeWorld;if(old!=null&&lastTargetNanos>0L){val dt=((now-lastTargetNanos).coerceAtLeast(0L)/1_000_000_000f).coerceAtMost(.3f);val expected=old+tracker.currentVelocity()*dt;val candidate=enemies.minByOrNull{WorldCombatModel.vecToWorld(ground(it)-player).distanceTo(expected)};if(candidate!=null){val r=WorldCombatModel.vecToWorld(ground(candidate)-player);if(r.distanceTo(expected)<=WorldCombatModel.TARGET_STICKY_WORLD){lockedRelativeWorld=r;return candidate}};tracker.reset()};val fresh=enemies.minByOrNull{player.distanceTo(ground(it))}?:return null;lockedRelativeWorld=WorldCombatModel.vecToWorld(ground(fresh)-player);tracker.reset();return fresh}
    private fun inRange(p:BrawlerCombatProfile,d:Float):Boolean{val m=when(p.attackStyle){AttackStyle.MELEE,AttackStyle.DASH->.90f;AttackStyle.SHOTGUN->.84f;AttackStyle.SPRAY->.92f;else->1f};return d<=p.attackRangeWorld*m+WorldCombatModel.BODY_RADIUS_WORLD}
    private fun attackInterval(p:BrawlerCombatProfile,c:BotConfig)=max(c.attackMinIntervalSeconds,when(p.attackStyle){AttackStyle.MELEE,AttackStyle.DASH->.23f;AttackStyle.SHOTGUN->.28f;AttackStyle.SPRAY,AttackStyle.BURST->.24f;AttackStyle.THROWER->.38f;AttackStyle.SNIPER->.36f;else->.30f})
    private fun attackRadius(p:BrawlerCombatProfile,c:BotConfig)=when(p.attackStyle){AttackStyle.MELEE,AttackStyle.DASH->205f;AttackStyle.SHOTGUN->215f;else->c.aimSwipeRadius.coerceIn(220f,245f)}
    private fun attackDuration(p:BrawlerCombatProfile,c:BotConfig)=when(p.attackStyle){AttackStyle.THROWER->90L;AttackStyle.SNIPER->72L;AttackStyle.MELEE,AttackStyle.DASH->55L;else->(c.aimSwipeDurationSeconds*1000f).roundToLong().coerceIn(58L,85L)}

    private fun chooseMovement(player:Vector2,relWorld:Vector2,p:BrawlerCombatProfile,o:BotObservation):Float{
        val now=o.timestampNanos;if(strafeFlipAt==0L){strafeSide=if(((now/100_000_000L)and 1L)==0L)1f else-1f;strafeFlipAt=now+1_450_000_000L}else if(now>=strafeFlipAt){strafeSide=-strafeSide;strafeFlipAt=now+1_450_000_000L}
        val dist=relWorld.length();val desired=p.preferredRangeWorld;val before=abs(dist-desired);val toward=norm(relWorld);val tangent=Vector2(-toward.y*strafeSide,toward.x*strafeSide);val stepWorld=min(WorldCombatModel.MOVE_STEP_WORLD,p.moveSpeedWorld*.34f);val stepPx=WorldCombatModel.worldToPx(stepWorld);val previous=lastMoveDir;val scores=FloatArray(WorldCombatModel.DIRECTIONS);var best=0;var bestScore=-Float.MAX_VALUE;val inBand=abs(dist-desired)<max(130f,p.attackRangeWorld*.08f)
        for(i in 0 until WorldCombatModel.DIRECTIONS){val rad=2.0*Math.PI*i/WorldCombatModel.DIRECTIONS;val d=Vector2(cos(rad).toFloat(),sin(rad).toFloat());val next=relWorld-d*stepWorld;var score=(before-abs(next.length()-desired))*1.9f;score+=(d.x*tangent.x+d.y*tangent.y)*if(inBand)165f else 38f;if(previous!=null)score+=WorldCombatModel.MOMENTUM_WEIGHT*(d.x*previous.x+d.y*previous.y);val end=player+d*stepPx;if(hitsWall(player,end,o.walls,WorldCombatModel.worldToPx(105f)))score-=9000f;if(end.x<70f||end.x>1850f||end.y<70f||end.y>1010f)score-=2600f;for(e in o.enemies){val nd=WorldCombatModel.pxToWorld(end.distanceTo(ground(e)));val safety=max(620f,p.safeRangeWorld*.68f);if(nd<safety)score-=(safety-nd)*1.4f};scores[i]=score;if(score>bestScore){bestScore=score;best=i}}
        var chosen=best;if(lastMoveIndex>=0&&now<moveLockUntil&&lastMoveIndex<scores.size&&scores[lastMoveIndex]+WorldCombatModel.KEEP_BAND>=scores[best])chosen=lastMoveIndex else if(now>=moveLockUntil)moveLockUntil=now+WorldCombatModel.DIRECTION_LOCK_NANOS;lastMoveIndex=chosen;val angle=360f*chosen/WorldCombatModel.DIRECTIONS;val r=Math.toRadians(angle.toDouble());lastMoveDir=Vector2(cos(r).toFloat(),sin(r).toFloat());return angle
    }
    private fun ownVelocity(p:BrawlerCombatProfile,now:Long):Vector2{val d=lastMoveDir?:return Vector2(0f,0f);return if(now-lastMoveNanos<=500_000_000L)d*p.moveSpeedWorld else Vector2(0f,0f)}
    private fun rememberMove(a:Float,now:Long){lastMoveAngle=((a%360f)+360f)%360f;lastMoveNanos=now;val r=Math.toRadians(a.toDouble());lastMoveDir=Vector2(cos(r).toFloat(),sin(r).toFloat())}
    private fun hitsWall(a:Vector2,b:Vector2,w:List<EntityBox>,m:Float)=w.any{seg(a,b,it.left-m,it.top-m,it.right+m,it.bottom+m)}
    private fun blocked(a:Vector2,b:Vector2,w:List<EntityBox>)=w.any{seg(a,b,it.left,it.top,it.right,it.bottom)}
    private fun seg(a:Vector2,b:Vector2,l:Float,t:Float,r:Float,bt:Float):Boolean{var t0=0f;var t1=1f;val dx=b.x-a.x;val dy=b.y-a.y;fun clip(p:Float,q:Float):Boolean{if(abs(p)<1e-6f)return q>=0f;val x=q/p;if(p<0f){if(x>t1)return false;if(x>t0)t0=x}else{if(x<t0)return false;if(x<t1)t1=x};return true};return clip(-dx,a.x-l)&&clip(dx,r-a.x)&&clip(-dy,a.y-t)&&clip(dy,bt-a.y)}
    private fun norm(v:Vector2):Vector2{val l=v.length();return if(l<1e-4f)Vector2(0f,0f)else v*(1f/l)}
    private fun clear(){tracker.reset();lockedRelativeWorld=null;lastTargetNanos=0L;lastMoveDir=null;lastMoveAngle=null;lastMoveNanos=0L;lastMoveIndex=-1;moveLockUntil=0L}
}
''')

p=ROOT/'bot-core/src/main/kotlin/dev/pylarl/botcore/config/BotConfig.kt'
s=p.read_text()
if 'val selectedBrawler:' not in s:s=s.replace('    val debugOverlay: Boolean = false,\n','    val debugOverlay: Boolean = false,\n    val selectedBrawler: String = "shelly",\n')
p.write_text(s)

write('bot-core/src/test/kotlin/dev/pylarl/botcore/decision/WorldCombatV4Test.kt', r'''package dev.pylarl.botcore.decision
import dev.pylarl.botcore.action.*
import dev.pylarl.botcore.combat.*
import dev.pylarl.botcore.config.BotConfig
import dev.pylarl.botcore.vision.*
import org.junit.Assert.*
import org.junit.Test
import kotlin.math.abs
class WorldCombatV4Test {
 private fun obs(ts:Long,p:EntityBox,e:List<EntityBox>,b:String)=BotObservation(ts,p,e,emptyList(),emptyList(),emptyList(),null,false,false,false,b)
 @Test fun knownCanonicalRangesConvertToRoundedWorldRanges(){assertEquals(3000f,WorldCombatModel.roundedWorldRange(640f),.01f);assertEquals(600f,WorldCombatModel.roundedWorldRange(128f),.01f);assertEquals(2300f,WorldCombatModel.roundedWorldRange(490f),.01f)}
 @Test fun trackedVelocityIsCappedByPlausibleMovementSpeed(){val t=EnemyTracker();t.update(Vector2(0f,0f),1_000_000_000L);val v=t.update(Vector2(200f,0f),1_100_000_000L,targetMaxSpeedWorld=720f);assertTrue(v.length()<=972.01f)}
 @Test fun aimingUsesSameGroundAnchorForPlayerAndEnemy(){val p=EntityBox(100f,100f,200f,250f,1f);val e=EntityBox(300f,0f,400f,300f,1f);val a=GameplayDecisionEngine().decide(obs(1_000_000_000L,p,listOf(e),"shelly"),BotConfig(selectedBrawler="shelly",attackMinIntervalSeconds=.01f)).filterIsInstance<AttackVector>().first();assertTrue("angle=${a.angleDegrees}",a.angleDegrees in 5f..25f)}
 @Test fun verticalTargetDoesNotForceHardRightMovement(){val p=EntityBox(450f,400f,550f,520f,1f);val e=EntityBox(450f,20f,550f,140f,1f);val m=GameplayDecisionEngine().decide(obs(1_000_000_000L,p,listOf(e),"shelly"),BotConfig(selectedBrawler="shelly",aimedAttacks=false)).filterIsInstance<MoveVector>().first();val right=abs(((m.angleDegrees+180f)%360f)-180f);assertTrue("angle=${m.angleDegrees}",right>30f)}
}
''')
print('Applied independent world-coordinate combat v4')
