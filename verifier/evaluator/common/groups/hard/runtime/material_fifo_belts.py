from types import SimpleNamespace
from material_collection_drive import fixed_stops
from material_belt_contact import step_belt

def reset(p):
 if not hasattr(p,'transport'):p.transport={};p.belt_distance={}
 for name,d in p.transport.items():d.update(displacement=0.,velocity=0.,bodies={})

def deck(p,d,token):
 p.belt_distance['deck']=p.belt_distance.get('deck',0.)+d['displacement']
 q=p.parts[token];bodies={str(token):d['bodies'][str(token)]} if abs(q['z'])-q['size'][2]/2<.18 else {}
 p.transport['deck']=dict(d,distance=p.belt_distance['deck'],bodies=bodies)

def source(p,job=None):
 ids=[i for i,q in p.parts.items() if q['owner']=='source'];centres=[.55+.26*k for k in range(8)];targets={i:centres[k] if p.t>=p.arrivals[i-1] else centres[i-1] for k,i in enumerate(ids)}
 if job:ids.append(job['token']);targets[job['token']]=0.
 fixed_stops(p,'source',ids,targets,[0.]+centres,'z',p.cfg.get('transfer_speed',.55) if job else .45,-1)
 if job:deck(p,p.transport['source'],job['token'])

def kit(p,side,job=None):
 k=p.kits[side];ids=[i for i in k['members'] if p.parts[i]['owner'] in ('kit_'+side,'out_'+side,'accepted')];target=.52+(k['out']['target'] if k['out'] else 0.)
 if job:ids.append(job['token'])
 sign=1;velocity=p.cfg.get('transfer_speed',.55) if job else .45 if k['out'] else 0.
 line=.55 if side=='a' else 1.1
 # The rear component contacts the first component; one downstream finger
 # stops the pair. There is no blade inserted between two touching members.
 stops=[dict(id='out_'+side+'_stop_'+str(j),closed=abs(t-target)<1e-8,face=t+.1,cross=line,half_width=.16) for j,t in enumerate([.52,1.35,2.05])]
 d=step_belt(p.parts,ids,axis='z',displacement=p.dt*velocity,stops=stops,body_contacts=True)
 name='out_'+side;p.belt_distance[name]=p.belt_distance.get(name,0.)+p.dt*velocity;d.update(distance=p.belt_distance[name],velocity=velocity,stops=stops,clamps=[]);p.transport[name]=d
 if job:deck(p,d,job['token'])

def single(p,job):
 i=job['token'];q=p.parts[i];target=job['dest'][2];sign=1 if target>q['z'] else -1;speed=p.cfg.get('transfer_speed',.55)
 name='slot'+str(0 if abs(p.cart_x+.55)<1e-8 else 1)+('_forward' if sign>0 else '_reverse')
 fixed_stops(p,name,[i],{i:target},[0.,.46],'z',speed,sign)
 deck(p,p.transport[name],job['token'])

def boxes(p,feed):
 parts={b['id']:b for b in p.boxes};targets={};centres=[-1.35,-.6,.6,1.65,2.4]
 for i,b in parts.items():
  targets[i]=.6 if b['owner']=='station' or b['owner']=='supply' and feed==i else (2.4-.75*(i-1) if b['owner'] in ('shipping','shipped') else -.6-.75*(i-1))
 before={i:b['z'] for i,b in parts.items()};proxy=SimpleNamespace(parts=parts,dt=p.dt,transport=p.transport,belt_distance=p.belt_distance)
 fixed_stops(proxy,'box_lane',list(parts),targets,centres,'z',.5,1)
 p.transport['box_lane']['body_set']='boxes'
 for i,b in parts.items():
  for token in b['members']:p.parts[token]['z']+=b['z']-before[i]
