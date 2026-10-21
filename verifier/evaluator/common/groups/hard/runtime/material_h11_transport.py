"""Two-face process with supported tool docking/coupling and variable fixtures."""
import copy,math
import material_h11_faces_transport as base
from material_remaining_common import approach
from material_control_tools import body_of,compile_body
ID='H11';MODE='faces_tools';TITLE='Variable-width fixture preparation, physical tool exchange, and two-face regripping'
CORE=base.CORE+' Prepare the shared head tool and two independent fixtures for products of different widths; exchange tools only after checking rack support and coupling engagement.'
SIGNALS=copy.deepcopy(base.SIGNALS);SIGNALS[0].extend('source_fixture_ready tool_busy tool_at_rack tool_latched a_fixture_ready b_fixture_ready'.split());SIGNALS[1].extend('tool_dock tool_unlock tool_lock tool_return adjust_a adjust_b'.split());SIGNALS[2].extend('tool_id rack_id source_type a_type b_type cradle_type'.split());SIGNALS[3].extend('tool_select a_width b_width'.split())
SCENARIOS=base.SCENARIOS+[('type_order',{'types':[2,1,2,1]}),('slow_coupler',{'tool_speed':.25}),('slow_fixture',{'fixture_speed':.015})]
VARIANTS=base.VARIANTS+['legacy_only','unsupported_unlock','wrong_tool','wrong_fixture']
EXPECTED=dict(base.EXPECTED,legacy_only='wrong_fixture',unsupported_unlock='unsupported_tool',wrong_tool='wrong_gripper',wrong_fixture='wrong_fixture')
CONTRACT=base.CONTRACT+' Addition: product widths in Z alternate between 160 and 120 mm (types 1 and 2); the two physical edge-grip tools likewise have contact widths of 160 and 120 mm. tool_id identifies the tool coupled to the head (0 means none). tool_select=1/2 and a tool_dock rising edge move the empty head to its taught rack slot at X=-1.8, Y=1.1, and Z=-0.5 or 0. After tool_at_rack, a tool_unlock rising edge decouples a tool supported by the rack. Dock at the other slot, establish physical contact with its tool, then couple it on a tool_lock rising edge. A tool_return rising edge moves the head back to safe height and home before gripping a product. A tool of the wrong physical width causes a bad grip; decoupling while holding a product or unlocking without rack support causes unsupported_tool. Independent fixtures A and B start at 200 mm; adjust_a/b levels and a_width/b_width targets of 120 or 160 mm move actual screws at 0.015–0.08 m/s. A prepares its fixture width for the next product before admission, as indicated by source_fixture_ready. B fixes the edges after width preparation. Request each face operation only after fixture_ready for the current product width. Check tool ownership and rack support, and both-face processing of all four products. The ideal mechanical coupling extends the holding and regripping principles of P01/N14; the source material is not claimed to establish an automatic quick-changer CAD design.'
EQUIPMENT=base.EQUIPMENT+[('TOOL_RACK','Exchange-tool support rack',[-1.8,1.1,-.25]),('FIXTURE','Width-adjustment drive',[.65,.7,-.4])]
CONTRACT+=' The completion limit is 600 s, including tool-exchange delay scenarios.'
MODULES=(base.MODULES[0]+['Exchange rack and mechanical coupling axes','Two-fixture width-adjustment response'],base.MODULES[1]+['Tool return and recoupling','Fixture-width preparation by product'])
class FacesTools(base.Faces):
 mode=MODE;faults=base.Faces.faults+['unsupported_tool','wrong_gripper','wrong_fixture']
 def __init__(self,*args):
  self.exchange=dict(tool=1,at=0,job=None,tools=[dict(id=1,width=.16,owner='head',pos=[-1.15,1.45,.45]),dict(id=2,width=.12,owner='rack',pos=[-1.8,1.1,0.])],history=[],a_width=.2,b_width=.2,fixtures=[])
  super().__init__(*args)
  for i,p in self.parts.items():p['tool_type']=self.cfg.get('types',[1,2,1,2])[i-1];p['size'][2]=.16 if p['tool_type']==1 else .12
  self.refresh()
 def begin_move(self,ident,target,kind):
  p=self.parts[ident];e=self.exchange
  if e['tool']!=p['tool_type'] or e['job'] or e['at']:self.emit('wrong_gripper');return
  if kind=='a' and abs(e['a_width']-p['size'][2])>1e-8:self.emit('wrong_fixture');return
  super().begin_move(ident,target,kind)
 def work(self,s):
  i=self.a if s=='a' else self.b or self.cradle
  if i and abs(self.parts[i]['rx']-(0. if s=='a' else math.pi))>1e-8:self.emit('wrong_product_face');return
  if i and abs(self.exchange[s+'_width']-self.parts[i]['size'][2])>1e-8:self.emit('wrong_fixture');return
  super().work(s)
  if self.services[s]:self.exchange['fixtures'].append(dict(side=s,id=i,width=self.exchange[s+'_width'],product_width=self.parts[i]['size'][2]))
 def begin_step(self,dt_ms):
  super().begin_step(dt_ms);e=self.exchange;c=self.commands
  if c.get('b_clamp') and self.b and abs(e['b_width']-self.parts[self.b]['size'][2])>1e-8:self.emit('wrong_fixture')
  for s in 'ab':
   if c.get('adjust_'+s):
    target=c.get(s+'_width',0)/1000
    if target not in [.12,.16] or self.services[s]:self.emit('wrong_fixture')
    else:e[s+'_width']=approach(e[s+'_width'],target,self.dt*self.cfg.get('fixture_speed',.08))
  if self.rising('tool_dock') or self.rising('tool_return'):
   if self.held or self.job or e['job']:self.emit('unsupported_tool')
   else:
    slot=c.get('tool_select',0)
    if self.rising('tool_return'):
     if not e['tool']:self.emit('unsupported_tool')
     else:e['job']=dict(kind='return',slot=0,path=[[self.head[0],1.45,self.head[2]],[-1.15,1.45,.45]])
    elif slot not in [1,2] or (e['tool'] and e['tool']!=slot):self.emit('unsupported_tool')
    else:e['job']=dict(kind='dock',slot=slot,path=[[self.head[0],1.65,self.head[2]],[-1.8,1.65,-.5 if slot==1 else 0.],[-1.8,1.1,-.5 if slot==1 else 0.]])
    e['at']=0
  if self.rising('tool_unlock'):
   if self.held or self.job or e['job'] or not e['at'] or e['tool']!=e['at']:self.emit('unsupported_tool')
   else:t=e['tools'][e['tool']-1];t['owner']='rack';e['history'].append(dict(action='return',id=e['tool'],pos=self.head[:]));e['tool']=0
  if self.rising('tool_lock'):
   if e['job'] or not e['at'] or e['tool'] or e['tools'][e['at']-1]['owner']!='rack':self.emit('unsupported_tool')
   else:e['tool']=e['at'];e['tools'][e['tool']-1]['owner']='head';e['history'].append(dict(action='acquire',id=e['tool'],pos=self.head[:]))
  if e['job']:
   j=e['job'];dest=j['path'][0];d=math.dist(self.head,dest);a=min(d,self.dt*self.cfg.get('tool_speed',.6))
   if d:self.head=[x+(y-x)*a/d for x,y in zip(self.head,dest)]
   if math.dist(self.head,dest)<1e-8:j['path'].pop(0)
   if not j['path']:e['at']=j['slot'];e['job']=None
 def refresh(self):
  if self.exchange['tool']:self.exchange['tools'][self.exchange['tool']-1]['pos']=self.head[:]
  super().refresh()
 def observations(self):
  b,w=super().observations();e=self.exchange;b.update(source_fixture_ready=bool(self.source() and abs(e['a_width']-self.source()['size'][2])<1e-8),tool_busy=bool(e['job']),tool_at_rack=bool(e['at']),tool_latched=bool(e['tool']),a_fixture_ready=bool(self.a and abs(e['a_width']-self.parts[self.a]['size'][2])<1e-8),b_fixture_ready=bool(self.b and abs(e['b_width']-self.parts[self.b]['size'][2])<1e-8));w.update(tool_id=e['tool'],rack_id=e['at'])
  for label,i in [('source',self.source()['token'] if self.source() else 0),('a',self.a),('b',self.b),('cradle',self.cradle)]:w[label+'_type']=self.parts[i].get('tool_type',1) if i else 0
  return b,w
 def physical(self):return dict(super().physical(),extension=dict(kind='tool_exchange',**copy.deepcopy(self.exchange)))
 def goal(self):return super().goal() and {(h['side'],h['id']) for h in self.exchange['fixtures']}=={(s,i) for s in 'ab' for i in range(1,5)} and bool(self.exchange['history']) and not self.exchange['job'] and not self.exchange['at']
