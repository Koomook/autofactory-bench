"""A transverse pusher transfers off a stopped longitudinal deck onto an X belt."""
from material_hard_stations import Accumulator as Base,approach
from material_collection_drive import fixed_stops
class Accumulator(Base):
 def __init__(self,*args,**kw):
  super().__init__(*args,**kw);self.pusher=0.;self.pushing=None;self.collecting=None
 def clear(self):return super().clear() and self.collecting is None and self.pushing is None and self.pusher<1e-8
 def step(self):
  p=self.p;q=self.occupant();capacity=p.demands[self.name[-1]] if p.mode=='magazine' else 2 if self.name.endswith('a') else 1
  if q is None:self.arrived_at=None
  elif self.arrived_at is None:self.arrived_at=p.t
  elif p.t-self.arrived_at>=self.cycle:
   q['owner']='collecting_'+self.name;self.collecting=q['token'];self.pushing=q['token']
  ids=[i for i,q in p.parts.items() if q['owner'] in ('accepted','collecting_'+self.name) and q.get('exit')==self.name]
  # Positive X force is supplied by a real finger while the body still rests
  # on the stopped Z belt. Once across the seam the receiving belt drives it.
  crossing=self.pushing if self.pushing and p.parts[self.pushing]['x']<self.xyz[0]+.46-1e-8 else None
  if crossing:
   q=p.parts[crossing];q['x']=approach(q['x'],self.xyz[0]+.46,p.dt*self.speed);self.pusher=q['x']-self.xyz[0]
  else:
   self.pushing=None;self.pusher=approach(self.pusher,0.,p.dt*self.speed)
  belt_ids=[i for i in ids if i!=crossing];centres=[self.xyz[0]+.7+.5*k for k in range(capacity)]
  targets={i:self.xyz[0]+.7+.5*(capacity-1-p.parts[i].get('rank',0)) for i in belt_ids}
  fixed_stops(p,self.name,belt_ids,targets,centres,'x',self.speed,1)
  p.transport[self.name]['pusher']=dict(offset=self.pusher,token=crossing,origin=self.xyz[:],stroke=.46,body_half=(.15 if p.mode=='magazine' else .21))
  if self.collecting and self.pushing is None and self.pusher<1e-8:
   q=p.parts[self.collecting];target=self.xyz[0]+.7+.5*(capacity-1-q.get('rank',0))
   if abs(q['x']-target)<1e-8:
    q['owner']='accepted';p.accepted.append(q['token']);self.taken+=1;self.collecting=None;p.emit('accepted',token=q['token'],exit=self.name)


def sheet_feed(p,side):
 ids=[i for i,q in p.parts.items() if i in p.batches and q['side']==side and q['owner'] in ('source_'+side,'feeding_'+side,'press_'+side)]
 waiting=[i for i in ids if p.parts[i]['owner']=='source_'+side and p.t>=p.batches[i]['arrival']];targets={}
 retaining=p.feeding[side] and p.parts[p.feeding[side]]['z']+.21>.42
 for i in ids:
  q=p.parts[i]
  if q['owner'].startswith('source'):
   targets[i]=(.65 if waiting and i==waiting[0] and not retaining else 1.5) if i in waiting else 1.5+(i==3)*.6
  else:targets[i]=0.
 outgoing=[q for i,q in p.parts.items() if i in p.batches and q['side']==side and q['owner']=='moving']
 fixed_stops(p,'input_'+side,ids,targets,[0.,.65,1.5,2.1],'z',.65,-1,external_bodies=outgoing)
 if p.feeding[side] and abs(p.parts[p.feeding[side]]['z'])<1e-8:
  p.parts[p.feeding[side]]['owner']='press_'+side;p.feeding[side]=None
