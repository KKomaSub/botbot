from pathlib import Path
ROOT=Path('project')
def write(rel,text):
    p=ROOT/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8')

write('bot-core/src/main/kotlin/dev/pylarl/botcore/decision/FriendlyFireGuard.kt',r'''package dev.pylarl.botcore.decision

import dev.pylarl.botcore.combat.WorldCombatModel
import dev.pylarl.botcore.vision.EntityBox
import dev.pylarl.botcore.vision.Vector2
import java.util.ArrayDeque
import kotlin.math.max
import kotlin.math.min

class FriendlyFireGuard {
    private data class FriendMark(val relativeWorld:Vector2,val at:Long)
    private val friends=ArrayDeque<FriendMark>()
    private var enemyMark:Vector2?=null
    private var enemyAt=0L
    private var enemyStreak=0

    fun observe(player:Vector2,teammates:List<EntityBox>,now:Long){
        prune(now)
        for(t in teammates){
            val rel=WorldCombatModel.vecToWorld(ground(t)-player)
            friends.addLast(FriendMark(rel,now))
        }
        while(friends.size>24)friends.removeFirst()
    }

    fun probablyFriendly(relativeWorld:Vector2,now:Long):Boolean{
        prune(now)
        return friends.any{it.relativeWorld.distanceTo(relativeWorld)<=320f}
    }

    fun confirmedEnemy(relativeWorld:Vector2,now:Long):Boolean{
        if(probablyFriendly(relativeWorld,now)){
            enemyMark=null;enemyAt=0L;enemyStreak=0
            return false
        }
        val old=enemyMark
        val continuous=old!=null&&now-enemyAt in 1L..420_000_000L&&old.distanceTo(relativeWorld)<=520f
        enemyStreak=if(continuous)enemyStreak+1 else 1
        enemyMark=relativeWorld;enemyAt=now
        return enemyStreak>=2
    }

    fun shotLaneClear(player:Vector2,target:Vector2,teammates:List<EntityBox>):Boolean{
        val vx=target.x-player.x;val vy=target.y-player.y;val len2=vx*vx+vy*vy
        if(len2<1f)return true
        for(t in teammates){
            val p=ground(t)
            val wx=p.x-player.x;val wy=p.y-player.y
            val u=((wx*vx+wy*vy)/len2).coerceIn(0f,1f)
            if(u<=.08f||u>=.96f)continue
            val px=player.x+vx*u;val py=player.y+vy*u
            val dx=p.x-px;val dy=p.y-py
            val body=max(28f,min(62f,(t.right-t.left)*.48f))
            if(dx*dx+dy*dy<=body*body)return false
        }
        return true
    }

    fun reset(){friends.clear();enemyMark=null;enemyAt=0L;enemyStreak=0}
    private fun prune(now:Long){while(friends.isNotEmpty()&&now-friends.first.at>700_000_000L)friends.removeFirst()}
    private fun ground(b:EntityBox)=Vector2((b.left+b.right)/2f,b.bottom)
}
''')

write('bot-core/src/main/kotlin/dev/pylarl/botcore/decision/WallEscape.kt',r'''package dev.pylarl.botcore.decision

import dev.pylarl.botcore.action.MoveVector
import dev.pylarl.botcore.config.BotConfig
import dev.pylarl.botcore.vision.BotObservation

/**
 * Screen-space player coordinates are camera-locked in Brawl Stars, so lack of
 * player-box motion cannot prove the world character is stuck. Legacy wall
 * escape used that signal and caused false escape turns during normal travel.
 * Obstacle avoidance now lives in GameplayDecisionEngine's corridor planner.
 */
class WallEscape {
    fun update(observation:BotObservation,config:BotConfig):MoveVector?=null
}
''')

write('bot-core/src/main/kotlin/dev/pylarl/botcore/decision/TeamFollow.kt',r'''package dev.pylarl.botcore.decision
import dev.pylarl.botcore.action.MoveVector
import dev.pylarl.botcore.config.BotConfig
import dev.pylarl.botcore.vision.*
object TeamFollow {
 fun action(player:EntityBox?,teammates:List<EntityBox>,config:BotConfig):MoveVector? {
  val p=player?.footPosition()?:return null
  val target=teammates.minByOrNull{p.distanceTo(it.center())}?:return null
  val d=p.distanceTo(target.center())
  if(d<=config.teammateFollowMinDistance||d>=config.teammateFollowMaxDistance)return null
  return MoveVector((target.center()-p).angleDegrees(),150f,220L)
 }
}
''')