PLANT=FacesTools

def program(b,v):
 body,locals=body_of(base.program,b,v if v in base.VARIANTS else 'reference')
 if v in ['legacy_only','false_complete','idle']:return compile_body(b,body,locals)
 body+='''\nIF NOT I_a_present AND I_source_type>0 AND NOT I_source_fixture_ready AND NOT I_head_busy THEN O_adjust_a:=TRUE;IF I_source_type=1 THEN O_a_width:=160;ELSE O_a_width:=120;END_IF;END_IF;
IF O_admit AND NOT I_source_fixture_ready THEN O_admit:=FALSE;END_IF;
IF NOT I_b_fixture_ready THEN O_b_clamp:=FALSE;END_IF;
IF I_a_present AND NOT I_a_done AND NOT I_a_fixture_ready THEN O_adjust_a:=TRUE;IF I_a_type=1 THEN O_a_width:=160;ELSE O_a_width:=120;END_IF;O_work_a:=FALSE;END_IF;
IF I_b_present AND NOT I_b_done AND NOT I_b_fixture_ready THEN O_adjust_b:=TRUE;IF I_b_type=1 THEN O_b_width:=160;ELSE O_b_width:=120;END_IF;O_work_b:=FALSE;END_IF;
IF toolphase=0 THEN
 desired:=I_tool_id;
 IF O_admit THEN desired:=I_source_type;ELSIF O_to_cradle THEN desired:=I_a_type;ELSIF O_head_grip THEN desired:=I_cradle_type;ELSIF O_release THEN desired:=I_b_type;END_IF;
 IF desired<>I_tool_id THEN toolphase:=1;END_IF;
END_IF;
IF toolphase>0 THEN
 O_admit:=FALSE;O_to_cradle:=FALSE;O_head_grip:=FALSE;O_release:=FALSE;
 CASE toolphase OF
 1: O_tool_select:=I_tool_id;O_tool_dock:=TRUE;toolphase:=2;
 2: IF I_tool_at_rack AND NOT I_tool_busy THEN O_tool_unlock:=TRUE;toolphase:=3;END_IF;
 3: IF NOT I_tool_latched THEN O_tool_select:=desired;O_tool_dock:=TRUE;toolphase:=4;END_IF;
 4: IF I_tool_at_rack AND I_rack_id=desired AND NOT I_tool_busy THEN O_tool_lock:=TRUE;toolphase:=5;END_IF;
 5: IF I_tool_latched THEN O_tool_return:=TRUE;toolphase:=6;END_IF;
 6: IF NOT I_tool_busy AND NOT I_tool_at_rack THEN toolphase:=0;END_IF;
 END_CASE;
END_IF;'''
 if v=='unsupported_unlock':body+='\nIF I_tool_latched AND NOT I_tool_at_rack THEN O_tool_unlock:=TRUE;END_IF;'
 if v=='wrong_tool':body=body.replace('IF desired<>I_tool_id THEN','IF FALSE THEN')
 if v=='wrong_fixture':body+='\nO_adjust_a:=FALSE;IF I_source_ready AND NOT I_a_present AND NOT I_head_busy THEN O_admit:=TRUE;END_IF;'
 return compile_body(b,body,locals,'toolphase:INT:=0;desired:INT:=1;')
def audit_frame(f):
 base.audit_frame(f);e=f['plant']['physical']['extension'];assert len(e['tools'])==2 and sum(t['owner']=='head' for t in e['tools'])==int(e['tool']>0)
 for t in e['tools']:
  if t['owner']=='head':assert math.dist(t['pos'],f['plant']['physical']['head'])<1e-8
  else:assert math.dist(t['pos'],[-1.8,1.1,-.5 if t['id']==1 else 0.])<1e-8
 for h in e['fixtures']:assert abs(h['width']-h['product_width'])<1e-8
 for p in f['plant']['parts'].values():
  if p['owner']=='head':assert e['tool']==p['tool_type']
def audit_final(f):base.audit_final(f);e=f['physical']['extension'];assert len(e['fixtures'])==8 and any(h['id']==2 for h in e['history'])

from material_control_views import install as _install_request_views
_install_request_views(PLANT,ID)
