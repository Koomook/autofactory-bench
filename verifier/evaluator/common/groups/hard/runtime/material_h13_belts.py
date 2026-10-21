from types import SimpleNamespace
from material_collection_drive import fixed_stops

def source_belt(p,on):
 ids=[i for i in p.feeder.tokens if p.parts[i]['owner']=='source'];centres=[1.5,.0+2.15,2.8]
 fixed_stops(p,'source',ids,{i:centres[k] for k,i in enumerate(ids)},centres,'z',p.feeder.speed if on else 0.,-1)

def unit_belt(p,available):
 f=p.form;parts={i:dict(x=u['pos'][0],y=u['pos'][1],z=u['pos'][2],size=u['size']) for i,u in f['units'].items() if u['owner'] in ('supply','feeding')}
 ranks={i:k for k,i in enumerate(available) if i!=f['feeding']};ranks={i:k for k,i in enumerate(ranks)}
 retaining=f['feeding'] and parts[f['feeding']]['x']+.25>2.05
 targets={}
 for i in parts:
  if i==f['feeding']:targets[i]=1.25
  elif i in ranks:targets[i]=2.3+.56*ranks[i]+(.56 if retaining else 0)
  else:targets[i]=2.3+.56*(i-1)
 proxy=SimpleNamespace(parts=parts,dt=p.dt,transport=p.transport,belt_distance=p.belt_distance)
 fixed_stops(proxy,'units',list(parts),targets,[1.25]+[2.3+.56*k for k in range(9)],'x',p.cfg.get('formation_speed',.5),-1)
 proxy.transport['units']['body_set']='units'
 for i,b in parts.items():f['units'][i]['pos']=[b[k] for k in 'xyz']
