"""Expose the added physical jobs as request/result records in the common replay UI."""
def install(plant,ident):
 original=plant.refresh
 def refresh(self):
  original(self)
  def add(key,payload,state,results=(),arrival=0,generation=1):self.requests.append(self.request(key,generation,payload,arrival,state,results,label=key))
  if ident=='H02':
   for b in self.boxes:add('Combined-package box '+str(b['id']),dict(a_generation=b['id'],b_generation=b['id'],members_required=4),b['owner'],b['members'] if b['owner']=='shipped' else (),self.cfg.get('box_arrivals',[0,10])[b['id']-1])
  elif ident=='H04':
   for i in [2,4]:add('Stack separation '+str(i),dict(lower=i-1,upper=i),'done' if i in self.separated else 'separating' if self.separator and self.separator['id']==i else 'waiting',[i] if i in self.separated else ())
   for i in range(101,105):add('Content alignment '+str(i),dict(x=0,z=-.55,yaw=0),'done' if i in self.alignment_history else 'waiting',[i] if i in self.alignment_history else ())
  elif ident=='H05':
   for i in self.cfg.get('rejects',[2,5]):
    result=next((r for r in self.rw['returns'] if r['body']==i),None);add('Disassembly and reinspection return '+str(i),dict(body=i,new_inspection_required=True),'returned' if result else 'repairing' if self.rw['body']==i else 'waiting',[i] if result else (),generation=result['generation'] if result else 1)
  elif ident=='H06':
   add('Raw-roll leading-edge splice',dict(old_roll=1,new_roll=2,join_coordinate_mm=3600),'joined' if self.joined else 'pressing' if self.press else 'waiting',[1,2] if self.joined else ())
   add('Splice scrap receipt',dict(excluded_interval_mm=[3550,3650]),'received' if self.discarded else 'waiting',self.discarded)
  elif ident=='H07':
   for i in [1,2,3]:
    core=any(h['id']==i for h in self.core_history);tape=next((t for t in self.tape['strips'] if t['roll']==i),None)
    add('Core preparation '+str(i),dict(core=i),'seated' if core else 'waiting',[i] if core else (),self.cfg.get('core_arrivals',[0,5,10])[i-1])
    add('Tail tape '+str(i),dict(roll=i,length_mm=80),'attached' if tape else 'waiting',[tape['id']] if tape else ())
  elif ident=='H08':
   for r in self.exchange['rolls']:add('Spent-roll exchange '+str(r['id']),dict(core=r['id'],interval_mm=[r['u0']*1000,(r['u0']+1.6)*1000]),r['owner'],[r['id']] if r['owner']=='shipped' else ())
  elif ident=='H11':
   for side in 'ab':
    i=self.a if side=='a' else self.b
    if i:add(side.upper()+' fixture-width preparation',dict(product=i,width_mm=self.parts[i]['size'][2]*1000),'ready' if abs(self.exchange[side+'_width']-self.parts[i]['size'][2])<1e-8 else 'adjusting',[i] if abs(self.exchange[side+'_width']-self.parts[i]['size'][2])<1e-8 else (),generation=i)
   add('Shared-head tool handover',dict(tool=self.exchange['tool'],rack=self.exchange['at']),'moving' if self.exchange['job'] else 'latched' if self.exchange['tool'] else 'rack_supported',[self.exchange['tool']] if self.exchange['tool'] else (),generation=len(self.exchange['history'])+1)
  elif ident=='H15':
   for p in self.pallets:add('Empty-pallet handover '+str(p['id']),dict(pallet=p['id'],destination=p['side']),p['owner'],[p['id']] if p['side'] else ())
 plant.refresh=refresh
