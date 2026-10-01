from pathlib import Path

p = Path('project/bot-core/src/main/kotlin/dev/pylarl/botcore/decision/GameplayDecisionEngine.kt')
s = p.read_text(encoding='utf-8')

old_fields = '    private var moveLockUntil=0L;private var lastMoveIndex=-1;private var strafeSide=1f;private var strafeFlipAt=0L\n'
new_fields = '    private var moveLockUntil=0L;private var lastMoveIndex=-1;private var strafeSide=1f;private var strafeFlipAt=0L\n    private var exploreHeadingIndex=-1;private var exploreTurnAt=0L\n'
if old_fields not in s:
    raise SystemExit('field anchor not found')
s = s.replace(old_fields, new_fields, 1)

old_no_target = '        if(target==null){tracker.update(null,o.timestampNanos);TeamFollow.action(player,o.teammates,c)?.let{rememberMove(it.angleDegrees,o.timestampNanos);return listOf(it)};val age=o.timestampNanos-lastMoveNanos;return if(c.alwaysMove&&lastMoveAngle!=null&&age in 0L..350_000_000L&&lastTargetNanos>0L&&o.timestampNanos-lastTargetNanos<350_000_000L)listOf(MoveVector(lastMoveAngle!!,145f,320L))else emptyList()}\n'
new_no_target = '''        if(target==null){
            tracker.update(null,o.timestampNanos)
            TeamFollow.action(player,o.teammates,c)?.let{rememberMove(it.angleDegrees,o.timestampNanos);return listOf(it)}
            if(!c.alwaysMove)return emptyList()
            val age=o.timestampNanos-lastMoveNanos
            val recentlySawTarget=lastTargetNanos>0L&&o.timestampNanos-lastTargetNanos<500_000_000L
            val angle=if(lastMoveAngle!=null&&age in 0L..500_000_000L&&recentlySawTarget) lastMoveAngle!! else chooseExplorationMovement(pg,o)
            rememberMove(angle,o.timestampNanos)
            return listOf(MoveVector(angle,150f,320L))
        }
'''
if old_no_target not in s:
    raise SystemExit('no-target anchor not found')
s = s.replace(old_no_target, new_no_target, 1)

old_range = '    private fun inRange(p:BrawlerCombatProfile,d:Float):Boolean{val m=when(p.attackStyle){AttackStyle.MELEE,AttackStyle.DASH->.90f;AttackStyle.SHOTGUN->.84f;AttackStyle.SPRAY->.92f;else->1f};return d<=p.attackRangeWorld*m+WorldCombatModel.BODY_RADIUS_WORLD}\n'
new_range = '''    private fun inRange(p:BrawlerCombatProfile,d:Float):Boolean {
        // attackRangeWorld already represents the weapon's nominal cast range.
        // Do not shorten it by attack style; that suppressed valid shots (especially shotguns).
        return d <= p.attackRangeWorld + WorldCombatModel.BODY_RADIUS_WORLD
    }
'''
if old_range not in s:
    raise SystemExit('inRange anchor not found')
s = s.replace(old_range, new_range, 1)

old_choose_header = '        val dist=relWorld.length();val desired=p.preferredRangeWorld;val before=abs(dist-desired);val toward=norm(relWorld);val tangent=Vector2(-toward.y*strafeSide,toward.x*strafeSide);val stepWorld=min(WorldCombatModel.MOVE_STEP_WORLD,p.moveSpeedWorld*.34f);val stepPx=WorldCombatModel.worldToPx(stepWorld);val previous=lastMoveDir;val scores=FloatArray(WorldCombatModel.DIRECTIONS);var best=0;var bestScore=-Float.MAX_VALUE;val inBand=abs(dist-desired)<max(130f,p.attackRangeWorld*.08f)\n'
new_choose_header = '        val dist=relWorld.length();val desired=p.preferredRangeWorld;val before=abs(dist-desired);val toward=norm(relWorld);val tangent=Vector2(-toward.y*strafeSide,toward.x*strafeSide);val stepWorld=min(WorldCombatModel.MOVE_STEP_WORLD,p.moveSpeedWorld*.34f);val stepPx=WorldCombatModel.worldToPx(stepWorld);val previous=lastMoveDir;val scores=FloatArray(WorldCombatModel.DIRECTIONS);var best=0;var bestScore=-Float.MAX_VALUE;val inBand=abs(dist-desired)<max(130f,p.attackRangeWorld*.08f);val startWallClearance=nearestWallDistance(player,o.walls)\n'
if old_choose_header not in s:
    raise SystemExit('choose header anchor not found')
