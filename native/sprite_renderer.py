"""Execute original-atlas scene commands on software Pygame surfaces.

Imported only by an explicitly opened GUI. Tests can inspect the entire scene
plan in native.art without importing this module or initializing SDL.
"""
import pygame as pg
from .art import AtlasCatalog, SceneBuilder


class SpritePainter:
    def __init__(self,tile,origin):
        self.catalog=AtlasCatalog()
        self.builder=SceneBuilder(self.catalog,tile,origin)
        self.atlases={}
        self.crops={}
        self.scaled={}

    def sprite(self,key,crop=None):
        entry=self.catalog.frames[key]
        cache=(key,tuple(crop) if crop else None)
        if cache not in self.crops:
            atlas=str(entry.atlas)
            if atlas not in self.atlases:
                self.atlases[atlas]=pg.image.load(atlas).convert_alpha()
            image=self.atlases[atlas].subsurface(entry.rect).copy()
            if crop: image=image.subsurface(tuple(round(v) for v in crop)).copy()
            self.crops[cache]=image
        return self.crops[cache]

    def draw_command(self,screen,command):
        frame=self.catalog.frames[command['key']]
        image=self.sprite(command['key'],command['crop'])
        w,h=image.get_size(); scale=command['scale']; anchor=command['anchor']
        if anchor=='alpha_center':
            left,top,right,bottom=frame.meta.get('alpha_bbox',[0,0,w,h])
            fit=command['fit'] or (w*scale,h*scale)
            scale=min(fit[0]/max(1,right-left),fit[1]/max(1,bottom-top))
            ax,ay=(left+right)/2,(top+bottom)/2
        else:
            if command['fit']: scale=min(command['fit'][0]/w,command['fit'][1]/h)
            ax,ay=anchor or frame.anchor
            ax*=w; ay*=h
        width,height=max(1,round(w*scale)),max(1,round(h*scale))
        cache=(command['key'],tuple(command['crop']) if command['crop'] else None,width,height,command['flip'])
        if cache not in self.scaled:
            resized=pg.transform.scale(image,(width,height))
            if any(command['flip']): resized=pg.transform.flip(resized,*command['flip'])
            self.scaled[cache]=resized
        x,y=command['position']
        screen.blit(self.scaled[cache],(round(x-ax*scale),round(y-ay*scale)))

    def draw(self,screen,k,snapshot):
        for command in self.builder.build(k,snapshot): self.draw_command(screen,command)

    def held_icon(self,screen,food,position,size=25):
        # Reuse item/plating selection, without mutating the world command list.
        saved=self.builder.commands
        try:
            self.builder.commands=[]
            self.builder.item(food,position,0,size)
            for command in self.builder.commands: self.draw_command(screen,command)
        finally:
            self.builder.commands=saved

    def dish_icon(self,screen,dish,position,size=30):
        key=self.catalog.choose(f'dishes/{dish}/ready',f'food/{dish}_ready')
        if key:
            self.draw_command(screen,{'key':key,'position':position,'scale':1,'fit':(size,size),
                                      'anchor':'alpha_center','flip':(False,False),'crop':None})
