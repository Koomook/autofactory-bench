"""H06–H10 installation: native devices, explicit rigid mounts and clear sweeps.

Scoped by clearance_revision=6. H01–H05 and H11–H15 retain their contracts.
"""
from copy import deepcopy
from math import acos,atan2,cos,sin,pi
from types import SimpleNamespace
from motion_medium_mechanisms import pose,link,DiverseMotionPlant
from motion_miniprocess_clearance import rotated

OFFSETS={'level':1.4,'brake_bank':.9,'gantry':.5,'counterbalance':.75,
         'hoist':.6,'balance':.75,'table':0,'booms':0,'exchange':1.0,'pockets':0}

def revise_layout(c):
 l=c['layout'];l['clearance_revision']=6;s=l['source'];s['position'][2]+=OFFSETS[c['source_mode']];s['position'][0]-=.25
 for k in ('1','2'):c['port_x'][k]-=250
 s['foot_size']=[4.05 if c['source_mode']=='level' else 2.2,s['position'][1],1.35]
 if c['source_mode']=='brake_bank':s.update(rail_shift_z=.87,foot_size=[3.4,s['position'][1],2.3],foot_offset_z=.2)
 for k,cell in l['cells'].items():
  m=cell['mode'];dz=OFFSETS[m];cell['position'][2]+=dz;cell['mount_extension_z']=dz
  cell['foot_size']=[2.75 if m=='gantry' else 2.5,cell['position'][1],1.75]
  if m=='table':cell['foot_size']=[1.15,cell['position'][1],1.0]
  if m=='booms':
   cell['position'][1]=.2;cell['foot_size']=[2.1,.2,2.2];cell['foot_offset_z']=.55
   cell['native_positions']=[[-.6,0,0],[.6,0,1.1]]
  if m=='balance':cell['foot_size']=[3.25,cell['position'][1],1.1]
  if m=='counterbalance':cell['foot_size']=[1.35,cell['position'][1],1.0]
  if m=='exchange':
   cell['position'][1]=.08;cell['position'][0]+=1.3;cell['rotation_y']=pi;cell['foot_size']=[2.75,.08,1.75];cell['dock_point']=[-.65,1.52,0]
  if m=='pockets':
   cell['position'][2]=1.1;cell['foot_size']=[2.75,cell['position'][1],1.6];cell['foot_offset_z']=.35
   cell['pocket_z']=.51-cell['position'][2]
   cell['native_positions']=[[-.95,.2,.25],[0,.5,.85],[.95,.2,.25]]
   cell['pocket_homes']=[[-.7,-.15],[0,.2],[.7,-.15]]
   cell['pocket_branches']=[1,1,-1]
 return l

def cell_state(plant,s,cell):
 cfg=plant.layout['cells'][str(s)];m=cfg['mode'];cell['clearance_revision']=6
 if m=='booms':cell['native_positions']=cfg['native_positions']
 if m=='pockets':
  cell.update(native_positions=cfg['native_positions'],pocket_z=cfg['pocket_z'])
  route=plant.stage[s]['route'];dest=[-.35 if route==1 else .35,cfg['pocket_z']]
  for k,x in enumerate(plant.values(s)):
   base=cfg['native_positions'][k];home=cfg['pocket_homes'][k];tip=[home[i]+(dest[i]-home[i])*x/1000 for i in (0,1)]
   dx,dz=tip[0]-base[0],tip[1]-base[2];v=(dx*dx+dz*dz-.9**2-.7**2)/(2*.9*.7)
   if not -1<=v<=1:raise ValueError(('unreachable pocket',k,tip,v))
   b=cfg['pocket_branches'][k]*acos(v);a=atan2(dz,dx)-atan2(.7*sin(b),.9+.7*cos(b))
   obj=object.__new__(DiverseMotionPlant);obj.mode='articulated';obj.drives={n:SimpleNamespace(x=t*180/pi,v=0) for n,t in zip('abc',(a,b,-a-b))};obj.i={};obj.c=dict(axis_units={},axis_labels={})
   mech=obj.mechanism();p=mech['poses'];p['tool']['pos'][1]=.915-base[1]
   p['tool_stem']=link([p['tool']['pos'][0],.85,p['tool']['pos'][2]],[p['tool']['pos'][0],p['tool']['pos'][1]+.03,p['tool']['pos'][2]],.035)
   cell['mechanisms']['robot'+str(k)]=mech
 return cell

def mounts(plant,poses):
 l=plant.layout;out={};source=l['source']
 for s in (1,2,3,4):
  r=poses['receiver'+str(s)];key='connector'+str(s)
  if s<3:
   level=source['spread']>1;dy=-.10 if level else -.07
   start=rotated(r,[0,dy,source['position'][2]-r['pos'][2]-(.45 if level else 0)]);end=rotated(r,[0,dy,.09])
  else:
   cell=l['cells'][str(s)];m=cell['mode'];base=cell['position'];dz=cell['mount_extension_z']
   if m=='table':continue # Original table jaws and ledger supports carry the jig.
   if m=='pockets':
    for k in (0,1):
     p=pose([base[0]-.35+.7*k,1.6,.51]);out[key+str(k)]=pose(rotated(p,[0,-.115,.09]),scale=[.06,.06,.06])
    continue
   if m=='gantry':start=rotated(r,[0,-.0528,base[2]-r['pos'][2]]);end=rotated(r,[0,-.0528,.09])
   elif m=='booms':
    # End-eye side lug and raised bridge leave both telescoping sleeves and
    # the central insertion slot clear. All three pieces follow the same tip.
    theta=-65*pi/180
    a=[.05*cos(theta),-.4,.05*sin(theta)]
    b=[a[0]-.18*sin(theta),-.4,a[2]+.18*cos(theta)]
    top=[b[0],-.0675,b[2]]
    out[key]=link(rotated(r,a),rotated(r,b),.035)
    out[key+'b']=link(rotated(r,b),rotated(r,top),.035)
    out[key+'c']=link(rotated(r,top),rotated(r,[0,-.0675,.09]),.035);continue
   elif m=='exchange':
    # Reverse the native cell installation: the tall A guide stays behind
    # the heads. B's original arm carries a low bridge under the raised A head.
    start=[r['pos'][0],base[1]+.9822,base[2]-.22]
    elbow=[start[0],start[1],.60];end=[start[0],r['pos'][1]-.0675,.60]
    out[key]=link(start,elbow,.05);out[key+'b']=link(elbow,end,.05);continue
   else:
    dy=-.07 if m in ('counterbalance','balance') else -.0675
    start=rotated(r,[0,dy,dz]);end=rotated(r,[0,dy,.09])
  out[key]=pose([(a+b)/2 for a,b in zip(start,end)],r['quaternion'],[.06,.06,sum((a-b)**2 for a,b in zip(start,end))**.5])
 return out
