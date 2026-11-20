"""Real-window acceptance and reproducible render artifacts for the native port.

Uses real SDL windows and synthetic SDL test events, explicitly distinguished
from physical keyboard automation. Never contacts a model or web service.
"""
from copy import copy
import argparse
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pygame as pg
from native.controls import Keyboard
from native.game import LocalGame,replay
from native.policy import drive_reference
from native.timing import DecisionSession,RealtimeClock
from native.window import Renderer,handle_events


def png(renderer,folder,name):
    path=folder/(name+'.png')
    pg.image.save(renderer.screen,str(path))
    return str(path)


def check_input_and_pacing(interval,folder):
    game=LocalGame(decision_seconds=interval)
    session=DecisionSession(game); keys=Keyboard(); renderer=Renderer(game)
    renderer.draw(False,False)
    # Use the real event queue and the same event handler as normal play.
    pg.event.clear()
    for event in [pg.event.Event(pg.KEYDOWN,key=pg.K_w),pg.event.Event(pg.KEYDOWN,key=pg.K_d),
                  pg.event.Event(pg.KEYDOWN,key=pg.K_DOWN)]: pg.event.post(event)
    active,paused,cleared=handle_events(pg.event.get(),keys,session)
    assert active and not paused
    actions=keys.sample(); assert actions['human']['move']==[1,-1] and actions['jeff']['move']==[0,1]
    session.advance_tick(actions,evidence=keys.last_evidence)
    for key in [pg.K_w,pg.K_d,pg.K_DOWN]: pg.event.post(pg.event.Event(pg.KEYUP,key=key))
    handle_events(pg.event.get(),keys,session)
    session.advance_tick(keys.sample(),evidence=keys.last_evidence)
    assert all(v==(0,0) for v in game.k.manual.values())
    # Pause/resume and focus-loss must clear queued button edges and both chefs.
    for key in [pg.K_SPACE,pg.K_RETURN]: keys.press(pg.key.name(key))
    pg.event.post(pg.event.Event(pg.KEYDOWN,key=pg.K_p))
    active,paused,cleared=handle_events(pg.event.get(),keys,session)
    assert paused and cleared and not keys.held and all(not q for q in keys.buttons.values())
    frozen=game.k.time; pacer=RealtimeClock()
    pacer.add(2,paused=True); assert not pacer.pop_tick() and game.k.time==frozen
    pg.event.post(pg.event.Event(pg.KEYDOWN,key=pg.K_p))
    active,paused,cleared=handle_events(pg.event.get(),keys,session,paused)
    assert not paused
    keys.press('w'); session.advance_tick(keys.sample())
    pg.event.post(pg.event.Event(pg.WINDOWFOCUSLOST))
    _,paused,cleared=handle_events(pg.event.get(),keys,session)
    assert paused and cleared and all(v==(0,0) for v in game.k.manual.values())
    renderer.draw(paused,False); png(renderer,folder,f'paused-{interval:g}')
    session.close('input_test_complete')

    # Actual wall-clock presentation, independent of the decision period.
    game=LocalGame(decision_seconds=interval); session=DecisionSession(game)
    renderer=Renderer(game); renderer.draw(False,False); pg.event.clear()
    pacer=RealtimeClock(); clock=pg.time.Clock(); frames=0; start=time.perf_counter()
    while game.tick<40:
        pacer.add(clock.tick(60)/1000)
        pg.event.pump()
        while game.tick<40 and pacer.pop_tick(): session.advance_tick()
        renderer.draw(False,False); frames+=1
    elapsed=time.perf_counter()-start
    assert abs(game.k.time-2)<1e-8 and game.tick==40
    assert session.index==(20 if interval==.1 else 2)
    result={'decision_seconds':interval,'simulation_seconds':game.k.time,'ticks':game.tick,
            'decisions':session.index,'wall_seconds':elapsed,'frames':frames,
            'synthetic_key_pause_focus_checks':'passed'}
    session.close('pacing_test_complete')
    return result


