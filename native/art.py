"""Original Cocos atlas catalog and scene planning. Pure Python; no GUI imports.

Frame order/prefixes mirror LevelOneArt.load. PNG rectangles use a top-left
origin; Cocos anchors use a bottom-left origin. Assets are only read in place.
"""
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import struct

ART_ROOT = Path(__file__).resolve().parents[1] / 'cocos-kitchen/assets/resources/art'
ATLAS_ORDER = (
    ('level1',''),('level1-modular','modular/'),('kitchen-modules-v2','modular/'),
    ('serving-side-v1','modular/'),('burger-food','food/'),('grid-foundation-v1',''),
    ('action-feedback-v1',''),('chefs-v2',''),('knife-v1',''),('knife-arc-v1',''),
    ('trash-directions-v1',''),('throw-diagonal-v1',''),('ingredient-pack-v1',''))


@dataclass(frozen=True)
class Frame:
    key: str
    atlas: Path
    rect: tuple
    meta: dict

    @property
    def size(self): return self.rect[2:]

    @property
    def anchor(self):
        x,y=self.meta.get('anchor',[.5,.5])
        return x,1-y  # SDL canvas is top-left, Cocos anchor is bottom-left


class AtlasCatalog:
    def __init__(self, root=ART_ROOT):
        self.root=Path(root)
        self.frames={}
        self.atlases={}
        self.manifest_hashes={}
        for name,prefix in ATLAS_ORDER:
            folder=self.root/name
            raw=(folder/'manifest.json').read_bytes()
            manifest=json.loads(raw)
            atlas=folder/'atlas.png'
            with atlas.open('rb') as stream:
                header=stream.read(24)
            if header[:8]!=b'\x89PNG\r\n\x1a\n': raise ValueError(f'invalid atlas PNG: {name}')
            width,height=struct.unpack('>II',header[16:24])
            self.atlases[name]={'path':atlas,'size':(width,height)}
            self.manifest_hashes[name]=hashlib.sha256(raw).hexdigest()
            for key,meta in manifest['frames'].items():
                x,y,w,h=meta['rect']
                if min(x,y)<0 or min(w,h)<=0 or x+w>width or y+h>height:
                    raise ValueError(f'frame outside atlas: {name}/{key}')
                full=prefix+key
                self.frames[full]=Frame(full,atlas,(x,y,w,h),meta)

    def has(self,key): return key in self.frames

    def choose(self,*keys): return next((key for key in keys if self.has(key)),None)

    def fingerprint(self):
        return hashlib.sha256(json.dumps(self.manifest_hashes,sort_keys=True).encode()).hexdigest()


def cabinet_key(map_data,station):
    e=map_data['equipment'][station]; x,y=e['cell']
    below=(x,y+1)
    covered=below in {tuple(p) for p in map_data['walls']} or any(
        below in [tuple(c) for c in q.get('cells',[q['cell']])] for q in map_data['equipment'].values())
    axis=map_data.get('presentation',{}).get('station_views',{}).get(station,{}).get('run_axis','horizontal')
    return 'modular/counter_east' if axis=='vertical' and covered else 'modular/counter_south'


def chef_key(catalog,actor,chef,time,throwing=None):
    kind='player' if actor=='human' else 'jeff'; facing=chef['facing']
    if throwing:
        dx,dy=throwing
        if abs(dx)>.3 and abs(dy)>.3:
            diagonal=('up' if dy<0 else 'down')+'_'+('left' if dx<0 else 'right')
            key=f'throw/{kind}/{diagonal}/release'
            if catalog.has(key): return key
        key=f'knifeless/characters/{kind}/{facing}/chop_2'
        if catalog.has(key): return key
    if chef.get('working') and chef.get('action_kind')=='chop':
        beat=(time/.27+(0 if actor=='human' else .27))%1
        phase=0 if beat<.3 else 1 if beat<.45 else 2 if beat<.75 else 3
        key=f'characters/{kind}/{facing}/chop_{phase}'
        pose=catalog.frames[key].meta
        knifeless='knifeless/'+key
        if pose.get('grip') and pose.get('knife') and catalog.has(knifeless) and catalog.has(pose['knife']):
            return knifeless
        return key
    walking=chef.get('manual_moving') or (chef.get('job_id') is not None and not chef.get('working') and chef.get('travel_remaining',0)>0)
    return f'characters/{kind}/{facing}/'+(f'walk_{int(time*12)%8}' if walking else 'idle_0')


