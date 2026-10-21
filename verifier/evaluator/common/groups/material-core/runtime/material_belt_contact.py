"""Ideal no-inertia belt/contact integration, independent of PLC/result state.

A drive has one axis and signed surface displacement per scan. Every contacting
body receives it. Only a contacting clamp or physical stop can constrain a body;
there is no per-object velocity argument and no off-axis destination argument.
A clamped body slips against the belt (low-back-pressure accumulation contract).
"""
def step_belt(parts, ids, *, axis, displacement, clamps=(), stops=(), body_contacts=False):
 if axis not in ('x','z'):raise ValueError('A horizontal belt cannot lift a body')
 before={i:dict(parts[i]) for i in ids};rows={}
 ordered=sorted(ids,key=lambda i:parts[i][axis],reverse=displacement>=0) if body_contacts else ids
 processed=[]
 for i in ordered:
  p=parts[i];x=p[axis];dx=displacement;hold=None;stop=None
  for c in clamps:
   if not c.get('closed'):continue
   if all(abs(p[k]-c['position'][k])<=c.get('tolerance',1e-7) for k in ('x','y','z')):
    dx=0.;hold=c['id'];break
  if hold is None:
   for s in stops:
    if not s.get('closed'):continue
    # Stop position is the body-centre contact limit for its specified length.
    # It is fixed in the hardware frame and is not a per-body motion target.
    cross='z' if axis=='x' else 'x'
    if abs(p[cross]-s['cross'])>s.get('half_width',.14):continue
    limit=s['face']-(1 if displacement>=0 else -1)*p['size'][0 if axis=='x' else 2]/2
    if displacement>0 and x<=limit+1e-8 and x+dx>=limit:
     dx=max(0.,limit-x);stop=s['id']
    elif displacement<0 and x>=limit-1e-8 and x+dx<=limit:
     dx=min(0.,limit-x);stop=s['id']
  touching=None
  if body_contacts:
   dimension=0 if axis=='x' else 2;cross='z' if axis=='x' else 'x';ci=2 if axis=='x' else 0
   for other in processed:
    q=parts[other]
    if abs(q[cross]-p[cross])>=(q['size'][ci]+p['size'][ci])/2 or abs(q['y']-p['y'])>=(q['size'][1]+p['size'][1])/2:continue
    gap=(q['size'][dimension]+p['size'][dimension])/2;limit=q[axis]-(gap if displacement>=0 else -gap)
    if displacement>0 and x+dx>limit+1e-10:dx=max(0.,limit-x);touching=str(other)
    elif displacement<0 and x+dx<limit-1e-10:dx=min(0.,limit-x);touching=str(other)
  p[axis]=x+dx;processed.append(i)
  rows[str(i)]={'delta':dx,'clamp':hold,'stop':stop,'slip':displacement-dx,**({'body_contact':touching} if touching else {})}
  assert all(p[k]==before[i][k] for k in ('x','y','z') if k!=axis)
 return dict(axis=axis,displacement=displacement,bodies=rows)
