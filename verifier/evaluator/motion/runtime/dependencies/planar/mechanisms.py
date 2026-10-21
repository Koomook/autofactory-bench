"""Synthetic benchmark mechanisms. Metres, world XYZ, explicit protected pairs.

Setup is fixed when a scenario is instantiated. PLC request/reference registers
never move fixed hardware. The renderer consumes these same solid transforms.
This is a rigid, kinematic interference model, not whole-machine CAD certification.
"""
from math import sin, cos, radians, hypot
from dependencies.geometry.plant import rotating_head_safe

LIMITS={6:[100,100,400],7:[650,150],8:[350,150],9:[150,70,70,100],10:[1000,360],11:[360,100,100],12:[100,250,120],13:[150,40,400],15:[70,70,250],16:[300,120],17:[300,180,400,120],18:[350,80,120],19:[600,90]}

def bodies(n, positions, setup, module_position=0):
 q=setup['request'];v={k:t/1000 for k,t in positions.items()};a=v.get('a',0);b=v.get('b',0);c=v.get('c',0);d=v.get('d',0)
 parts=[];pairs=[]
 def box(name,pos,size,moving=False,angle=0,axis='y'):
  parts.append(dict(name=name,pos=list(pos),size=list(size),moving=moving,angle=angle,axis=axis));return name
 def protect(m,others):pairs.extend((m,t) for t in others)
 def slotted(prefix,start,end,holes,y,height,z,width):
  cursor=start;names=[]
  for lo,hi in sorted(holes)+[(end,end)]:
   if lo>cursor:names.append(box(prefix+str(len(names)),[(cursor+lo)/2,y,z],[lo-cursor,height,width]))
   cursor=max(cursor,hi)
  return names
 if n==6:
  nose=box('transfer-nose',[c+.025,.455,0],[.13,.055,.07],True)
  protect(nose,[box('upper-opening-plate',[.295,.4775+a,0],[.31,.045,.26],True),box('lower-opening-plate',[.295,.4325-b,0],[.31,.045,.26],True)])
 elif n==7:
  tip=box('access-probe',[a,.145+b,0],[.022,.07,.025],True)
  holes=[(q[k]/1000-.012,q[k]/1000+.012) for k in ['first','second']]
  walls=slotted('access-deck-',.05,.68,holes,.155,.11,0,.13)
  for k,depth in [('first',0),('second',q['depth']/1000)]:walls.append(box(k+'-port-floor',[q[k]/1000,.095+depth,0],[.024,.02,.13]))
  protect(tip,walls)
 elif n==8:
  fork=box('access-fork',[.29,.55,.18-b],[.23,.018,.035],True)
  pitch=q['pitch']/1000;mark=setup['mark']/1000
  shelves=[]
  for j in range(7):shelves.append(box('rack-shelf-'+str(j),[.215,.55+a-mark+pitch/2-j*pitch,0],[.13,.008,.16],True))
  protect(fork,shelves)
 elif n==9:
  for k,side in [('b',-1),('c',1)]:
   pin=box(k+'-locking-pin',[a,.39,side*(.16-v[k])],[.006,.012,.115],True)
   walls=[]
   for x in [.0815,.1185]:walls.append(box(k+'-receiver-'+str(x),[x,.39,side*.04],[.03,.025,.025]))
   protect(pin,walls)
 elif n==11:
  for k,side in [('b',1),('c',-1)]:box(k+'-tool-probe',[.33+side*.11,.40875-v[k],0],[.015,.1125,.015],True)
 elif n==12:
  key=box('coarse-docking-key',[.08+a,.18+c,-.12],[.008,.02,.012],True)
  coarse=q['coarse']/1000
  walls=slotted('low-dock-',.06,.10+coarse,[(.075,.085),(.075+coarse,.085+coarse)],.18,.04,-.12,.08)
  protect(key,walls)
  tip=box('telescopic-tool',[.13+a+b,.325+c,0],[.10,.025,.05],True)
  protect(tip,[box('far-clearance-wall',[.5075,.23125,0],[.485,.3225,.10])])
 elif n==13:
  angle=positions['b'];t=radians(angle)
  head=box('tilted-key',[ -.08*sin(t),.28+a+.08*cos(t),c-.025],[.065,.17,.055],True,angle,'z')
  t=radians(q['angle']);cx=-.08*sin(t);cy=.40+.08*cos(t);walls=[]
  # A fixed, rotated rectangular aperture. No request-dependent safety window.
  for name,lx,ly,sx,sy in [('left',-.05,0,.03,.236),('right',.05,0,.03,.236),('lower',0,-.103,.07,.03),('upper',0,.103,.07,.03)]:
   walls.append(box('tilt-aperture-'+name,[cx+lx*cos(t)-ly*sin(t),cy+lx*sin(t)+ly*cos(t),.15],[sx,sy,.012],False,q['angle'],'z'))
  protect(head,walls)
 elif n==15:
  xx=.12+q['target']/1000;wrong='b' if q['side']==1 else 'a'
  for k,side in [('a',-1),('b',1)]:
   pin=box(k+'-datum',[xx,.37,side*(.13-v[k])],[.055,.055,.025],True)
   if k==wrong:protect(pin,[box('blocked-insert-face',[xx,.37,side*.1025],[.07,.07,.01])])
  box('access-nose',[c+.12,.36,0],[.035,.02,.02],True)
 elif n==16:
  # The moving table and carrier each have a bore under the supplied probe.
  xx=q['target']/1000;zz=.18-q['depth']/1000
  box('module-probe',[xx,.53-module_position/1000,zz],[.016,.10,.016],True)
  for name,center,y in [('table',[a,zz],.413),('carrier',[xx,.18-b],.445)]:
   for side in [-1,1]:
    box(name+'-bore-x'+str(side),[center[0]+side*.041,y,center[1]],[.062,.012,.10],True)
    box(name+'-bore-z'+str(side),[center[0],y,center[1]+side*.041],[.02,.012,.062],True)
  protect('module-probe',[p['name'] for p in parts if '-bore-' in p['name']])
 elif n==17:
  head=box('rotating-head',[c,.415+d,0],[.20,.04,.035],True,positions['b'])
  fork=[box('feeder-fork-'+str(side),[a-.28,.49,side*.055],[.24,.18,.02],True) for side in [-1,1]]
  target=q['target']/1000
  walls=[box('destination-cheek-'+str(side),[target+side*.08,.43,0],[.11,.12,.24]) for side in [-1,1]]
  protect(head,fork+walls)
 elif n==18:
  tool=box('internal-tool',[a,.30+c,.02+b],[.03,.02,.02],True)
  protect(tool,[box('retraction-overhang',[.20,.365,.08],[.55,.07,.08])])
  key=box('search-carriage-key',[a,.27+c,0],[.018,.02,.025],True)
  walls=slotted('search-low-guard-',-.05,.45,[(.01,.03),(.15,.17)],.27,.14,0,.04)
  protect(key,walls)
 elif n==19:
  tip=box('guide-tip',[a,.385-b,0],[.018,.07,.025],True)
  walls=[box('guide-floor',[.30,.265,0],[.30,.02,.06])]
  walls += [box('guide-end-'+str(xx),[xx,.30,0],[.01,.04,.06]) for xx in [.145,.455]]
  walls += [box('guide-side-'+str(z),[.30,.30,z],[.30,.04,.05]) for z in [-.055,.055]]
  protect(tip,walls)
 return parts,pairs