s = s.replace(old_choose_header, new_choose_header, 1)

old_loop = '        for(i in 0 until WorldCombatModel.DIRECTIONS){val rad=2.0*Math.PI*i/WorldCombatModel.DIRECTIONS;val d=Vector2(cos(rad).toFloat(),sin(rad).toFloat());val next=relWorld-d*stepWorld;var score=(before-abs(next.length()-desired))*1.9f;score+=(d.x*tangent.x+d.y*tangent.y)*if(inBand)165f else 38f;if(previous!=null)score+=WorldCombatModel.MOMENTUM_WEIGHT*(d.x*previous.x+d.y*previous.y);val end=player+d*stepPx;if(hitsWall(player,end,o.walls,WorldCombatModel.worldToPx(105f)))score-=9000f;if(end.x<70f||end.x>1850f||end.y<70f||end.y>1010f)score-=2600f;for(e in o.enemies){val nd=WorldCombatModel.pxToWorld(end.distanceTo(ground(e)));val safety=max(620f,p.safeRangeWorld*.68f);if(nd<safety)score-=(safety-nd)*1.4f};scores[i]=score;if(score>bestScore){bestScore=score;best=i}}\n'
new_loop = '''        for(i in 0 until WorldCombatModel.DIRECTIONS){
            val rad=2.0*Math.PI*i/WorldCombatModel.DIRECTIONS
            val d=Vector2(cos(rad).toFloat(),sin(rad).toFloat())
            val next=relWorld-d*stepWorld
            var score=(before-abs(next.length()-desired))*1.9f
            score+=(d.x*tangent.x+d.y*tangent.y)*if(inBand)165f else 38f
            if(previous!=null)score+=WorldCombatModel.MOMENTUM_WEIGHT*(d.x*previous.x+d.y*previous.y)
            val end=player+d*stepPx
            if(hitsWall(player,end,o.walls,WorldCombatModel.worldToPx(105f)))score-=9000f
            val endWallClearance=nearestWallDistance(end,o.walls)
            val wallComfort=130f
            if(endWallClearance<wallComfort)score-=(wallComfort-endWallClearance)*18f
            if(endWallClearance<startWallClearance)score-=(startWallClearance-endWallClearance)*14f
            else score+=min(endWallClearance-startWallClearance,80f)*4f
            val edgeClearance=min(min(end.x,1920f-end.x),min(end.y,1080f-end.y))
            if(edgeClearance<105f)score-=(105f-edgeClearance)*16f
            for(e in o.enemies){val nd=WorldCombatModel.pxToWorld(end.distanceTo(ground(e)));val safety=max(620f,p.safeRangeWorld*.68f);if(nd<safety)score-=(safety-nd)*1.4f}
            scores[i]=score
            if(score>bestScore){bestScore=score;best=i}
        }
'''
if old_loop not in s:
    raise SystemExit('movement loop anchor not found')
s = s.replace(old_loop, new_loop, 1)