write('bot-core/src/main/kotlin/dev/pylarl/botcore/decision/GameplayDecisionEngine.kt',r'''package dev.pylarl.botcore.decision

import dev.pylarl.botcore.action.*
import dev.pylarl.botcore.combat.*
import dev.pylarl.botcore.config.BotConfig
import dev.pylarl.botcore.vision.*
import kotlin.math.*

class GameplayDecisionEngine {
    private val tracker=EnemyTracker()
    private val friendGuard=FriendlyFireGuard()
    private var lastAttack=Long.MIN_VALUE/2
    private var lastSuper=0L
    private var lockedRelativeWorld:Vector2?=null
    private var lastTargetNanos=0L
    private var lastMoveDir:Vector2?=null
    private var lastMoveAngle:Float?=null
    private var lastMoveNanos=0L
    private var moveLockUntil=0L
    private var lastMoveIndex=-1
    private var strafeSide=1f
    private var strafeFlipAt=0L
    private var roamHeadingIndex=-1

    fun decide(o:BotObservation,c:BotConfig):List<BotAction>{
        FogAvoidance.action(o.fogEscapeVector)?.let{rememberMove(it.angleDegrees,o.timestampNanos);return listOf(it)}
        val player=o.player?:run{clear();return emptyList()}
        val pg=ground(player)
        friendGuard.observe(pg,o.teammates,o.timestampNanos)
        val enemies=sanitizeEnemies(pg,o.enemies,o.teammates,o.timestampNanos)
        val profile=BrawlerCombatProfiles.forName(o.currentBrawler?:c.selectedBrawler)
        val target=selectTarget(pg,enemies,o.timestampNanos)

        if(target==null){
            tracker.update(null,o.timestampNanos)
            if(!c.alwaysMove)return emptyList()
            val angle=chooseRoamMovement(pg,o)
            rememberMove(angle,o.timestampNanos)
            return listOf(MoveVector(angle,150f,360L))
        }

        val tg=ground(target)
        val relWorld=WorldCombatModel.vecToWorld(tg-pg)
        val distWorld=relWorld.length()
        val blocked=blocked(pg,tg,o.walls)
        val hittable=!blocked||profile.ignoreWallsForAttacks
        lastTargetNanos=o.timestampNanos
        tracker.update(relWorld,o.timestampNanos,ownVelocity(profile,o.timestampNanos),WorldCombatModel.DEFAULT_MOVE_SPEED_WORLD)
        val hostileConfirmed=friendGuard.confirmedEnemy(relWorld,o.timestampNanos)
        val clearOfFriends=friendGuard.shotLaneClear(pg,tg,o.teammates)
        val actions=mutableListOf<BotAction>()

        AbilityPolicy.superAction(o.superReady,!blocked,WorldCombatModel.worldToPx(distWorld),o.timestampNanos,lastSuper,c)?.let{actions+=it;lastSuper=o.timestampNanos}
        if(hostileConfirmed&&clearOfFriends&&hittable&&c.aimedAttacks&&inRange(profile,distWorld)){
            val cooldown=(attackInterval(profile,c)*1_000_000_000L).toLong()
            if(o.timestampNanos-lastAttack>=cooldown){
                val aim=if(c.smartAimEnabled&&c.leadShots)tracker.predicted(relWorld,profile.projectileSpeedWorld,profile.leadStrength,WorldCombatModel.BODY_RADIUS_WORLD,profile.projectileRadiusWorld,profile.attackRangeWorld)else relWorld
                actions+=AttackVector(aim.angleDegrees(),attackRadius(profile,c),attackDuration(profile,c))
                lastAttack=o.timestampNanos
            }
        }
        if(c.alwaysMove){
            val angle=chooseCombatMovement(pg,relWorld,profile,o,enemies)
            rememberMove(angle,o.timestampNanos)
            actions+=MoveVector(angle,150f,340L)
        }
        return actions
    }

    private fun sanitizeEnemies(player:Vector2,enemies:List<EntityBox>,teammates:List<EntityBox>,now:Long):List<EntityBox>{
        if(enemies.isEmpty())return emptyList()
        return enemies.filter{e->
            val eg=ground(e)
            val sameFrameFriend=teammates.any{t->ground(t).distanceTo(eg)<=max(42f,(e.right-e.left)*.55f)}
            val rel=WorldCombatModel.vecToWorld(eg-player)
            !sameFrameFriend&&!friendGuard.probablyFriendly(rel,now)
        }
    }

    private fun ground(b:EntityBox)=Vector2((b.left+b.right)/2f,b.bottom)

    private fun selectTarget(player:Vector2,enemies:List<EntityBox>,now:Long):EntityBox?{
        if(enemies.isEmpty()){lockedRelativeWorld=null;return null}
        val old=lockedRelativeWorld
        if(old!=null&&lastTargetNanos>0L){
            val dt=((now-lastTargetNanos).coerceAtLeast(0L)/1_000_000_000f).coerceAtMost(.3f)
            val expected=old+tracker.currentVelocity()*dt
            val candidate=enemies.minByOrNull{WorldCombatModel.vecToWorld(ground(it)-player).distanceTo(expected)}
            if(candidate!=null){
                val rel=WorldCombatModel.vecToWorld(ground(candidate)-player)
                if(rel.distanceTo(expected)<=WorldCombatModel.TARGET_STICKY_WORLD){lockedRelativeWorld=rel;return candidate}
            }
            tracker.reset()
        }
        val fresh=enemies.minByOrNull{player.distanceTo(ground(it))}?:return null
        lockedRelativeWorld=WorldCombatModel.vecToWorld(ground(fresh)-player)
        tracker.reset()
        return fresh
    }

    private fun inRange(p:BrawlerCombatProfile,d:Float)=d<=p.attackRangeWorld+WorldCombatModel.BODY_RADIUS_WORLD
    private fun attackInterval(p:BrawlerCombatProfile,c:BotConfig)=max(c.attackMinIntervalSeconds,when(p.attackStyle){AttackStyle.MELEE,AttackStyle.DASH->.23f;AttackStyle.SHOTGUN->.28f;AttackStyle.SPRAY,AttackStyle.BURST->.24f;AttackStyle.THROWER->.38f;AttackStyle.SNIPER->.36f;else->.30f})
    private fun attackRadius(p:BrawlerCombatProfile,c:BotConfig)=when(p.attackStyle){AttackStyle.MELEE,AttackStyle.DASH->205f;AttackStyle.SHOTGUN->215f;else->c.aimSwipeRadius.coerceIn(220f,245f)}
    private fun attackDuration(p:BrawlerCombatProfile,c:BotConfig)=when(p.attackStyle){AttackStyle.THROWER->90L;AttackStyle.SNIPER->72L;AttackStyle.MELEE,AttackStyle.DASH->55L;else->(c.aimSwipeDurationSeconds*1000f).roundToLong().coerceIn(58L,85L)}

    private fun chooseCombatMovement(player:Vector2,relWorld:Vector2,p:BrawlerCombatProfile,o:BotObservation,enemies:List<EntityBox>):Float{
        val now=o.timestampNanos
        if(strafeFlipAt==0L){strafeSide=if(((now/100_000_000L)and 1L)==0L)1f else-1f;strafeFlipAt=now+1_450_000_000L}
        else if(now>=strafeFlipAt){strafeSide=-strafeSide;strafeFlipAt=now+1_450_000_000L}
        val dist=relWorld.length();val desired=p.preferredRangeWorld;val before=abs(dist-desired);val toward=norm(relWorld)
        val tangent=Vector2(-toward.y*strafeSide,toward.x*strafeSide)
        val stepWorld=min(WorldCombatModel.MOVE_STEP_WORLD,p.moveSpeedWorld*.34f)
        val stepPx=WorldCombatModel.worldToPx(stepWorld)
        val previous=lastMoveDir
        val scores=FloatArray(WorldCombatModel.DIRECTIONS)
        var best=0;var bestScore=-Float.MAX_VALUE
        val inBand=abs(dist-desired)<max(130f,p.attackRangeWorld*.08f)
        val bodyRadius=max(24f,WorldCombatModel.worldToPx(WorldCombatModel.BODY_RADIUS_WORLD)+11f)
        for(i in 0 until WorldCombatModel.DIRECTIONS){
            val d=direction(i)
            val next=relWorld-d*stepWorld
            var score=(before-abs(next.length()-desired))*1.9f
            score+=(d.x*tangent.x+d.y*tangent.y)*if(inBand)165f else 38f
            if(previous!=null)score+=WorldCombatModel.MOMENTUM_WEIGHT*(d.x*previous.x+d.y*previous.y)
            if(pathBlocked(player,d,o.walls,bodyRadius,150f))score-=12000f
            score+=min(corridorClearance(player,d,o.walls,bodyRadius,160f),150f)*2.2f
            val end=player+d*stepPx
            score+=edgeScore(end)
            for(e in enemies){val nd=WorldCombatModel.pxToWorld(end.distanceTo(ground(e)));val safety=max(620f,p.safeRangeWorld*.68f);if(nd<safety)score-=(safety-nd)*1.4f}
            scores[i]=score
            if(score>bestScore){bestScore=score;best=i}
        }
        var chosen=best
        if(lastMoveIndex>=0&&now<moveLockUntil&&lastMoveIndex<scores.size&&scores[lastMoveIndex]+WorldCombatModel.KEEP_BAND>=scores[best])chosen=lastMoveIndex
        else if(now>=moveLockUntil)moveLockUntil=now+WorldCombatModel.DIRECTION_LOCK_NANOS
        lastMoveIndex=chosen
        val d=direction(chosen);lastMoveDir=d
        return 360f*chosen/WorldCombatModel.DIRECTIONS
    }

    private fun chooseRoamMovement(player:Vector2,o:BotObservation):Float{
        val center=Vector2(960f,540f)
        val edge=min(min(player.x,1920f-player.x),min(player.y,1080f-player.y))
        if(roamHeadingIndex<0)roamHeadingIndex=bestInitialRoamHeading(player,o.walls)
        val desired=if(edge<150f)norm(center-player) else direction(roamHeadingIndex)
        val previous=lastMoveDir
        val bodyRadius=max(26f,WorldCombatModel.worldToPx(WorldCombatModel.BODY_RADIUS_WORLD)+13f)
        var best=roamHeadingIndex
        var bestScore=-Float.MAX_VALUE
        for(i in 0 until WorldCombatModel.DIRECTIONS){
            val d=direction(i)
            var score=(d.x*desired.x+d.y*desired.y)*520f
            if(previous!=null)score+=(d.x*previous.x+d.y*previous.y)*70f
            val blocked=pathBlocked(player,d,o.walls,bodyRadius,245f)
            if(blocked)score-=14000f
            val clearance=corridorClearance(player,d,o.walls,bodyRadius,245f)
            score+=min(clearance,190f)*3.2f
            val far=player+d*235f
            score+=edgeScore(far)*1.7f
            if(score>bestScore){bestScore=score;best=i}
        }
        val chosen=best
        lastMoveIndex=chosen;lastMoveDir=direction(chosen)
        return 360f*chosen/WorldCombatModel.DIRECTIONS
    }

    private fun bestInitialRoamHeading(player:Vector2,walls:List<EntityBox>):Int{
        val forward=36 // 270 degrees: away from the usual lower-team spawn toward map activity.
        val bodyRadius=max(26f,WorldCombatModel.worldToPx(WorldCombatModel.BODY_RADIUS_WORLD)+13f)
        var best=forward;var bestScore=-Float.MAX_VALUE
        for(offset in intArrayOf(0,-2,2,-4,4,-6,6,-8,8)){
            val i=(forward+offset+WorldCombatModel.DIRECTIONS)%WorldCombatModel.DIRECTIONS
            val d=direction(i)
            var score=500f-abs(offset)*18f
            if(pathBlocked(player,d,walls,bodyRadius,245f))score-=12000f
            score+=min(corridorClearance(player,d,walls,bodyRadius,245f),180f)*3f
            if(score>bestScore){bestScore=score;best=i}
        }
        return best
    }

    private fun pathBlocked(start:Vector2,dir:Vector2,walls:List<EntityBox>,radius:Float,lookahead:Float):Boolean{
        if(walls.isEmpty())return false
        val end=start+dir*lookahead
        for(w in walls){
            val l=w.left-radius;val t=w.top-radius;val r=w.right+radius;val b=w.bottom+radius
            val startClear=signedRectClearance(start,l,t,r,b)
            if(startClear<0f){
                var prev=startClear
                for(k in 1..6){
                    val p=start+dir*(lookahead*k/6f)
                    val cur=signedRectClearance(p,l,t,r,b)
                    if(cur<prev-1.5f)return true
                    prev=cur
                }
            }else if(seg(start,end,l,t,r,b))return true
        }
        return false
    }

    private fun corridorClearance(start:Vector2,dir:Vector2,walls:List<EntityBox>,radius:Float,lookahead:Float):Float{
        if(walls.isEmpty())return 500f
        var best=500f
        for(k in 1..6){
            val p=start+dir*(lookahead*k/6f)
            for(w in walls){
                val c=signedRectClearance(p,w.left-radius,w.top-radius,w.right+radius,w.bottom+radius)
                best=min(best,max(0f,c))
            }
        }
        return best
    }

    private fun signedRectClearance(p:Vector2,l:Float,t:Float,r:Float,b:Float):Float{
        val dx=when{p.x<l->l-p.x;p.x>r->p.x-r;else->0f}
        val dy=when{p.y<t->t-p.y;p.y>b->p.y-b;else->0f}
        if(dx>0f||dy>0f)return hypot(dx,dy)
        return -min(min(p.x-l,r-p.x),min(p.y-t,b-p.y))
    }

    private fun edgeScore(p:Vector2):Float{
        val c=min(min(p.x,1920f-p.x),min(p.y,1080f-p.y))
        return when{c<70f->-7000f;c<120f->-(120f-c)*35f;else->min(c,260f)*.15f}
    }

    private fun direction(index:Int):Vector2{val a=2.0*Math.PI*index/WorldCombatModel.DIRECTIONS;return Vector2(cos(a).toFloat(),sin(a).toFloat())}
    private fun ownVelocity(p:BrawlerCombatProfile,now:Long):Vector2{val d=lastMoveDir?:return Vector2(0f,0f);return if(now-lastMoveNanos<=500_000_000L)d*p.moveSpeedWorld else Vector2(0f,0f)}
    private fun rememberMove(a:Float,now:Long){lastMoveAngle=((a%360f)+360f)%360f;lastMoveNanos=now;val r=Math.toRadians(a.toDouble());lastMoveDir=Vector2(cos(r).toFloat(),sin(r).toFloat())}
    private fun blocked(a:Vector2,b:Vector2,w:List<EntityBox>)=w.any{seg(a,b,it.left,it.top,it.right,it.bottom)}
    private fun seg(a:Vector2,b:Vector2,l:Float,t:Float,r:Float,bt:Float):Boolean{var t0=0f;var t1=1f;val dx=b.x-a.x;val dy=b.y-a.y;fun clip(p:Float,q:Float):Boolean{if(abs(p)<1e-6f)return q>=0f;val x=q/p;if(p<0f){if(x>t1)return false;if(x>t0)t0=x}else{if(x<t0)return false;if(x<t1)t1=x};return true};return clip(-dx,a.x-l)&&clip(dx,r-a.x)&&clip(-dy,a.y-t)&&clip(dy,bt-a.y)}
    private fun norm(v:Vector2):Vector2{val l=v.length();return if(l<1e-4f)Vector2(0f,0f)else v*(1f/l)}
    private fun clear(){tracker.reset();friendGuard.reset();lockedRelativeWorld=null;lastTargetNanos=0L;lastMoveDir=null;lastMoveAngle=null;lastMoveNanos=0L;lastMoveIndex=-1;moveLockUntil=0L;roamHeadingIndex=-1}
}
''')
print('navigation/team v6 patch applied')
