from material_collection_drive import fixed_stops

def source(p):
 ids=[i for i,q in p.parts.items() if q['owner']=='source'];centres=[-.5-.16*k for k in range(6)]
 targets={i:centres[k] if p.t>=p.arrivals[i-1] else centres[i-1] for k,i in enumerate(ids)}
 fixed_stops(p,'product_source',ids,targets,centres,'z',0. if p.load_job else .4,1)

def jigs(p,released):
 for name,y,sign,centres in [('upper',.885,1,[-1.2,-.4,.6,1.2]),('lower',.385,-1,[-1.2,0.,1.2])]:
  ids=[i for i in p.jigs if abs(p.parts[i]['y']-y)<1e-8];targets={}
  for i in ids:
   j=p.jigs[i];targets[i]=p.X[p.move_job['dest']] if p.move_job and p.move_job['jig']==i else p.X[j['location']]
  fixed_stops(p,name,ids,targets,centres,'x',p.cfg.get('belt_speed',.5) if released else 0.,sign)

def collection(p):
 ids=p.accepted[:];centres=[1.45-.17*k for k in range(6)];targets={i:centres[k] for k,i in enumerate(ids)}
 if p.exit_job:ids.append(p.exit_job['product']);targets[p.exit_job['product']]=p.exit_job['target']
 fixed_stops(p,'product_exit',ids,targets,centres,'z',.4,1)
