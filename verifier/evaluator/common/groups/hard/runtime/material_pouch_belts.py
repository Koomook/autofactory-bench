from material_collection_drive import fixed_stops
from material_remaining_common import approach

def mechanism(p):
 if not hasattr(p,'nip'):p.nip=dict(y=.96,phase='idle',distance=0.,velocity=0.)
 n=p.nip;n['velocity']=0.
 if p.feed and n['phase']=='idle':n['phase']='feed_lower'
 if n['phase']=='feed_lower':
  n['y']=approach(n['y'],.868,p.dt*.6)
  if abs(n['y']-.868)<1e-8:n['phase']='feed'
 if n['phase']=='feed_raise':
  n['y']=approach(n['y'],.96,p.dt*.6)
  if abs(n['y']-.96)<1e-8:
   p.parts[p.feed]['owner']='prepared';p.feed=None;n['phase']='idle';p.emit('pouch_prepared',token=p.pouch)
 ranks={i:k for k,i in enumerate(i for i,q in p.parts.items() if q['kind']=='pouch' and q['owner']=='source')}
 ids=[i for i in ranks if not p.parts[i].get('coupled_to')]
 targets={i:.48+.42*ranks[i] for i in ids}
 if p.feed:ids.append(p.feed);targets[p.feed]=0.
 speed=.4 if (p.feed and n['phase']=='feed') or (not p.feed and not p.separator) else 0.
 fixed_stops(p,'pouch_feed',ids,targets,[0.,.48,.90,1.32,1.74],'z',speed,-1,cross_center=-.65)
 if p.feed and n['phase']=='feed':
  n['velocity']=-.4
  if abs(p.parts[p.feed]['z'])<1e-8:n['phase']='feed_raise'
 n['distance']+=n['velocity']*p.dt

def collection(p):
 n=p.nip;job=p.exit_job
 if job and n['phase']=='idle':n['phase']='exit_lower'
 if n['phase']=='exit_lower' and job:
  target=.85+p.parts[job['pouch']]['size'][1]+.014;n['y']=approach(n['y'],target,p.dt*.6)
  if abs(n['y']-target)<1e-8:n['phase']='exit'
 ids=[h['pouch'] for h in p.history];centres=[1.70-.42*k for k in range(4)];targets={i:centres[k] for k,i in enumerate(ids)}
 if job:ids.append(job['pouch']);targets[job['pouch']]=job['target']
 active=job and n['phase'] in ('exit','exit_raise')
 fixed_stops(p,'exit',ids,targets,centres,'z',.4 if active else 0.,1,cross_center=0.)
 for h in p.history+([job] if job else []):p.parts[h['content']]['z']=p.parts[h['pouch']]['z']
 if active:
  n['velocity']=.4;n['distance']+=p.dt*.4
  if p.parts[job['pouch']]['z']>.38:n['phase']='exit_raise'
 if n['phase']=='exit_raise':
  n['y']=approach(n['y'],.96,p.dt*.6)
  # Keep the exit phase until the requested package has reached its stop.
  if abs(n['y']-.96)<1e-8 and not job:n['phase']='idle'
