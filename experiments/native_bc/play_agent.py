"""Play the learned Level-1 cook as Jeff, or verify a rendered scripted-partner round."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from native.game import LocalGame, replay
from native.timing import DecisionSession, game_speed
from experiments.native_bc.policy import LearnedAgent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, default=Path(__file__).resolve().parent / 'checkpoints' / 'level1-tree-bc.json')
    parser.add_argument('--speed', type=game_speed, default=1.0)
    parser.add_argument('--seed', type=int, default=100)
    parser.add_argument('--scripted-partner', action='store_true', help='Replace the keyboard human with the original assembler script')
    parser.add_argument('--verify-render', type=Path, help='New output folder for an unpaced full round, PNGs and replay verification')
    args = parser.parse_args()
    if args.verify_render and not args.scripted_partner:
        parser.error('--verify-render needs --scripted-partner')
    folder = args.verify_render or ROOT / 'runs' / 'native_bc' / 'play'
    if args.verify_render:
        folder.mkdir(parents=True, exist_ok=False)
    else:
        folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    record = folder / f'{stamp}.jsonl'
    agent = LearnedAgent(args.checkpoint)
    game = LocalGame(level=agent.policy.model['level'], seed=args.seed, record=record,
                     decision_seconds=agent.policy.model['decision_seconds'], runtime={
                         'pacing': 'offline_unpaced_render_check' if args.verify_render else 'monotonic_wall_clock',
                         'game_speed': args.speed, 'render_fps': 60, 'presentation': 'original',
                         'controller': 'learned-tree-bc-jeff', 'partner': 'reference-assembler' if args.scripted_partner else 'keyboard-human',
                         'policy_sha256': hashlib.sha256(args.checkpoint.read_bytes()).hexdigest(),
                     })
    port = game.agent_port('jeff')
    agent.start(port)

    def decision(_):
        if args.scripted_partner:
            from reference_policy import choose
            action = choose(game.k, 'human', 'assembler')
            if action:
                game.agent_port('human').start(action)
        agent.poll(port, game.k.time)

    session = DecisionSession(game, on_decision=decision)
    print(f'Learned Jeff: {args.checkpoint.resolve()}', flush=True)
    print('Role: cook (prepare beef, cook and transfer to the assembly plate).', flush=True)
    print('Human: scripted assembler' if args.scripted_partner else 'Human: WASD/Space/E; assemble, serve and wash plates.', flush=True)
    print(f'Recording: {record}', flush=True)
    try:
        from native import window
        import pygame as pg
        if args.verify_render:
            pg.init()
            if pg.display.get_driver() != 'windows':
                raise RuntimeError('The render check requires the real Windows SDL driver')
            renderer = window.Renderer(game)
            served = False
            try:
                while not game.k.ended:
                    if any(event.type == pg.QUIT for event in pg.event.get()):
                        raise RuntimeError('Render verification canceled by window close')
                    session.advance_tick()
                    if game.tick % 20 == 0 or game.k.ended or (game.k.served and not served):
                        renderer.draw(False, False)
                    if game.k.served and not served:
                        pg.image.save(renderer.screen, str(folder / 'first-served.png'))
                        served = True
                pg.image.save(renderer.screen, str(folder / 'final.png'))
            finally:
                pg.quit()
        else:
            class HumanKeyboard(window.Keyboard):
                def sample(self):
                    actions = super().sample()
                    # Assign each chef one controller; P2 keyboard input cannot override Jeff.
                    actions.pop('jeff', None)
                    return {} if args.scripted_partner else actions

            with patch.object(window, 'Keyboard', HumanKeyboard):
                window.run(game, session=session)
    finally:
        agent.close()
        session.close('round_complete' if game.k.ended else 'window_closed')
    result = replay(record)
    if args.verify_render:
        (folder / 'report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
