"""Swept oriented-box checks for declared interference parts of reused Easy assets.

Boxes follow the renderer's structural faces (small bolts/chamfers excluded).
The protected pairs are explicit in each task. This is not a whole-CAD solver.
"""
from math import sqrt
from motion_assembly import resolve, rotate


def dot(a,b): return sum(x*y for x,y in zip(a,b))
def sub(a,b): return [x-y for x,y in zip(a,b)]
def norm(a): return sqrt(dot(a,a))
def cross(a,b): return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]


def component_boxes(d, value):
    w,h,z=d['size']; k=d['ui']
    if k=='servo':
        return [('carriage',[(value-.5)*(w-.3),h*.38,0],[.30,max(.12,h*.55),z*.92]),
                ('plate',[(value-.5)*(w-.3),h*.38+max(.09,h*.36),0],[.22,.06,z*.72])]
    if k=='press':
        gland=h*.29-.026;plate=-h*.18-value*h*.72+.06
        return [('ram',[0,-h*.18-value*h*.72,0],[w*.62,.12,z*.62]),
                ('housing',[0,h/2,0],[w,h*.42,z]),
                ('cover',[0,h*.71+.012,0],[w*.94,.024,z*.94]),
                ('gland',[0,h*.29-.013,0],[.2,.026,.2]),
                ('rod',[0,(gland+plate)/2,0],[.14,max(.005,gland-plate),.14]),
                *[(side+'_column',[sign*(w/2-.06),-h*.23+.011,-z/2+.06],[.08,h*1.04-.022,.08]) for side,sign in [('left',-1),('right',1)]],
                *[(side+'_foot',[sign*(w/2-.06),-h*.75+.011,-z/2+.06],[.12,.022,.14]) for side,sign in [('left',-1),('right',1)]]]
    if k=='cylinder':
        exposed=z*.10+value*z*.75
        return [('push_plate',[0,0,-z*.475-value*z*.75],[.12,.14,.03]),
                ('rod',[0,0,-z*.375-exposed/2],[.036,.036,exposed])]
    if k=='door':
        half=w/2;shift=value*(half-.08)
        return [('left_panel',[-half/2-shift,0,0],[half,h-.12,z]),
                ('right_panel',[half/2+shift,0,0],[half,h-.12,z])]
    if k=='gripper':
        wide=d.get('visual_variant')=='wide-stroke';j=.32-value*.2 if wide else .15-value*.05
        return [('body',[0,0,0],[.74 if wide else .2,.16,.14]),
                ('left_jaw',[-j,-.16,0],[.06 if wide else .04,.2,.1]),
                ('right_jaw',[j,-.16,0],[.06 if wide else .04,.2,.1])]
    if k=='clamp':
        j=.13+(1-value)*.16
        return [('left_jaw',[-j,.035,0],[.10,.20,.30]),('right_jaw',[j,.035,0],[.10,.20,.30]),
                ('base',[0,-.115,0],[w+.62,.05,z*1.08]),
                ('housing',[0,.015,z/2+.11],[.34,.18,.18])]
    if k=='vertical_slide':
        return [('carriage',[0,-h*.27+value*h*.54,0],[w,.12,z*.70])]
    if k=='fork':
        return [('crossbar',[0,.04,.10-value*.18],[.34,.30,.12]),
                ('left_tine',[-.105,-.08,-z/2+.06-value*.18],[.055,.055,z]),
                ('right_tine',[.105,-.08,-z/2+.06-value*.18],[.055,.055,z])]
    if k in ('fixture','support_frame'):
        return [('solid',[0,0,0],d['size'])]
    return []


class InterferenceGeometry:
    def __init__(self,scene,pairs):
        self.scene=scene;self.pairs=pairs
        self.devices={d['id']:d for d in scene['devices']}
        self.needed={x for p in pairs for x in p['devices']}
        ancestry=set(self.needed)
        for name in list(self.needed):
            while self.devices[name].get('assembly_mount'):
                name=self.devices[name]['assembly_mount']['parent'];ancestry.add(name)
        self.pose_scene={'devices':[d for d in scene['devices'] if d['id'] in ancestry]}
        self.cached_key=None;self.cached_boxes=None
        self.checks=0

    def boxes(self,positions):
        key=tuple(sorted(positions.items()))
        if key==self.cached_key:return self.cached_boxes
        state={a.upper()+'_AXIS_A':v for a,v in positions.items()}
        poses=resolve(self.pose_scene,state)
        out={}
        for name in self.needed:
            d=self.devices[name];p=poses[name];q=p['quaternion'];axes=[rotate(q,e) for e in ([1,0,0],[0,1,0],[0,0,1])]
            items=[]
            for label,local,size in component_boxes(d,state.get(name,0)):
                c=[x+y for x,y in zip(p['pos'],rotate(q,local))]
                items.append(dict(name=name+'/'+label,c=c,axes=axes,half=[s/2 for s in size]))
            out[name]=items
        self.cached_key=key;self.cached_boxes=out
        return out

    @staticmethod
    def swept(a,b,a1,b1,margin=0,error=0):
        # SAT interval intersection on every fixed separating axis: detects a
        # pass-through even when both endpoint poses are disjoint.
        relative=sub(b['c'],a['c']);delta=sub(sub(b1['c'],a1['c']),relative)
        candidates=[*a['axes'],*b['axes'],*[cross(x,y) for x in a['axes'] for y in b['axes']]]
        enter,leave=0.0,1.0;gap=-float('inf')
        rotation_error=sum(norm(sub(u,v))*h for u,v,h in zip(a['axes'],a1['axes'],a['half']))
        rotation_error+=sum(norm(sub(u,v))*h for u,v,h in zip(b['axes'],b1['axes'],b['half']))
        for axis in candidates:
            length=norm(axis)
            if length<1e-8:continue
            axis=[x/length for x in axis]
            def radius(box):return sum(abs(dot(axis,u))*h for u,h in zip(box['axes'],box['half']))
            radius_a=max(radius(a),radius(a1));radius_b=max(radius(b),radius(b1))
            # Rotation bound of any vertex over this microstep.
            radius_sum=radius_a+radius_b+margin+error+rotation_error
            x=dot(axis,relative);v=dot(axis,delta)
            gap=max(gap,abs(x)-radius_a-radius_b)
            if abs(v)<1e-12:
                if abs(x)>radius_sum:return False,gap
                continue
            lo,hi=sorted(((-radius_sum-x)/v,(radius_sum-x)/v))
            enter=max(enter,lo);leave=min(leave,hi)
            if enter>leave:return False,gap
        return enter<=leave,gap

    def check(self,before,after,error):
        a=self.boxes(before);b=self.boxes(after);collisions=[];minimum=float('inf')
        for pair in self.pairs:
            left,right=pair['devices']; margin=pair.get('clearance_mm',0)/1000
            for i,l in enumerate(a[left]):
                for j,r in enumerate(a[right]):
                    self.checks+=1
                    hit,gap=self.swept(l,r,b[left][i],b[right][j],margin,error)
                    minimum=min(minimum,gap*1000)
                    if hit:collisions.append(dict(pair=pair['id'],components=[l['name'],r['name']],gap_mm=gap*1000))
        return collisions,minimum
