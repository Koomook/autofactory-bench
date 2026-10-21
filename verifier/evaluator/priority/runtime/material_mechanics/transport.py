"""Shared material path stepping and transport bookkeeping."""
import math
from .station import StationBase

class RemainingBase(StationBase):
 revision=10
 faults=['false_completion','invalid_request','axis_busy','unsupported_transfer','receiver_overflow']
 def status(self):
  s=super().status();s['revision']=10;return s
 def emit(self,name,**kw):
  if name in self.faults and any(e['type']==name for e in self.violations):return
  e=dict(type=name,scan=self.scan,**kw);self.events.append(e);self.log.append(e)
  if name in self.faults:self.violations.append(e)
 def xyz(self,p):return [p[k] for k in 'xyz']
 def setxyz(self,p,xyz):
  for k,v in zip('xyz',xyz):p[k]=v
 def step_path(self,p,path,speed):
  if not path:return
  dest=path[0];xyz=self.xyz(p);d=math.dist(xyz,dest);step=self.dt*speed
  self.setxyz(p,[a+(b-a)*min(1.,step/max(d,1e-12)) for a,b in zip(xyz,dest)])
  if d<=step+1e-10:self.setxyz(p,dest);path.pop(0)
