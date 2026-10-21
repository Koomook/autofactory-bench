"""Three independently driven supports; SI metres, ideal no-slip rigid transfer."""
import math
from material_medium_cells import MaterialMediumCellPlant,clamp
FAULTS=['operation_without_request','opposed_drives','transfer_drive_missing','transfer_misaligned','rotate_without_centered_load','belt_during_rotation','return_before_clear','workpiece_lost','false_completion']
class CornerTransferPlant(MaterialMediumCellPlant):
    def __init__(self,mode,binding,calibration,parameters,factor=1.):
        super().__init__(mode,binding,calibration,parameters,factor)
        self.turn=0.;self.started=False;self.delivered=False;self.loaded=False;self.history=[]
        self.parts[0]['x']=float(parameters.get('initial_x',-.9));self.parts[0]['owner']='infeed'
        self.local=0.;self.travels={k:0. for k in ('infeed','deck','outfeed')}
        self.speed=float(parameters.get('speed_factor',1.))*self.belt_speed
    def step_devices(self,dt_ms):
        self.dt=dt_ms;self.pending=[];c=self.commands;self.started|=bool(c.get('start'));self.old_turn=self.turn
        if any(c.get(k) for k in self.binding['outputs']) and not self.started:self.fault('operation_without_request')
        if c.get('rotate') and c.get('return'):self.fault('opposed_drives')
        else:self.turn=clamp(self.turn+dt_ms/(self.axis_ms*self.factor)*(c.get('rotate',0)-c.get('return',0)))
        self.delta=dt_ms/1000*self.speed
        for k in self.travels:
            if c.get(k):self.travels[k]+=self.delta
    def transfer(self,u,source,receiver,end,begin):
        c=self.commands;on_source=u-.08<=end+1e-8;on_receiver=u+.08>=begin-1e-8
        # Both contact patches must have matching drive. A stopped receiving belt
        # is NOT silently treated as a continuation of the sending belt.
        if on_source and on_receiver:
            if bool(c.get(source))!=bool(c.get(receiver)):self.fault('transfer_drive_missing')
            return self.delta if c.get(source) and c.get(receiver) else 0.
        return self.delta if c.get(source if on_source else receiver) else 0.
    def resolve_interactions(self,scan):
        p=self.parts[0];c=self.commands;events=[];moving=abs(self.turn-self.old_turn)>1e-8
        centered=p['owner']=='deck' and abs(self.local)<=.015
        clear=p['owner']=='outfeed' and -p['z']-.08>.32
        if c.get('rotate') and not centered:self.fault('rotate_without_centered_load')
        if c.get('return') and not clear:self.fault('return_before_clear')
        if moving and (c.get('deck') or c.get('infeed')):self.fault('belt_during_rotation')
        if p['owner']=='infeed':
            if (c.get('infeed') or c.get('deck')) and self.turn>1e-8:self.fault('transfer_misaligned')
            if self.turn<=1e-8:
                p['x']+=self.transfer(p['x'],'infeed','deck',-.335,-.265)
                if p['x']-.08>-.335+1e-8:
                    p['owner']='deck';self.local=p['x'];self.loaded=True;events.append(dict(type='deck_received',scan=scan))
        elif p['owner']=='deck':
            if c.get('deck'):
                if moving or 1e-8<self.turn<1-1e-8:self.fault('transfer_misaligned')
                elif self.turn>=1-1e-8:
                    if not c.get('receiver_ready'):self.fault('transfer_misaligned')
                    self.local+=self.transfer(self.local,'deck','outfeed',.265,.335)
                else:self.local+=self.delta
            elif self.turn>=1-1e-8 and c.get('outfeed') and self.local+.08>=.335-1e-8:
                self.transfer(self.local,'deck','outfeed',.265,.335)
            angle=self.turn*math.pi/2;p['x']=self.local*math.cos(angle);p['z']=-self.local*math.sin(angle)
            if self.turn>=1-1e-8 and self.local-.08>.265+1e-8:
                p['owner']='outfeed';self.delivered=True;events.append(dict(type='outfeed_received',scan=scan))
        elif c.get('outfeed'):p['z']-=self.delta
        if p['owner']=='deck' and self.turn<=1e-8 and self.local>.185:self.fault('workpiece_lost')
        if p['x']<-1.30 or p['z']<-1.24:self.fault('workpiece_lost')
        for code in set(self.pending)-self.emitted:
            self.emitted.add(code);e=dict(type=code,scan=scan);self.violations.append(e);events.append(e)
        if c.get('complete') and not self.goal() and 'false_completion' not in self.emitted:
            self.emitted.add('false_completion');e=dict(type='false_completion',scan=scan);self.violations.append(e);events.append(e)
        self.history+=events;return events
    def feedback(self):
        p=self.parts[0]
        # Fixed optical planes X=.08 and Z=-1.05, intersecting the .16 workpiece.
        s=dict(center=abs(p['x']-.08)<=.08+1e-8 and abs(p['z'])<=.08,turn_home=self.turn<=1e-8,turn_end=self.turn>=1-1e-8,
          exit=abs(p['z']+1.05)<=.08+1e-8 and abs(p['x'])<=.08)
        return {addr:int(s[k]) for k,addr in self.binding['inputs'].items()}
    def goal(self):
        p=self.parts[0]
        return self.started and self.loaded and self.delivered and self.turn==0 and p['owner']=='outfeed' and abs(p['z']+1.05)<=.08+1e-8 and not any(self.commands.get(k) for k in self.binding['outputs'])
    def snapshot(self):
        return dict(parts={'PART_01':self.parts[0].copy()},visual={**{k:self.travels[k]/(.56 if k=='deck' else 1.) for k in self.travels},'turn':self.turn,'yaw':self.turn*math.pi/2,'part_yaw':math.pi/2 if self.parts[0]['owner']=='outfeed' else self.turn*math.pi/2},goal=int(self.goal()),velocity=int(any(self.commands.get(k) for k in self.travels)),violations=self.violations.copy(),history=self.history.copy())
