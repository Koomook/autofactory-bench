"""H02–H05 installation revision. Native Medium geometry/drive units are preserved.

Receiver adapters are rigid mounting parts, not extra controlled axes. All world
poses are also recorded by the plant, including the longer H05 radial adapter.
"""
from motion_medium_mechanisms import pose,link

OFFSETS={'level':1.4,'brake_bank':.9,'gantry':.5,'frame':.65,
         'flying':1.35,'gear':1.2,'hoist':.6,'counterbalance':.75,
         'capture':.65,'index':.4}

def revise_layout(c):
 layout=c['layout'];layout['clearance_revision']=5
 src=layout['source'];src['position'][2]+=OFFSETS[c['source_mode']]
 src['position'][0]-=.25
 for s in ('1','2'):c['port_x'][s]-=250
 src['foot_size']=[4.05 if c['source_mode']=='level' else 2.2,src['position'][1],1.35]
 if c['source_mode']=='brake_bank':
  src.update(rail_shift_z=.87,foot_size=[3.4,src['position'][1],2.3],foot_offset_z=.2)
 for cell in layout['cells'].values():
  dz=OFFSETS[cell['mode']];cell['position'][2]+=dz;cell['mount_extension_z']=dz
  cell['foot_size']=[2.75 if cell['mode'] in ('gantry','flying') else 2.5,cell['position'][1],1.75]
  if cell['mode']=='flying':cell['foot_size']=[2.75,cell['position'][1],2.5];cell['foot_offset_z']=-.5
  if cell['mode']=='index':cell['receiver_radius']=.48+dz
  if cell['mode']=='gear':
   # Front roll clears underneath the receiver arm; central riser supports it.
   cell['position'][1]=.05;cell['foot_size'][1]=.05
 if c['task_slug']=='sway_settle':
  for s,dx in (('3',.9),('4',.5)):
   layout['cells'][s]['position'][0]+=dx;c['port_x'][s]+=dx*1000
 return layout

def rotated(p,v):
 # Quaternion vector rotation; same rigid transform used by Three.js.
 x,y,z,w=p['quaternion'];a,b,c=v
 tx=2*(y*c-z*b);ty=2*(z*a-x*c);tz=2*(x*b-y*a)
 return [p['pos'][0]+a+w*tx+y*tz-z*ty,
         p['pos'][1]+b+w*ty+z*tx-x*tz,
         p['pos'][2]+c+w*tz+x*ty-y*tx]

def mount_poses(layout,poses):
 out={};source=layout['source']
 for s in (1,2,3,4):
  r=poses['receiver'+str(s)]
  if s<3:
   level=source['spread']>1;dy=-.10 if level else -.07
   start=rotated(r,[0,dy,source['position'][2]-r['pos'][2]-(.45 if level else 0)])
   end=rotated(r,[0,dy,.09])
  else:
   cell=layout['cells'][str(s)];m=cell['mode'];dz=cell['mount_extension_z']
   if m=='gantry':
    # Sit on the native bridge top; pass above both native rail carriages.
    start=rotated(r,[0,-.0528,cell['position'][2]-r['pos'][2]])
    end=rotated(r,[0,-.0528,.09])
   elif m=='flying':
    # Original dock deck, then upright through the central opening between tines.
    start=[r['pos'][0],cell['position'][1]+.8245,cell['position'][2]-.93]
    elbow=[start[0],r['pos'][1]-.0675,start[2]]
    out['connector'+str(s)]=link(start,elbow,.055)
    out['connector'+str(s)+'b']=link(elbow,rotated(r,[0,-.0675,.09]),.055)
    continue
   elif m=='gear':
    start=[r['pos'][0],cell['position'][1]+1.04,cell['position'][2]]
    elbow=[start[0],r['pos'][1]-.0675,start[2]]
    out['connector'+str(s)]=link(start,elbow,.06)
    out['connector'+str(s)+'b']=link(elbow,rotated(r,[0,-.0675,.09]),.06)
    continue
   else:
    dy=-.07 if m in ('frame','capture','counterbalance') else -.0675
    if m=='index':dy=-.07
    start=rotated(r,[0,dy,dz]);end=rotated(r,[0,dy,.09])
  # Rectangular cross-section keeps the receiver's roll/yaw. A shortest-arc
  # "point Y along the segment" quaternion introduces unwanted section twist.
  out['connector'+str(s)]=pose([(a+b)/2 for a,b in zip(start,end)],r['quaternion'],[.06,.06,sum((a-b)**2 for a,b in zip(start,end))**.5])
 return out
