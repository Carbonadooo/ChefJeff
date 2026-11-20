"""One command for native play, deterministic headless runs and replay checks."""
import sys

# The upstream modules read UTF-8 content with Path.read_text()'s locale default.
# Scope this compatibility fix to our child process; never change OS settings.
if __name__ == '__main__' and not sys.flags.utf8_mode:
    import subprocess
    raise SystemExit(subprocess.call([sys.executable, '-X', 'utf8', __file__, *sys.argv[1:]]))

import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
from native.game import LocalGame, replay
from native.timing import DecisionSession, decision_config, game_speed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--level', choices=[f'level-{n}' for n in range(1, 5)], default='level-1')
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--hz', type=int, default=20, help='Legacy adapter tick rate; engine substeps remain <=50 ms')
    parser.add_argument('--decision-seconds', default='0.1', help='Agent/training decision interval, e.g. 0.1 or 1; rounded up to an adapter tick')
    parser.add_argument('--speed', type=game_speed, default=1.0, help='GUI game speed: 1 normal, 0.5 half, 0.25 quarter; game-time ticks stay unchanged')
    parser.add_argument('--fps', type=int, default=60)
    parser.add_argument('--art',choices=('original','simple'),default='original',help='Original read-only atlases or previous geometric fallback')
    parser.add_argument('--record', type=Path, help='New JSONL file (never overwritten)')
    parser.add_argument('--no-record', action='store_true')
    parser.add_argument('--replay', type=Path, help='Verify a local recording without opening a window')
    parser.add_argument('--allow-code-change', action='store_true')
    parser.add_argument('--headless', action='store_true')
    duration = parser.add_mutually_exclusive_group()
    duration.add_argument('--ticks', type=int, default=3601, help='Headless adapter ticks (legacy behavior)')
    duration.add_argument('--steps', type=int, help='Headless decision steps instead of adapter ticks')
    parser.add_argument('--demo', action='store_true', help='Run the existing scripted reference pair; not an AI baseline')
    args = parser.parse_args(argv)
    if args.replay:
        print(json.dumps(replay(args.replay, not args.allow_code_change), indent=2))
        return 0
    if not 1 <= args.hz <= 240 or not 1 <= args.fps <= 240 or args.ticks < 0 or (args.steps is not None and args.steps < 0):
        parser.error('fps must be 1..240 and ticks must be nonnegative')
    if args.headless and args.speed != 1.0:
        parser.error('--speed controls GUI wall-clock pacing; headless runs are unpaced')
    try:
        timing = decision_config(args.decision_seconds,args.hz)
    except (ValueError,ZeroDivisionError):
        parser.error('decision seconds must be finite, positive and <=86400; hz must be positive')
    print(f"Timing: decision={timing['decision_seconds']:g}s ({timing['decision_ticks']} ticks); adapter={1/args.hz:g}s; engine substeps<=0.05s; render={args.fps} FPS",flush=True)
    print(f'Game speed: {args.speed:g}x; tick and decision intervals use game seconds.', flush=True)
    if timing['requested_decision_seconds'] != timing['decision_seconds']:
        print(f"Requested {args.decision_seconds}s rounded up to {timing['decision_seconds']:g}s at {args.hz} Hz.",flush=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    path = None if args.no_record else args.record or Path(__file__).resolve().parent / 'native-recordings' / f'{stamp}.jsonl'
    game = LocalGame(args.level, args.seed, args.hz, record=path,decision_seconds=args.decision_seconds,
                     runtime={'render_fps':args.fps,'presentation':args.art,
                              'game_speed':args.speed,
                              'speed_timebase':'simulation_seconds_per_wall_second',
                              'decision_timebase':'simulation_seconds',
                              'pacing':'offline_unpaced' if args.headless else 'monotonic_wall_clock'})
    from native.policy import drive_reference
    session = DecisionSession(game,on_decision=drive_reference if args.demo else None)
    print(f'Presentation: {args.art} (GUI only); human inputs remain sampled every adapter tick.',flush=True)
    if path:
        print(f'Recording: {path.resolve()}', flush=True)
    try:
        if args.headless:
            for _ in range(args.steps if args.steps is not None else args.ticks):
                if game.k.ended: break
                if args.steps is not None:
                    session.step()
                else:
                    session.advance_tick()
            print(json.dumps({'tick':game.tick,'decisions':session.index,'time':game.k.time,
                              'score':game.k.money,'served':game.k.served}))
        else:
            from native.window import run
            run(game, args.fps, args.demo, session=session,art_mode=args.art)
    finally:
        session.close('round_complete' if game.k.ended else 'headless_limit' if args.headless else 'window_closed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