def run_trace(level,interval,folder,seed=7):
    path=folder/f'window-{level}-{interval:g}.jsonl'
    game=LocalGame(level=level,seed=seed,decision_seconds=interval,record=path,
                   runtime={'render_fps':60,'presentation':'original','pacing':'unpaced_render_acceptance'})
    session=DecisionSession(game,on_decision=drive_reference); renderer=Renderer(game)
    captured={}; displayed=0
    try:
        while not game.k.ended:
            if any(event.type==pg.QUIT for event in pg.event.get()):
                raise RuntimeError('visual acceptance canceled by window close')
            session.advance_tick()
            state=game.state()
            names=[]
            if game.tick==1: names.append('initial')
            if any(c['working'] and c['action_kind']=='chop' for c in state['chefs'].values()): names.append('chopping')
            if any(c['holding'] and c['holding'].get('contents') for c in state['chefs'].values()): names.append('held-vessel')
            if any(c['holding'] and c['holding'].get('plate_id') for c in state['chefs'].values()): names.append('plated')
            if any(s.get('food') and s['food']['stage']=='ready' for s in state['stations'].values()): names.append('ready')
            if any(s['fire'] for s in state['stations'].values()): names.append('fire')
            if state['projectiles']: names.append('throw')
            if any(e.get('kind')=='caught' and abs(e.get('t',0)-game.k.time)<.051 for e in game.k.events[-8:]): names.append('caught')
            if game.k.served: names.append('served')
            new=[name for name in names if name not in captured]
            if new or game.tick%10==0 or game.k.ended:
                renderer.draw(False,True); displayed+=1
                assert not renderer.sprite_painter.builder.missing,renderer.sprite_painter.builder.missing
                for name in new: captured[name]=png(renderer,folder,f'{level}-{interval:g}-{name}')
        renderer.draw(False,True)
        captured['final']=png(renderer,folder,f'{level}-{interval:g}-final')
        result={'level':level,'seed':seed,'decision_seconds':interval,'score':game.k.money,'served':game.k.served,
                'rendered_frames':displayed,'screenshots':captured}
    finally:
        session.close('round_complete' if game.k.ended else 'acceptance_interrupted')
    result['replay']=replay(path)
    return result


def reference_sheet(folder):
    # Source pixels only; original atlases/manifests remain read-only.
    game=LocalGame(); renderer=Renderer(game); painter=renderer.sprite_painter
    names=['characters/player/down/idle_0','characters/player/right/chop_2','characters/jeff/down/idle_0',
           'characters/jeff/up/walk_3','modular/counter_south','modular/device_board_vertical',
           'modular/pan_vertical/beef/ready','objects/clean_plate','dishes/steak/ready','food/burger_ready',
           'modular/sink_unit_east','knife/v1/arc/right_2']
    sheet=pg.Surface((900,600)); sheet.fill((240,217,181)); font=pg.font.Font(None,17)
    for n,key in enumerate(names):
        x=(n%4)*225; y=(n//4)*200
        sprite=painter.sprite(key); w,h=sprite.get_size(); scale=min(160/w,145/h)
        image=pg.transform.scale(sprite,(round(w*scale),round(h*scale)))
        sheet.blit(image,(x+110-image.get_width()//2,y+15))
        label=key.replace('characters/','').replace('modular/','')
        sheet.blit(font.render(label,True,(43,26,18)),(x+4,y+177))
    path=folder/'original-atlas-reference.png'; pg.image.save(sheet,str(path)); game.close('reference_sheet')
    return str(path)


def pose_and_map_checks(folder):
    images=[]
    for level in ('level-1','level-2','level-3','level-4'):
        game=LocalGame(level=level); renderer=Renderer(game)
        renderer.draw(False,False)
        images.append(png(renderer,folder,level+'-layout'))
        game.close('layout_check')
    # Explicit visual fixtures: snapshot-only poses; no gameplay/log claims.
    for facing in ('up','down','left','right'):
        game=LocalGame(); renderer=Renderer(game); state=game.state()
        state['chefs']['human'].update(facing=facing,working=True,action_kind='chop',target='b1')
        state['chefs']['jeff'].update(facing=facing,working=True,action_kind='chop',target='b2')
        visual=copy(game.k); visual.time=.15
        renderer.screen.fill((240,217,181))
        renderer.sprite_painter.draw(renderer.screen,visual,state)
        renderer.text('Visual fixture: original chop poses / '+facing,20,30)
        pg.display.flip()
        images.append(png(renderer,folder,'chop-fixture-'+facing))
        game.close('fixture_check')
    return images


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seed',type=int,default=7,help='Frozen spawn/order seed for the full rendering round')
    parser.add_argument('--split-only',action='store_true',help='Check the partitioned throw/catch kitchen instead of repeating level 3 rounds')
    args=parser.parse_args(); folder=args.output.resolve()
    if folder.exists() and (not folder.is_dir() or any(folder.iterdir())):
        parser.error('output folder must be new or empty; existing evidence is never overwritten')
    folder.mkdir(parents=True,exist_ok=True)
    pg.init()
    if pg.display.get_driver()=='dummy': raise RuntimeError('a real SDL display is required')
    try:
        report={'driver':pg.display.get_driver(),'input_source':'synthetic SDL events; physical keyboard not claimed',
                'pacing':[check_input_and_pacing(interval,folder) for interval in (.1,1)],
                'reference_sheet':reference_sheet(folder),'pose_and_map_images':pose_and_map_checks(folder),
                'rounds':([run_trace('level-4',.1,folder,args.seed)] if args.split_only else [run_trace('level-3',interval,folder,args.seed) for interval in (.1,1)])}
        (folder/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,indent=2))
    finally: pg.quit()


if __name__=='__main__': main()
