"""Real SDL window render/event check. Synthetic events are labelled as such.

Does not claim physical keyboard verification. No dummy SDL driver is used.
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pygame as pg
from native.controls import Keyboard
from native.game import LocalGame
from native.window import Renderer, handle_events


def main():
    pg.init()
    if pg.display.get_driver() == 'dummy':
        raise RuntimeError('This verification requires a real window, not dummy SDL')
    game = LocalGame()
    keyboard = Keyboard()
    renderer = Renderer(game)
    try:
        renderer.draw(False,False)
        start = game.k.positions['human']
        handle_events([pg.event.Event(pg.KEYDOWN,key=pg.K_w),
                       pg.event.Event(pg.KEYDOWN,key=pg.K_d),
                       pg.event.Event(pg.KEYDOWN,key=pg.K_DOWN)],keyboard,game)
        actions = keyboard.sample()
        assert actions['human']['move'] == [1,-1]
        assert actions['jeff']['move'] == [0,1]
        game.step(actions)
        assert game.k.positions['human'] != start
        renderer.draw(False,False)
        handle_events([pg.event.Event(pg.KEYUP,key=pg.K_w),pg.event.Event(pg.KEYUP,key=pg.K_d)],keyboard,game)
        game.step(keyboard.sample())
        assert game.k.manual['human'] == (0,0)
        active, paused, cleared = handle_events([pg.event.Event(pg.WINDOWFOCUSLOST)],keyboard,game)
        assert active and paused and cleared
        assert all(v == (0,0) for v in game.k.manual.values())
        assert not keyboard.held and not keyboard.edges
        renderer.draw(paused,False)
        print('PASS: real SDL driver='+pg.display.get_driver()+', window rendered, synthetic two-player keydown/keyup/diagonal/focus-loss events verified')
    finally:
        game.close('window_check')
        pg.quit()


if __name__ == '__main__':
    main()