def basis(p):
 t=radians(p['angle']);c=cos(t);s=sin(t)
 if p['axis']=='z':return ((c,s,0),(-s,c,0),(0,0,1))
 return ((c,0,-s),(0,1,0),(s,0,c))
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def intersects(p,q):
 if p["angle"]==q["angle"]==0:
  return all(abs(p["pos"][i]-q["pos"][i])<(p["size"][i]+q["size"][i])/2-1e-9 for i in range(3))
 u=basis(p);v=basis(q);delta=[q['pos'][i]-p['pos'][i] for i in range(3)]
 # Separating-axis test, positive penetration only; touching is allowed.
 for axis in (*u,*v,*(cross(x,y) for x in u for y in v)):
  if dot(axis,axis)<1e-16:continue
  rp=sum(abs(dot(axis,u[i]))*p['size'][i]/2 for i in range(3));rq=sum(abs(dot(axis,v[i]))*q['size'][i]/2 for i in range(3))
  if abs(dot(delta,axis))>=rp+rq-1e-9:return False
 return True

def contacts(n,positions,setup,module_position=0):
 if n==10:return [] if rotating_head_safe(positions['a'],positions['b']) else [('two-sided-head','corridor-boundary')]
 parts,pairs=bodies(n,positions,setup,module_position);byname={p['name']:p for p in parts}
 found=[(a,b) for a,b in pairs if intersects(byname[a],byname[b])]
 if n==11:
  angle=radians(positions['a']);holes=[]
  for side,key in [(1,'first'),(-1,'second')]:
   t=radians(setup['request'][key])-angle;holes.append((side*.11*cos(t),side*.11*sin(t)))
  for k,side in [('b',1),('c',-1)]:
   bottom=.3525-positions[k]/1000;top=bottom+.1125
   if bottom<.3475-1e-9 and top>.3125+1e-9 and not any(hypot(side*.11-hx,hz)+.0075<=.012+1e-9 for hx,hz in holes):found.append((k+'-tool-probe','index-disc'))
 return found

def contract(n):
 return dict(schema='motion-mechanism/5',units='metres; command/feedback mm or deg scaled x100',setup='Immutable request fixture configuration and fixed sensor plane, copied at scenario initialization.',collision='Positive rigid-body overlap for named protected pairs; M10 rectangle/corridor union; M11 cylindrical probe/disc bores. Contact is allowed. No force simulation or whole-machine CAD certification.',geometry_definition='planar/mechanisms.py:bodies,contacts',command_limits=dict(zip('abcd',LIMITS[n])),completion='After each 10 ms plant step; actual arrival tolerance 0.2 and speed <=1; no extra 30 ms local dwell; claim by 15000 ms, held for 100 ms.')
