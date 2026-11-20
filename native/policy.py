"""Optional engine regression demonstration using the repository's reference pair.

This is explicitly a scripted trace driver, not an AI teammate or benchmark.
For later agents use game.agent_port(actor) and environment.Agent.start/poll/close.
"""
from reference_policy import choose, choose_zoned, _cell_side


def drive_reference(game):
    k = game.k
    if k.ended:
        return
    for actor, role in (('human', 'cook'), ('jeff', 'assembler')):
        if k.split_floor:
            role = _cell_side(k, k.anchor(actor))
        action = (choose_zoned if k.split_floor else choose)(k, actor, role)
        if action:
            game.agent_port(actor).start(action)
