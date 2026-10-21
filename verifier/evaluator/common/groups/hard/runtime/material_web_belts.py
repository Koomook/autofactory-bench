from material_collection_drive import fixed_stops

def belts(p):
 from material_remaining_common import approach
 if not hasattr(p,'waste_gripper'):p.waste_gripper=dict(token=None,x=.65,y=1.10,z=0.,grip=0.,stage='idle')
 h=p.waste_gripper;active=p.parts[p.exit_job['id']] if p.exit_job and p.parts[p.exit_job['id']]['side']=='waste' else None
 if active and len(p.waste_path)>1 and h['stage']=='idle':h.update(token=active['token'],stage='approach')
 a=p.parts[h['token']] if h['token'] else None
 if h['stage']=='approach':
  h['x']=approach(h['x'],a['x'],p.dt*.6)
  if abs(h['x']-a['x'])<1e-8:h['stage']='lower'
 elif h['stage']=='lower':
  h['y']=approach(h['y'],a['y'],p.dt*.4)
  if abs(h['y']-a['y'])<1e-8:h['stage']='grip'
 elif h['stage']=='grip':
  h['grip']=approach(h['grip'],1.,p.dt/.2)
  if h['grip']>=1.:h['stage']='pull'
 elif h['stage']=='pull':
  h['x']=approach(h['x'],1.8+a['length']/2,p.dt*.4);a['x']=h['x']
  if abs(h['x']-(1.8+a['length']/2))<1e-8:p.waste_path=p.waste_path[1:];h['stage']='release'
 elif h['stage']=='release':
  h['grip']=approach(h['grip'],0.,p.dt/.2)
  if h['grip']<=0.:h['stage']='raise'
 elif h['stage']=='raise':
  h['y']=approach(h['y'],1.10,p.dt*.4)
  if h['y']>=1.10:h['stage']='return'
 elif h['stage']=='return':
  h['x']=approach(h['x'],.65,p.dt*.6)
  if abs(h['x']-.65)<1e-8:h.update(stage='idle',token=None)
 for side,sign in [('a',1),('b',-1),('waste',-1)]:
  ids=[i for i,q in p.parts.items() if q['side']==side and q['owner'] in ('accepted','discarded','exit') and not (side=='waste' and h['stage'] not in ('idle','return'))]
  old=p.orders[side]['ids'] if side!='waste' else p.discarded
  centres=[sign*(1.10-.20*k) for k in range(3)] if side!='waste' else [-.65-.18*k for k in range(2)]
  targets={i:centres[old.index(i)] if i in old else p.exit_job['target'] for i in ids}
  fixed_stops(p,'receiver_'+side,ids,targets,centres,'z',.4,sign,cross_center=.48 if side!='waste' else 1.84)
  if side=='waste' and p.exit_job and p.parts[p.exit_job['id']]['side']=='waste' and len(p.waste_path)==1 and abs(p.parts[p.exit_job['id']]['z']-p.exit_job['target'])<1e-8:p.waste_path=[]
