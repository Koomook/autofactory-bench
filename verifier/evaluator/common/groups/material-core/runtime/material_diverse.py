"""Contact/transport models for five bounded process tasks; no reference step access.

SI metres, ideal supports/grip, no forces, cutting mechanics or industrial safety certification.
"""
import math
from material_medium_cells import MaterialMediumCellPlant, clamp

FAULTS=['opposed_drives','operation_without_request','false_completion','workpiece_lost',
 'index_without_load','index_with_pusher_out','unload_before_index','lift_without_centered_load',
 'belt_during_lift','transfer_height_mismatch','transfer_drive_missing','return_with_load',
 'support_removed_before_grip','turn_without_grip','turn_without_clearance','release_without_support',
 'press_without_clamp','unclamp_with_tool_down','spindle_without_clamp','cut_without_spindle',
 'traverse_with_tool_down','tool_outside_hole','overtravel']

class MaterialDiversePlant(MaterialMediumCellPlant):
    def __init__(self,mode,binding,calibration,parameters,factor=1.):
        super().__init__(mode,binding,calibration,parameters,factor)
        self.axes={k:0. for k in ('load','index','unload','lift','grip','turn','clamp','ram','x','z')}
        if mode=='turnover':self.axes['lift']=1.
        self.parts=[dict(x=-.85 if mode=='index' else -1.1 if mode=='elevator' else 0.,
          y=.76 if mode=='index' else 1.10 if mode=='turnover' else .86 if mode=='press' else .68,
          z=.18 if mode=='turnover' else 0.,owner='source',status='idle')]
        self.started=False;self.history=[];self.gripped=False;self.angle=0.;self.insert_depth=0.
        self.holes=[0.,0.];self.rpm=0.;self.spindle_angle=0.;self.travel={k:0. for k in ('infeed','deck','outfeed')}
        self.speed_factor=float(parameters.get('speed_factor',1.))
        self.time=0.;self.loaded=False;self.delivered=False

    def step_devices(self,dt_ms):
        self.dt=dt_ms;self.time+=dt_ms/1000;self.pending=[];c=self.commands
        self.started |= bool(c.get('start'));self.before=self.axes.copy()
        if any(c.get(k) for k in self.binding['outputs']) and not self.started:self.fault('operation_without_request')
        for axis,forward,back in [('load','load','load_back'),('index','index','index_back'),('unload','unload','unload_back'),
          ('lift','up','down'),('grip','close','open'),('turn','turn','turn_back'),('clamp','clamp','unclamp'),
          ('ram','press','press_back'),('x','right','left'),('z','tool_down','tool_up')]:
            if c.get(forward) and c.get(back):self.fault('opposed_drives');continue
            self.axes[axis]=clamp(self.axes[axis]+dt_ms/(self.axis_ms*self.factor)*(c.get(forward,0)-c.get(back,0)))
        self.delta=dt_ms/1000*self.belt_speed*self.speed_factor
        for key in self.travel:self.travel[key]+=self.delta*bool(c.get(key))
        self.rpm=clamp(self.rpm+dt_ms/(200*self.factor)*(1 if c.get('spindle') else -1))
        self.spindle_angle+=self.rpm*dt_ms*.025

    def emit(self,name,scan):self.history.append(dict(type=name,scan=scan))
    def resolve_interactions(self,scan):
        start=len(self.history);a,c,p=self.axes,self.commands,self.parts[0];old=self.before
        if self.mode=='index':
            if c.get('index'):
                if not self.loaded or p['owner']!='table':self.fault('index_without_load')
                if a['load']>1e-8 or a['unload']>1e-8:self.fault('index_with_pusher_out')
            if c.get('unload') and a['index']<1-1e-8:self.fault('unload_before_index')
            if p['owner']=='source':
                p['x']=max(p['x'],-.85+.45*a['load'])
                if a['load']>=1-1e-8:
                    p['owner']='table';self.loaded=True;self.emit('pocket_loaded',scan)
            if p['owner']=='table':
                angle=math.pi/2*a['index'];p['x']=-.40*math.cos(angle);p['z']=-.40*math.sin(angle)
                if a['index']>=1-1e-8:
                    p['z']=min(p['z'],.18-1.20*a['unload']-.08)
                    if p['z']+.08<=-.67:
                        p['owner']='outfeed';self.emit('index_part_received',scan)
            elif p['owner']=='outfeed':
                p['z']=min(p['z'],.18-1.20*a['unload']-.08)
                if c.get('outfeed'):p['z']-=self.delta
            if p['z']< -1.72:self.fault('workpiece_lost')
        elif self.mode=='elevator':
            moving=abs(a['lift']-old['lift'])>1e-9
            if moving and any(c.get(k) for k in ('infeed','deck','outfeed')):self.fault('belt_during_lift')
            if c.get('up') and (p['owner']!='deck' or abs(p['x'])>.081):self.fault('lift_without_centered_load')
            if c.get('down') and p['owner']=='deck':self.fault('return_with_load')
            if p['owner']=='source':
                if c.get('infeed'):
                    if p['x']+.08>=-.42:
                        if not c.get('deck'):self.fault('transfer_drive_missing')
                        if a['lift']>1e-8:self.fault('transfer_height_mismatch')
                    p['x']+=self.delta
                if p['x']>=-.40:p['owner']='deck';self.emit('deck_acquired',scan)
            elif p['owner']=='deck':
                p['y']=.68+.60*a['lift']
                if c.get('deck'):
                    if a['lift']>1e-8 and a['lift']<1-1e-8:self.fault('transfer_height_mismatch')
                    p['x']+=self.delta
                    if p['x']+.08>=.42:
                        if a['lift']<1-1e-8:self.fault('transfer_height_mismatch')
                        if not c.get('outfeed'):self.fault('transfer_drive_missing')
                if p['x']-.08>=.42:
                    p['owner']='outfeed';self.delivered=True;self.emit('upper_line_received',scan)
            elif c.get('outfeed'):p['x']+=self.delta
            if p['x']>1.62:self.fault('workpiece_lost')
        elif self.mode=='turnover':
            if a['grip']>=1-1e-8 and abs(p['y']-1.10)<1e-8:
                if not self.gripped:self.emit('turnover_gripped',scan)
                self.gripped=True;p['owner']='gripper';p['status']='held'
            if c.get('down') and not self.gripped and not self.delivered:self.fault('support_removed_before_grip')
            if abs(a['turn']-old['turn'])>1e-8:
                if not self.gripped:self.fault('turn_without_grip')
                if a['lift']>.05:self.fault('turn_without_clearance')
            if self.gripped:self.angle=math.pi*a['turn']
            if c.get('open') and self.gripped:
                if a['lift']<1-1e-8 or abs(self.angle-math.pi)>1e-8:self.fault('release_without_support')
                else:
                    self.gripped=False;self.delivered=True;p['owner']='support';p['status']='idle';self.emit('flipped_part_seated',scan)
            if not self.gripped:p['y']=.80+.30*a['lift']
        elif self.mode=='press':
            if c.get('press') and a['clamp']<1-1e-8:self.fault('press_without_clamp')
            if c.get('unclamp') and a['ram']>1e-8:self.fault('unclamp_with_tool_down')
            die=1.14-.30*a['ram']
            p['y']=min(p['y'],die-.08)
            self.insert_depth=max(0.,.86-p['y'])
            if self.insert_depth>.100001:self.fault('overtravel')
            if self.insert_depth>=.10-1e-8 and not self.delivered:
                self.delivered=True;p['owner']='housing';self.emit('insert_seated',scan)
        else:
            if c.get('spindle') and a['clamp']<1-1e-8:self.fault('spindle_without_clamp')
            if c.get('unclamp') and (a['z']>1e-8 or self.rpm>1e-8):self.fault('unclamp_with_tool_down')
            if abs(a['x']-old['x'])>1e-8 and a['z']>1e-8:self.fault('traverse_with_tool_down')
            tip=.98-.28*a['z'];x=-.04+.08*a['x']
            if tip<.76:
                if self.rpm<1-1e-8:self.fault('cut_without_spindle')
                if a['clamp']<1-1e-8:self.fault('press_without_clamp')
                hole=0 if abs(x+.04)<1e-7 else 1 if abs(x-.04)<1e-7 else None
                if hole is None:self.fault('tool_outside_hole')
                elif self.rpm>=1-1e-8 and a['clamp']>=1-1e-8:
                    was=self.holes[hole];self.holes[hole]=max(was,.76-tip)
                    if was<.06-1e-8 and self.holes[hole]>=.06-1e-8:self.emit('hole_'+str(hole+1)+'_machined',scan)
        for code in set(self.pending)-self.emitted:
            self.emitted.add(code);e=dict(type=code,scan=scan);self.violations.append(e);self.history.append(e)
        if c.get('complete') and not self.goal() and 'false_completion' not in self.emitted:
            self.emitted.add('false_completion');e=dict(type='false_completion',scan=scan);self.history.append(e);self.violations.append(e)
        return self.history[start:]

    def feedback(self):
        a,p=self.axes,self.parts[0]
        s={k+'_home':v<=1e-8 for k,v in a.items()};s.update({k+'_end':v>=1-1e-8 for k,v in a.items()})
        s.update(loaded=abs(p['x']+.4)<=.08+1e-8 and abs(p['z'])<=.08+1e-8,
          exit=(p['owner']=='outfeed' and (abs(p['z']+1.45)<=.08+1e-8 if self.mode=='index' else abs(p['x']-1.10)<=.08+1e-8)),
          centered=p['owner']=='deck' and abs(p['x']-.08)<=.08+1e-8,gripped=self.gripped,seated=self.delivered,
          depth_ok=self.insert_depth>=.10-1e-8,spindle_ready=self.rpm>=1-1e-8,spindle_stopped=self.rpm<=1e-8,
          hole_1=self.holes[0]>=.06-1e-8,hole_2=self.holes[1]>=.06-1e-8)
        return {address:int(s[key]) for key,address in self.binding['inputs'].items()}

    def goal(self):
        if not self.started or any(self.commands.get(k) for k in self.binding['outputs']):return False
        a,p=self.axes,self.parts[0]
        if self.mode=='index':return self.loaded and p['owner']=='outfeed' and p['z']<=-1.37 and a['load']==0 and a['unload']==0
        if self.mode=='elevator':return self.delivered and p['owner']=='outfeed' and p['x']>=1.02 and a['lift']==0
        if self.mode=='turnover':return self.delivered and not self.gripped and abs(self.angle-math.pi)<1e-8 and a['grip']==0 and a['lift']==1
        if self.mode=='press':return self.delivered and self.insert_depth>=.10-1e-8 and a['ram']==0 and a['clamp']==0
        return all(d>=.06-1e-8 for d in self.holes) and a['z']==0 and a['clamp']==0 and self.rpm==0

    def snapshot(self):
        return dict(parts={'PART_01':self.parts[0].copy()},visual={**self.axes,**self.travel,
          'angle':self.angle,'index_display':self.axes['index']*1.5,'index_yaw':-self.axes['index']*math.pi/2,
          'insert_depth':self.insert_depth,'hole_1':self.holes[0]/.06,'hole_2':self.holes[1]/.06,
          'spindle':self.spindle_angle,'rpm':self.rpm,'x_slide':.4+.2*self.axes['x'],
          'z_slide':1.-self.axes['z']},velocity=0.,goal=int(self.goal()),
          violations=self.violations.copy(),history=self.history.copy(),holes=self.holes.copy(),insert_depth=self.insert_depth)