class SceneBuilder:
    """Build sprite draw commands with original anchor/asset/depth contracts.

    Commands are inspectable without SDL. SpritePainter executes them only when
    the user explicitly opens a native window.
    """
    def __init__(self,catalog,tile=59,origin=(20,126)):
        self.catalog=catalog; self.tile=tile; self.origin=origin
        self.commands=[]
        self.missing=set()

    def point(self,p):
        return (self.origin[0]+(p[0]+.5)*self.tile,self.origin[1]+(p[1]+.5)*self.tile)

    def put(self,key,position,depth,scale=None,fit=None,anchor=None,flip=(False,False),crop=None):
        if not self.catalog.has(key):
            self.missing.add(key); return False
        self.commands.append({'key':key,'position':tuple(position),'depth':depth,
                              'scale':self.tile/64 if scale is None else scale,'fit':fit,
                              'anchor':anchor,'flip':flip,'crop':crop})
        return True

    def item(self,food,pos,depth,size=None,side='south'):
        if not food: return
        c=self.catalog; size=size or self.tile*.65
        stage=food['stage']
        if stage=='pot':
            vessel=food.get('vessel') or 'pot'
            direction={'south':'vertical','east':'horizontal','west':'west','north':'north'}.get(side,'vertical')
            empty=c.choose(f'modular/{vessel}_{direction}',f'objects/{vessel}','objects/pot')
            contents=food.get('contents')
            filled=empty+f"/{contents['ingredient']}/{contents['stage']}" if empty and contents else ''
            key=filled if c.has(filled) else empty
            if key: self.put(key,pos,depth,fit=(size,size),anchor='alpha_center')
            if contents and key!=filled:
                self.item(contents,(pos[0],pos[1]-size*.1),depth+.001,size*.48)
            return
        if stage in ('clean_plate','dirty_plate','extinguisher'):
            self.put('objects/'+stage,pos,depth,fit=(size,size),anchor='alpha_center'); return
        components=food.get('components') or [food.get('ingredient','beef')]
        dish=food.get('dish') or ('burger' if set(components)=={'bread','beef','lettuce','tomato'} else 'steak' if components==['beef'] else None)
        if food.get('plate_id'):
            key=c.choose(f'dishes/{dish}/{stage}',f'food/{dish}_ready')
            if key:
                self.put(key,pos,depth,fit=(size,size),anchor='alpha_center'); return
            self.put('objects/clean_plate',pos,depth,fit=(size,size),anchor='alpha_center')
            target=next((d for d in self.snapshot['dishes'] if set(components)<={p['item'] for p in d['components']}),{})
            layers=[p for p in target.get('plating',[]) if p['item'] in components]
            if layers:
                for i,layer in enumerate(layers):
                    self.put('feedback/'+layer['layer'],(pos[0],pos[1]+size*.07-i*size*.065),depth+.001*(i+1),fit=(size*.78,size*.43),anchor='alpha_center')
                return
        ingredient=food.get('ingredient','beef')
        key=c.choose(f'food/{ingredient}_{stage}',f'ingredients/{ingredient}/{stage}',
                     f"ingredients/{ingredient}/{'prepared' if stage=='chopped' else stage}")
        if key: self.put(key,pos,depth+.01,fit=(size*.72,size*.72),anchor='alpha_center')
        else: self.missing.add(f'food/{ingredient}_{stage}')

    def build(self,k,snapshot=None):
        s=snapshot or k.snapshot(); self.snapshot=s; self.commands=[]; self.missing=set()
        tile=self.tile; scale=tile/64; m=s['map']; walls={tuple(p) for p in m['walls']}
        equipment=m['equipment']
        for y in range(m['height']):
            for x in range(m['width']):
                key=f'modular/floor_{(x-1)%4}_{(y-1)%4}'
                self.put(key,self.point((x,y)),-1000,fit=(tile,tile),anchor='alpha_center')
        for x,y in walls:
            pos=self.point((x,y)); depth=y-.495
            self.put('modular/wall_cap',pos,depth,fit=(tile,tile),anchor='alpha_center')
            if y==0 and (x,y+1) not in walls:
                self.put('modular/wall_face',(pos[0],pos[1]-tile/2),depth+.001,
                         scale=scale,anchor=(.5,0),crop=(0,0,64,44))
        for decor in m.get('presentation',{}).get('decorations',[]):
            x,y=self.point(decor['cell'])
            self.put('modular/'+decor['asset'],(x,y),decor['cell'][1]-.45,
                     fit=(tile*.65,tile*.44),anchor='alpha_center')
        sink_unit=None
        if k.sink in equipment and k.dryer in equipment:
            sx,sy=equipment[k.sink]['cell']; rx,ry=equipment[k.dryer]['cell']
            dx,dy=rx-sx,ry-sy
            if abs(dx)+abs(dy)==1:
                side='east' if dx>0 else 'west' if dx<0 else 'south' if dy>0 else 'north'
                unit_key='modular/sink_unit_'+side
                if self.catalog.has(unit_key):
                    sink_unit=(unit_key,self.point(((sx+rx)/2,(sy+ry)/2)),side)
        for key,e in equipment.items():
            station=s['stations'].get(key,{})
            x,y=self.point(e['cell']); row=e['cell'][1]; depth=row-.495
            for cell in e.get('cells',[e['cell']]):
                px,py=self.point(cell)
                self.put(cabinet_key(m,key),(px,py+22*scale),cell[1]-.495)
            typ=e.get('type',''); axis=m.get('presentation',{}).get('station_views',{}).get(key,{}).get('device_axis','horizontal')
            if typ=='ingredient_source':
                self.put('modular/source_'+e.get('item',key),(x,y),depth+.005,fit=(tile*.53,tile*.5),anchor='alpha_center')
            elif station.get('stove'):
                self.put('modular/top_stove',(x,y),depth+.005)
            elif key in k.boards:
                self.put('modular/device_board_'+axis,(x,y),depth+.005)
            elif key==k.sink and not sink_unit:
                self.put('modular/device_sink_'+axis,(x,y),depth+.005)
            elif key==k.returns:
                self.put('modular/device_returns_'+axis,(x,y),depth+.005)
            elif typ=='serving_window':
                self.put('modular/serving_'+('east' if e.get('facing')=='east' else 'west'),(x,y),depth+.006)
            elif typ=='bin':
                self.put('modular/bin',(x,y),depth+.005)
            if sink_unit and key in (k.sink,k.dryer):
                unit_key,unit_center,side=sink_unit
                meta=self.catalog.frames[unit_key].meta; cw,ch=meta['canvasSize']
                across=side in ('east','west'); toward=side in ('east','south')
                rack=key==k.dryer; second=rack==toward
                crop=(cw/2 if second else 0,0,cw/2,ch) if across else (0,ch/2 if second else 0,cw,ch/2)
                center=(unit_center[0]+(crop[0]+crop[2]/2-cw/2)*scale,unit_center[1]+(crop[1]+crop[3]/2-ch/2)*scale)
                self.put(unit_key,center,depth+.006,anchor=(.5,.5),crop=crop)
                if rack:
                    count=len(k.stations[key].stack)+int(bool(station.get('food')))
                    for slot in meta.get('rackSlots',[])[:min(4,count)]:
                        self.put(meta['rackPlate'],(unit_center[0]+(slot[0]-cw/2)*scale,unit_center[1]+(slot[1]-ch/2)*scale),depth+.03)
                    self.put(meta['rackFront'],center,depth+.04,anchor=(.5,.5),crop=crop)
            food=station.get('food')
            if station.get('pot_id'):
                vessel=station.get('vessel') or 'pot'
                self.item({'stage':'pot','vessel':vessel,'contents':food},(x,y),depth+.02,tile*.78,e.get('facing','south'))
            elif not (sink_unit and key==k.dryer):
                self.item(food,(x,y),depth+.02,tile*(.45 if sink_unit and key==k.sink else .68))
            if station.get('heating'):
                frame=int(k.time*8)%7
                self.put(f'vfx/stove_flame_{frame}',(x,y+tile*.2),depth+.015,fit=(tile*.52,tile*.4),anchor='alpha_center')
                if food and food['stage']=='ready':
                    self.put(f'vfx/steam_{int(k.time*6)%7}',(x,y-tile*.4),depth+.05,fit=(tile*.55,tile*.7),anchor='alpha_center')
            if key==k.sink and any(c.get('working') and c.get('action_kind')=='wash' and c.get('target')==key for c in s['chefs'].values()):
                self.put(f'vfx/splash_{int(k.time*8)%7}',(x,y),depth+.06,fit=(tile*.68,tile*.68),anchor='alpha_center')
            if station.get('fire'):
                self.put(f'vfx/fire_{int(k.time*8)%7}',(x,y),depth+.08,fit=(tile,tile*1.25),anchor='alpha_center')
                self.put(f'vfx/smoke_{int(k.time*6)%7}',(x,y-tile*.5),depth+.09,fit=(tile*.7,tile*.8),anchor='alpha_center')
        for ground in s['ground']:
            pos=ground['position']; self.item(ground['food'],self.point(pos),round(pos[1])-1-.495+.012,tile*.62)
        for p in s['projectiles']:
            fraction=min(1,max(0,(k.time-p['started'])/max(.001,p['lands_at']-p['started'])))
            pos=[p['from'][i]+(p['to'][i]-p['from'][i])*fraction for i in (0,1)]
            px,py=self.point(pos); height=math.sin(fraction*math.pi)*tile*.65
            self.item(p,(px,py-height),pos[1]-.12+(.62 if height>=tile*.22 else 0),tile*.62)
        for actor,chef in s['chefs'].items():
            px,py=self.point(chef['position']); depth=chef['position'][1]
            if chef.get('sprint',{}).get('active_remaining',0)>0:
                self.put(f'modular/sprint_dust_{int(k.time*12)%4}',(px,py),depth-.02,fit=(tile*.75,tile*.45),anchor='alpha_center')
            target=equipment.get(chef.get('target'))
            if chef.get('working') and target and chef['facing'] in ('left','right'):
                depth=target['cell'][1]-.495+.015
            projectile=next((p for p in s['projectiles'] if p['actor']==actor and k.time-p['started']<.16),None)
            throwing=k.aim_of(actor) if projectile else None
            key=chef_key(self.catalog,actor,chef,k.time,throwing)
            held=chef.get('holding'); facing=chef['facing']
            meta=self.catalog.frames[key].meta
            grip=meta.get('grip_display',meta.get('grip')) if throwing else None
            if grip:
                ax,ay=meta.get('anchorPx',[34,83]); heldpos=(px+(grip[0]-ax)*scale,py+(grip[1]-ay)*scale)
            else:
                heldpos=(px+(-24 if facing=='left' else 24 if facing=='right' else 0)*scale,
                         py-(37 if facing=='up' else 24)*scale)
            behind=facing=='up' or '/up_' in key
            if held and behind: self.item(held,heldpos,depth-.001,tile*.47,{'up':'north','left':'west','right':'east'}.get(facing,'south'))
            self.put(key,(px,py),depth)
            if chef.get('working') and chef.get('action_kind')=='chop' and meta.get('grip') and meta.get('knife') and not meta.get('knife_hidden'):
                knife=meta['knife']; frame=self.catalog.frames[knife]
                ax,ay=meta.get('anchorPx',[34,83]); gx,gy=meta['grip']
                hand_key=key+'_hand'
                if not self.catalog.has(hand_key):
                    angle=math.radians(meta.get('grip_angle',0)); gx-=3*math.cos(angle); gy+=3*math.sin(angle)
                grip=(px+(gx-ax)*scale,py+(gy-ay)*scale)
                pivot=frame.meta['pivot']; width,height=frame.size
                knife_depth=(target['cell'][1] if target else chef['position'][1])-.11
                self.put(knife,grip,knife_depth,anchor=(pivot[0]/width,pivot[1]/height))
                if self.catalog.has(hand_key): self.put(hand_key,(px,py),knife_depth+.001)
            if held and not behind: self.item(held,heldpos,depth+.01,tile*.47,{'left':'west','right':'east'}.get(facing,'south'))
            hand=key+'_hand'
            if throwing and self.catalog.has(hand): self.put(hand,(px,py),depth+.02)
        self.commands.sort(key=lambda command:command['depth'])
        return self.commands
