from material_belt_contact import step_belt

def source(p):
 if not hasattr(p,'transport'):p.transport={};p.belt_distance={}
 for kind,name in [(1,'feed_a'),(2,'feed_b')]:
  ids=[i for i,q in p.parts.items() if q['kind']==kind and q['owner']=='source']
  # Equal-pitch source queues index as a whole and stop as a whole for pickup.
  delta=min(p.dt*.35,max(0.,-.55-p.parts[ids[0]]['z'])) if ids and not p.head_job else 0.
  d=step_belt(p.parts,ids,axis='z',displacement=delta);p.belt_distance[name]=p.belt_distance.get(name,0.)+delta
  d.update(distance=p.belt_distance[name],velocity=delta/p.dt,stops=[],clamps=[]);p.transport[name]=d
