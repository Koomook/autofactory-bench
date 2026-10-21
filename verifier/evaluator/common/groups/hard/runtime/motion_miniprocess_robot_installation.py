"""Scoped H09 repair and H11–H15 installation revision.

Reuse the published Medium mechanisms and passive installation adapters. Robot
link layers and bearing spans are explicit, recorded geometry, including rewind.
"""
from math import atan2,hypot,pi
from motion_medium_mechanisms import pose,link,yaw
from motion_miniprocess_clearance import rotated
from motion_miniprocess_installation import cell_state as previous_cell_state, mounts as previous_mounts

OFFSETS={'level':1.4,'brake_bank':.9,'table':0,'index':.4,'cross':1.2,
         'exchange':1.0,'master':1.5,'gear':1.2,'frame':.65,'capture':.65,
         'balance':.75,'pockets':0}

def revise_layout(c):
 l=c['layout'];l['clearance_revision']=7;s=l['source'];s['position'][2]+=OFFSETS[c['source_mode']];s['position'][0]-=.25
 for k in ('1','2'):c['port_x'][k]-=250
 s['foot_size']=[4.05 if c['source_mode']=='level' else 2.2,s['position'][1],1.35]
 if c['source_mode']=='brake_bank':s.update(rail_shift_z=.87,foot_size=[3.4,s['position'][1],2.3],foot_offset_z=.2)
 for k,cell in l['cells'].items():
  m=cell['mode'];dz=OFFSETS[m];cell['position'][2]+=dz;cell['mount_extension_z']=dz
  cell['foot_size']=[2.5,cell['position'][1],1.75]
  if m=='table':cell['foot_size']=[1.15,cell['position'][1],1.0]
  if m=='index':cell['receiver_radius']=.88
  if m=='balance':cell['foot_size']=[3.25,cell['position'][1],1.1]
  if m=='exchange':
   cell['position'][1]=.08;cell['position'][0]+=1.3;cell['rotation_y']=pi;cell['foot_size']=[2.75,.08,1.75];cell['dock_point']=[-.65,1.52,0]
  if m=='gear':cell['position'][1]=.05;cell['foot_size'][1]=.05
  if m=='pockets':
   cell['position'][2]=1.1;cell['foot_size']=[2.75,cell['position'][1],1.6];cell['foot_offset_z']=.35
   cell['pocket_z']=.51-cell['position'][2]
   cell['native_positions']=[[-.95,.2,.25],[0,.5,.85],[.95,.2,.25]]
   cell['pocket_homes']=[[-.7,-.15],[0,.2],[.7,-.15]];cell['pocket_branches']=[1,1,-1]
  if m=='master':
   cell['position'][0]+=.65;c['port_x'][k]+=650;cell['receiver_stand']=True
  if m=='cross':cell['cross_support_x']=-1.25;cell['foot_size']=[3.15,cell['position'][1],2.55]
  if m=='pockets' and c['task_slug']=='balance_route':cell['position'][0]+=.15;c['port_x'][k]+=150
 return l

def flat_link(a,b,width,height):
 angle=atan2(b[2]-a[2],b[0]-a[0])
 return pose([(x+y)/2 for x,y in zip(a,b)],yaw(-angle),[hypot(b[0]-a[0],b[2]-a[2]),height,width])

def cell_state(plant,s,cell):
 previous_cell_state(plant,s,cell);cell['clearance_revision']=7
 if cell['mode']=='cross':
  cell['cross_support_x']=plant.layout['cells'][str(s)]['cross_support_x']
  x,z=plant.values(s);p=cell['poses']
  p['stem0']=link([x/1000,.6872,0],[x/1000,.86,0],.06)
  p['stem1']=link([0,1.04,z/1000],[0,1.2128,z/1000],.06)
 if cell['mode']=='pockets':
  for mech in cell['mechanisms'].values():
   p=mech['poses'];elbow=p['elbow']['pos'];tip=p['wrist']['pos']
   elbow[1]=.975;tip[1]=1.10
   p['upper']=flat_link([0,.85,0],[elbow[0],.85,elbow[2]],.16,.14)
   p['forearm']=flat_link([elbow[0],1.10,elbow[2]],tip,.13,.13)
   mech['clearance_revision']=7
   t=p['tool']['pos'];p['tool_stem']=link([t[0],1.02,t[2]],[t[0],t[1]+.03,t[2]],.035)
 return cell

def mounts(plant,poses):
 out=previous_mounts(plant,poses)
 for s in (3,4):
  cell=plant.layout['cells'][str(s)];m=cell['mode'];base=cell['position'];r=poses['receiver'+str(s)];k='connector'+str(s);dz=cell['mount_extension_z']
  if m in ('frame','capture','index','cross'):
   dy=-.05 if m=='cross' else -.07
   a=rotated(r,[0,dy,dz]);b=rotated(r,[0,dy,.09]);out[k]=pose([(x+y)/2 for x,y in zip(a,b)],r['quaternion'],[.06,.06,dz-.09])
  if m=='gear':
   a=[r['pos'][0],base[1]+1.04,base[2]];b=[a[0],r['pos'][1]-.0675,a[2]]
   out[k]=link(a,b,.06);out[k+'b']=link(b,rotated(r,[0,-.0675,.09]),.06)
  if m=='master':
   # Fixed receiving stand on the common drive base, ahead of rotating disks.
   a=[r['pos'][0],base[1]+.05,base[2]-.45];b=[a[0],a[1],.60];top=[a[0],r['pos'][1]-.0675,.60]
   out[k]=link(a,b,.07);out[k+'b']=link(b,top,.07)
 return out