anchor = '    private fun ownVelocity(p:BrawlerCombatProfile,now:Long):Vector2{val d=lastMoveDir?:return Vector2(0f,0f);return if(now-lastMoveNanos<=500_000_000L)d*p.moveSpeedWorld else Vector2(0f,0f)}\n'
helpers = r'''    private fun chooseExplorationMovement(player:Vector2,o:BotObservation):Float {
        val now=o.timestampNanos
        if(exploreHeadingIndex<0){
            val seed=((now/100_000_000L)+(player.x*3f+player.y*5f).toLong()).toInt()
            exploreHeadingIndex=((seed%WorldCombatModel.DIRECTIONS)+WorldCombatModel.DIRECTIONS)%WorldCombatModel.DIRECTIONS
            exploreTurnAt=now+1_900_000_000L
        }else if(now>=exploreTurnAt){
            exploreHeadingIndex=(exploreHeadingIndex+11)%WorldCombatModel.DIRECTIONS
            exploreTurnAt=now+1_900_000_000L
        }
        val stepPx=WorldCombatModel.worldToPx(WorldCombatModel.MOVE_STEP_WORLD)
        val previous=lastMoveDir
        val preferredRad=2.0*Math.PI*exploreHeadingIndex/WorldCombatModel.DIRECTIONS
        val preferred=Vector2(cos(preferredRad).toFloat(),sin(preferredRad).toFloat())
        val startWallClearance=nearestWallDistance(player,o.walls)
        var best=0
        var bestScore=-Float.MAX_VALUE
        for(i in 0 until WorldCombatModel.DIRECTIONS){
            val rad=2.0*Math.PI*i/WorldCombatModel.DIRECTIONS
            val d=Vector2(cos(rad).toFloat(),sin(rad).toFloat())
            val end=player+d*stepPx
            var score=(d.x*preferred.x+d.y*preferred.y)*85f
            if(previous!=null)score+=(d.x*previous.x+d.y*previous.y)*115f
            if(hitsWall(player,end,o.walls,WorldCombatModel.worldToPx(110f)))score-=9000f
            val wallClearance=nearestWallDistance(end,o.walls)
            if(wallClearance<145f)score-=(145f-wallClearance)*20f
            if(wallClearance<startWallClearance)score-=(startWallClearance-wallClearance)*15f
            else score+=min(wallClearance-startWallClearance,90f)*4f
            val edgeClearance=min(min(end.x,1920f-end.x),min(end.y,1080f-end.y))
            if(edgeClearance<120f)score-=(120f-edgeClearance)*18f
            else score+=min(edgeClearance,260f)*.15f
            if(score>bestScore){bestScore=score;best=i}
        }
        val angle=360f*best/WorldCombatModel.DIRECTIONS
        val r=Math.toRadians(angle.toDouble())
        lastMoveIndex=best
        lastMoveDir=Vector2(cos(r).toFloat(),sin(r).toFloat())
        return angle
    }

    private fun nearestWallDistance(point:Vector2,walls:List<EntityBox>):Float {
        if(walls.isEmpty())return 10_000f
        var best=Float.MAX_VALUE
        for(w in walls){
            val dx=when{point.x<w.left->w.left-point.x;point.x>w.right->point.x-w.right;else->0f}
            val dy=when{point.y<w.top->w.top-point.y;point.y>w.bottom->point.y-w.bottom;else->0f}
            val distance=sqrt(dx*dx+dy*dy)
            if(distance<best)best=distance
        }
        return best
    }

'''
if anchor not in s:
    raise SystemExit('helper anchor not found')
s = s.replace(anchor, helpers + anchor, 1)

old_clear = '    private fun clear(){tracker.reset();lockedRelativeWorld=null;lastTargetNanos=0L;lastMoveDir=null;lastMoveAngle=null;lastMoveNanos=0L;lastMoveIndex=-1;moveLockUntil=0L}\n'
new_clear = '    private fun clear(){tracker.reset();lockedRelativeWorld=null;lastTargetNanos=0L;lastMoveDir=null;lastMoveAngle=null;lastMoveNanos=0L;lastMoveIndex=-1;moveLockUntil=0L;exploreHeadingIndex=-1;exploreTurnAt=0L}\n'
if old_clear not in s:
    raise SystemExit('clear anchor not found')
s = s.replace(old_clear, new_clear, 1)

p.write_text(s, encoding='utf-8')
print('attack + exploration + wall avoidance v5 patch applied')
