"""Static asset/scene checks only: no SDL, image decoding, windows or GPU."""
from copy import copy, deepcopy
import hashlib
import sys
import unittest
from native.art import AtlasCatalog, SceneBuilder, chef_key, cabinet_key
from native.game import LocalGame


class OriginalArtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.catalog=AtlasCatalog()

    def test_catalog_exact_order_override_and_rectangles(self):
        c=self.catalog
        self.assertEqual(len(c.atlases),13); self.assertEqual(len(c.frames),627)
        self.assertEqual(c.frames['characters/player/down/idle_0'].atlas.parent.name,'chefs-v2')
        self.assertEqual(c.frames['modular/top_stove'].atlas.parent.name,'grid-foundation-v1')
        for key,frame in c.frames.items():
            x,y,w,h=frame.rect
            self.assertTrue(all(isinstance(v,(int,float)) for v in frame.rect))
            self.assertGreater(w*h,0)
            ax,ay=frame.anchor
            self.assertTrue(0<=ax<=1 and 0<=ay<=1,key)
        self.assertNotIn('pygame',sys.modules)

    def test_map_layout_depth_and_original_frame_coverage(self):
        for level in ('level-1','level-2','level-3','level-4'):
            g=LocalGame(level)
            b=SceneBuilder(self.catalog); scene=b.build(g.k)
            self.assertGreater(len(scene),200)
            self.assertFalse(b.missing,(level,b.missing))
            self.assertEqual([q['depth'] for q in scene],sorted(q['depth'] for q in scene))
            keys={q['key'] for q in scene}
            self.assertIn('modular/wall_cap',keys)
            self.assertTrue(any('sink_unit' in key for key in keys))
            self.assertTrue(any('characters/player' in key for key in keys))
            self.assertTrue(any('characters/jeff' in key for key in keys))
            g.close()

    def test_directions_walking_chopping_and_thrown_frames(self):
        for actor in ('human','jeff'):
            for facing in ('up','down','left','right'):
                chef={'facing':facing,'manual_moving':False}
                self.assertTrue(self.catalog.has(chef_key(self.catalog,actor,chef,0)))
                chef['manual_moving']=True
                for n in range(8): self.assertIn('walk_',chef_key(self.catalog,actor,chef,n/12))
                chef.update(working=True,action_kind='chop')
                for t in (0,.09,.15,.23):
                    self.assertTrue(self.catalog.has(chef_key(self.catalog,actor,chef,t)))
                key=chef_key(self.catalog,actor,chef,0,throwing=(1,-1))
                self.assertIn('up_right/release',key); self.assertTrue(self.catalog.has(key))

    def test_key_states_food_pan_dish_fire_and_held_depth(self):
        g=LocalGame(level='level-3'); s=g.k.snapshot(); b=SceneBuilder(self.catalog)
        s['stations']['p1'].update(food={'stage':'ready','ingredient':'beef'},heating=True,fire=True)
        s['chefs']['human'].update(holding={'stage':'clean_plate'},facing='up')
        scene=b.build(g.k,s)
        keys={q['key'] for q in scene}
        self.assertIn('modular/pan_vertical/beef/ready',keys)
        self.assertTrue(any(key.startswith('vfx/fire_') for key in keys))
        self.assertTrue(any(key.startswith('vfx/steam_') for key in keys))
        body=next(q for q in scene if q['key']=='characters/player/up/idle_0')
        plate=next(q for q in scene if q['key']=='objects/clean_plate')
        self.assertLess(plate['depth'],body['depth'])
        self.assertFalse(b.missing)
        for components in (['bread'],['bread','beef','lettuce'],['bread','beef','lettuce','tomato']):
            b.commands=[]; b.snapshot=s
            b.item({'stage':'assembled','plate_id':'test','ingredient':'dish','components':components},(50,50),1)
            self.assertTrue(b.commands)
            self.assertFalse(b.missing)
        g.close()

    def test_chop_knife_grip_and_up_occlusion(self):
        g=LocalGame(); snapshot=g.k.snapshot(); b=SceneBuilder(self.catalog)
        for facing in ('down','left','right'):
            chef=snapshot['chefs']['human']
            chef.update(facing=facing,working=True,action_kind='chop',target='b1')
            commands=b.build(g.k,snapshot)
            body=next(q for q in commands if q['key'].startswith('knifeless/characters/player/'))
            knife=next(q for q in commands if q['key'].startswith('knife/v1/arc/'))
            pose=self.catalog.frames[body['key']].meta
            self.assertEqual(knife['key'],pose['knife'])
            self.assertTrue(all(0<=a<=1 for a in knife['anchor']))
        snapshot['chefs']['human']['facing']='up'
        visual=copy(g.k); visual.time=.15  # the source hides the up-view knife at the strike phase
        commands=b.build(visual,snapshot)
        pose=next(q for q in commands if q['key'].startswith('characters/player/up/chop_'))
        self.assertTrue(self.catalog.frames[pose['key']].meta['knife_hidden'])
        self.assertFalse(any(q['key'].startswith('knife/v1/arc/') for q in commands))
        g.close()

    def test_wash_effect_uses_original_frames(self):
        g=LocalGame(); snapshot=g.k.snapshot(); b=SceneBuilder(self.catalog)
        snapshot['chefs']['human'].update(working=True,action_kind='wash',target=g.k.sink)
        commands=b.build(g.k,snapshot)
        self.assertTrue(any(q['key'].startswith('vfx/splash_') for q in commands))
        g.close()

    def test_read_only_assets_and_manifest_fingerprint(self):
        p=self.catalog.frames['characters/jeff/down/idle_0'].atlas
        before=hashlib.sha256(p.read_bytes()).hexdigest()
        other=AtlasCatalog()
        self.assertEqual(other.fingerprint(),self.catalog.fingerprint())
        self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),before)


if __name__=='__main__': unittest.main()
