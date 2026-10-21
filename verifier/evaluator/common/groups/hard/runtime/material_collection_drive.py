"""Finite fixed-stop collection conveyors. One drive acts on all products.

The local module selects a requested empty stop from the existing finite
collection contract. It does not admit work, process it, route it or acknowledge
results. Closed side fingers let a low-pressure belt slip below parked goods.
"""
import copy
from material_belt_contact import step_belt

def fixed_stops(p,name,ids,targets,centres,axis,speed,sign,cross_center=None,external_bodies=()):
 if not hasattr(p,'transport'):p.transport={};p.belt_distance={}
 cross='x' if axis=='z' else 'z';index=2 if axis=='z' else 0
 if not ids:
  p.transport[name]=dict(axis=axis,displacement=0.,bodies={},velocity=0.,distance=p.belt_distance.get(name,0.),stops=[],clamps=[]);return
 lengths={round(p.parts[i]['size'][index],8) for i in ids}
 line=p.parts[ids[0]][cross] if cross_center is None else cross_center;stops=[]
 for j,centre in enumerate(centres):
  # Two fixed fingers serve H11's two published product lengths. Their
  # separate faces preserve the same pickup centre without a floating stop.
  for length in sorted(lengths):
   half=length/2;face=centre+sign*half
   wanted=any(abs(t-centre)<1e-7 and abs(p.parts[i]['size'][index]-length)<1e-7 for i,t in targets.items())
   crossing=any(sign*(t-centre)>1e-8 and abs(p.parts[i][axis]-face)<=p.parts[i]['size'][index]/2+.020+1e-8 for i,t in targets.items())
   crossing=crossing or any(abs(q[axis]-face)<=q['size'][index]/2+.020+1e-8 for q in external_bodies)
   stops.append(dict(id=name+'_stop_'+str(j)+'_'+str(round(length*1000)),face=face,cross=line,half_width=.5,closed=wanted and not crossing))
 velocity=sign*speed if any(sign*(t-p.parts[i][axis])>1e-8 for i,t in targets.items()) else 0.
 d=step_belt(p.parts,ids,axis=axis,displacement=p.dt*velocity,stops=stops)
 p.belt_distance[name]=p.belt_distance.get(name,0.)+p.dt*velocity
 d.update(velocity=velocity,distance=p.belt_distance[name],stops=stops,clamps=[]);p.transport[name]=d

def collection(p,centres,sign):
 ids=list(p.accepted);targets={i:centres[j] for j,i in enumerate(p.accepted)}
 if p.exit_job:
  i=p.exit_job['id'];ids.append(i);targets[i]=p.exit_job['target']
 fixed_stops(p,'exit',ids,targets,centres,'z',.4,sign)

def source_queue(p):
 ids=[i for i,q in p.parts.items() if q['owner']=='source'];centres=[.45+.24*j for j in range(4)]
 if p.job:
  if not hasattr(p,'transport'):p.transport={};p.belt_distance={}
  p.transport['source']=dict(axis='z',displacement=0.,bodies={str(i):dict(delta=0.,clamp=None,stop=None,slip=0.) for i in ids},velocity=0.,distance=p.belt_distance.get('source',0.),stops=[],clamps=[])
 else:fixed_stops(p,'source',ids,{i:centres[j] for j,i in enumerate(ids)},centres,'z',.4,-1)

def install(cls):
 old=cls.physical
 cls.physical=lambda self:dict(old(self),transport=copy.deepcopy(getattr(self,'transport',{})))
 return cls
