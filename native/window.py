"""Pygame presentation only. All game rules stay in SpatialKitchen."""
import math
import pygame as pg
from model_language import english_data
from .controls import Keyboard
from .policy import drive_reference
from .timing import DecisionSession, RealtimeClock

BG = (240,217,181)
TEXT = (43,26,18)
MUTED = (110,78,56)
BLUE = (42,90,158)
ORANGE = (168,82,14)
TILE = 59
OX, OY = 20, 126


def food_text(food):
    if not food:
        return ''
    if food.get('contents'):
        return food.get('vessel', 'pot') + ': ' + food_text(food['contents'])
    stage = food['stage']
    if stage in ('clean_plate', 'dirty_plate', 'extinguisher', 'pot'):
        return stage.replace('_', ' ')
    name = '+'.join(food.get('components') or []) or food.get('ingredient', 'food')
    return ('plate: ' if food.get('plate_id') else '') + name + ' ' + stage


class Renderer:
    def __init__(self, game, art_mode='original'):
        self.game = game
        self.sprite_painter = None
        if art_mode == 'original':
            from .sprite_renderer import SpritePainter
            self.sprite_painter = SpritePainter(TILE,(OX,OY))
        self.board_width = game.k.width * TILE
        self.side = OX + self.board_width + 22
        self.screen = pg.display.set_mode((self.side + 345, max(820, OY + game.k.height * TILE + 140)))
        pg.display.set_caption('ChefJeff Native - Local two-player kitchen')
        self.font = pg.font.Font(None, 23)
        self.small = pg.font.Font(None, 18)
        self.title = pg.font.Font(None, 37)

    def text(self, text, x, y, color=TEXT, small=False):
        font = self.small if small else self.font
        self.screen.blit(font.render(str(text), True, color), (x, y))

    def wrap(self, text, x, y, width=315, color=MUTED):
        words = str(text).split()
        line = ''
        for word in words:
            test = line + (' ' if line else '') + word
            if self.small.size(test)[0] > width and line:
                self.text(line, x, y, color, True)
                y += 18
                line = word
            else:
                line = test
        self.text(line, x, y, color, True)
        return y + 20

    def point(self, p):
        return (round(OX + (p[0] + .5) * TILE), round(OY + (p[1] + .5) * TILE))

    def item(self, food, pos):
        if not food:
            return
        x, y = pos
        stage = food['stage']
        color = {'raw': (207, 100, 98), 'chopped': (240, 174, 124),
                 'ready': (122, 209, 116), 'assembled': (122, 209, 116),
                 'burnt': (70, 52, 45), 'clean_plate': (231, 236, 245),
                 'dirty_plate': (157, 156, 126), 'extinguisher': (238, 75, 67), 'pot': (107, 121, 140)}.get(stage, ORANGE)
        if food.get('plate_id'):
            pg.draw.circle(self.screen, (240, 240, 245), (x, y), 13)
        pg.draw.circle(self.screen, color, (x, y), 9)
        if stage == 'pot':
            pg.draw.line(self.screen, color, (x + 9, y), (x + 19, y), 5)
            if food.get('contents'):
                self.item(food['contents'], (x, y - 3))
        short = (food.get('ingredient') or '').upper()[:2]
        if short:
            self.text(short, x - 8, y - 6, (22, 25, 30), True)

    def draw(self, paused, demo):
        k, screen = self.game.k, self.screen
        s = self.game.state()
        screen.fill(BG)
        screen.blit(self.title.render('ChefJeff / LOCAL KITCHEN', True, TEXT), (20, 18))
        self.text(f"{s['level_id']}   Score ${s['money']}   Served {s['served']}   Remaining {s['round_remaining']:.1f}s", 22, 62)
        self.text(f"Decision {self.game.timing['decision_seconds']:g}s | tick {1/self.game.hz:g}s | Speed {self.game.runtime.get('game_speed', 1.0):g}x",540,94,MUTED,True)
        self.text(('PAUSED - P to resume' if paused else 'ROUND COMPLETE - Esc to close' if k.ended else 'SCRIPTED DEMO' if demo else 'TWO PLAYERS'), 22, 94, ORANGE)
        if self.sprite_painter:
            self.sprite_painter.draw(screen,k,s)
            for actor,color in (('human',BLUE),('jeff',ORANGE)):
                target=k.selected_station(actor)
                if target in k.equipment:
                    tx,ty=self.point(k.equipment[target]['cell'])
                    pg.draw.rect(screen,color,(tx-TILE//2,ty-TILE//2,TILE-1,TILE-1),2)
                chef=s['chefs'][actor]; px,py=self.point(chef['position'])
                self.text('P1' if actor=='human' else 'P2',px-9,py+5,color,True)
                if chef.get('working'): self.text(f"{chef['work_remaining']:.1f}s",px-15,py+22,color,True)
                if chef.get('holding'):
                    bx,by=px,py-round(104*TILE/64)
                    pg.draw.rect(screen,TEXT,(bx-19,by-17,38,35))
                    pg.draw.rect(screen,(253,243,225),(bx-17,by-15,34,31))
                    pg.draw.rect(screen,TEXT,(bx-4,by+17,8,4))
                    self.sprite_painter.held_icon(screen,chef['holding'],(bx,by),27)
        else:
            for y in range(k.height):
                for x in range(k.width):
                    rect = pg.Rect(OX + x*TILE, OY + y*TILE, TILE-2, TILE-2)
                    wall = (x, y) in k.walls
                    pg.draw.rect(screen, (47, 57, 68) if wall else ((65, 79, 81) if (x+y)%2 else (70, 85, 87)), rect, border_radius=4)
            for key, e in s['map']['equipment'].items():
                station = s['stations'].get(key, {})
                typ = e.get('type', '')
                color = (94, 108, 124)
                if 'source' in typ: color = (65, 117, 132)
                if station.get('stove'): color = (130, 98, 76)
                if 'sink' in typ: color = (65, 112, 160)
                if 'serv' in typ: color = (70, 137, 91)
                if station.get('fire'): color = (213, 71, 43)
                for cell in e.get('cells', [e['cell']]):
                    x, y = self.point(cell)
                    pg.draw.rect(screen, color, (x-TILE//2+2, y-TILE//2+2, TILE-6, TILE-6), border_radius=7)
                x, y = self.point(e['cell'])
                label = e.get('item') or {'extinguisher':'exting.', 'counter_corner':'corner'}.get(key,key.replace('counter','c'))
                self.text(label[:11], x-TILE//2+4, y-TILE//2+5, TEXT, True)
                self.item(station.get('food'), (x, y+7))
                if station.get('pot_id') and not station.get('food'):
                    self.item({'stage': 'pot'}, (x, y+7))
                raw = k.stations.get(key)
                f = raw.food if raw else None
                if f and f.stage in ('raw','cooking','ready','burnt','chopped'):
                    stage_name = f.stage.upper()[:5]
                    self.text(stage_name,x-19,y+18,ORANGE if f.stage=='burnt' else TEXT,True)
                    if station.get('heating'):
                        ready = k.rules.heat_thresholds(f.ingredient)[0]
                        pg.draw.line(screen, ORANGE, (x-20,y+28),(x-20+round(40*min(1,f.heated/max(.01,ready))),y+28),3)
            for item in s['ground']:
                self.item(item['food'], self.point(item['position']))
            for p in s['projectiles']:
                progress = min(1, max(0, (k.time-p['started'])/max(.001, p['lands_at']-p['started'])))
                point = [p['from'][i]+(p['to'][i]-p['from'][i])*progress for i in (0,1)]
                self.item(p, self.point(point))
            for actor, color, label in (('human', BLUE, 'P1'), ('jeff', ORANGE, 'P2')):
                chef = s['chefs'][actor]
                x, y = self.point(chef['position'])
                target = k.selected_station(actor)
                if target in k.equipment:
                    tx, ty = self.point(k.equipment[target]['cell'])
                    pg.draw.rect(screen, color, (tx-TILE//2,ty-TILE//2,TILE-1,TILE-1), 3, border_radius=5)
                pg.draw.circle(screen, color, (x,y), 17)
                pg.draw.circle(screen, (249,247,236), (x,y-10), 12)
                ax, ay = k.aim_of(actor)
                pg.draw.line(screen, color, (x,y), (x+round(ax*30),y+round(ay*30)), 4)
                self.text(label, x-10,y-8,(20,27,36),True)
                self.item(chef['holding'],(x+18,y-22))
                if chef['working']:
                    self.text(f"{chef['work_remaining']:.1f}s",x-15,y+22,color,True)
        x, y = self.side, 20
        self.text('ORDERS',x,y,BLUE)
        y += 32
        for order in s['orders']:
            if order['status'] != 'pending': continue
            remaining = max(0,order['deadline']-k.time)
            if self.sprite_painter: self.sprite_painter.dish_icon(screen,order['dish'],(x+16,y+10),28)
            self.text(f"{order['id']}  {order['dish']}  {remaining:.1f}s",x+(38 if self.sprite_painter else 0),y,ORANGE if remaining<15 else TEXT)
            pg.draw.rect(screen,(52,65,75),(x,y+22,300,5))
            pg.draw.rect(screen,ORANGE,(x,y+22,round(300*min(1,remaining/order['patience'])),5))
            y += 43
        y = max(y+12, 285)
        self.text('RECIPES',x,y,BLUE); y += 28
        for dish in s['dishes']:
            y = self.wrap(f"{dish['id']} ${dish['price']}: " + ', '.join(c['item']+' '+c['state'] for c in dish['components']),x,y)
        y += 12
        for actor, color in (('human',BLUE),('jeff',ORANGE)):
            chef = s['chefs'][actor]
            self.text(('P1 / Human' if actor=='human' else 'P2 / Jeff'), x,y,color); y += 24
            y = self.wrap('Holding: '+(food_text(chef['holding']) or 'empty'),x,y)
            y = self.wrap('Task: '+chef['task'],x,y)
            for mode, prefix in (('hands','Hands'),('use','Use')):
                target, action = k.facing_interaction(actor,mode)
                y = self.wrap(prefix+': '+(english_data(action.label) if action else 'no action'),x,y,color=color)
            y += 8
        by = OY + k.height*TILE + 12
        self.text('P1: WASD move | Space hands | E use / throw | Q throw | Left Shift dash | X stop',20,by,BLUE,True)
        self.text('P2: Arrows move | Enter hands | Right Ctrl use / throw | Right Shift throw | / dash | . stop',20,by+23,ORANGE,True)
        self.text('P pause | Esc save & quit | Face a station to see actions. Work continues until you move away.',20,by+46,MUTED,True)
        self.text('Chop beef on board > load pan > wait for ready > plate > serve. Green food is ready; do not burn it.',20,by+69,MUTED,True)
        events = english_data(k.events[-2:])
        for index, event in enumerate(events):
            self.wrap(event.get('message',event.get('kind','')),20,by+94+index*18,self.board_width)
        pg.display.flip()


def handle_events(events, keyboard, game, paused=False):
    active = True
    clear_clock = False
    for event in events:
        if event.type == pg.QUIT:
            active = False
        elif event.type == pg.KEYDOWN:
            key = pg.key.name(event.key)
            if key == 'escape':
                active = False
            elif key == 'p' and not getattr(event,'repeat',False):
                paused = not paused
                evidence = keyboard.clear(); game.clear_input(); clear_clock = True
                if hasattr(game,'note_control'): game.note_control({'operation':'pause' if paused else 'resume','keyboard':evidence})
            elif not paused:
                keyboard.press(key)
        elif event.type == pg.KEYUP:
            keyboard.release(pg.key.name(event.key))
        elif event.type == pg.WINDOWFOCUSLOST:
            evidence = keyboard.clear(); game.clear_input(); paused = True; clear_clock = True
            if hasattr(game,'note_control'): game.note_control({'operation':'focus_lost','keyboard':evidence})
    return active, paused, clear_clock


def run(game, fps=60, demo=False, session=None, art_mode='original'):
    pg.init()
    renderer = Renderer(game,art_mode)
    clock, keyboard = pg.time.Clock(), Keyboard()
    pacer = RealtimeClock(game.hz, speed=game.runtime.get('game_speed', 1.0))
    session = session or DecisionSession(game,on_decision=drive_reference if demo else None)
    paused = False
    active = True
    try:
        while active:
            elapsed = clock.tick(fps)/1000
            active, paused, clear_clock = handle_events(pg.event.get(), keyboard, session, paused)
            if clear_clock:
                dropped = pacer.reset_backlog()
                session.note_control({'operation':'clock_reset','discarded_backlog_seconds':dropped,
                                      'backlog_timebase':'simulation_seconds'})
            if not paused and not game.k.ended and active:
                pacer.add(elapsed if not clear_clock else 0)
                # Retain catch-up backlog, but render/event-pump at least every ten ticks.
                for _ in range(10):
                    if not pacer.pop_tick(): break
                    actions = {} if demo else keyboard.sample()
                    session.advance_tick(actions,evidence={'keyboard':keyboard.last_evidence,
                                                          'active_wall_seconds':pacer.active_wall_seconds,
                                                          'game_speed':pacer.speed})
                    if game.k.ended: break
            renderer.draw(paused,demo)
    finally:
        keyboard.clear()
        game.clear_input()
        pg.quit()
