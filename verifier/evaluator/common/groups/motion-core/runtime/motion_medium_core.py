"""Inter-function Motion prototypes. Synthetic dynamics; no PLC stage in judgment."""
from copy import deepcopy
from math import ceil
from motion_precision_drive import PrecisionDrive, clamp
from motion_precision_geometry import InterferenceGeometry
from scan_runtime import parse_operand

VIOLATIONS = ('motion_without_request','conflicting_commands','reference_not_established',
 'command_out_of_range','travel_limit','docking_interference','head_collision',
 'premature_completion','result_not_held','completion_deadline_missed')

class MotionMediumPlant:
    def __init__(self, package, scenario):
        self.mode=package.plant['interactions'][0]['mode'];self.binding=package.binding
        self.c={**deepcopy(package.calibration),**scenario.get('parameters',{})}
        self.initial=scenario['initial'];self.drives={}
        for a,c in self.c['axes'].items():
            c=deepcopy(c); factor=self.c.get(a+'_response',1)
            c['speed_mm_s']*=factor;c['acceleration_mm_s2']*=factor
            if 'damping' in self.c and a=='s':c['damping_ratio']=self.c['damping']
            self.drives[a]=PrecisionDrive(self.initial[a],c)
        self.targets={a:self.initial.get('target_'+a,0) for a in self.drives}
        self.ref=self.initial.get('referenced',self.mode!='reference');self.offset=self.initial.get('raw_offset',12345)
        self.capture=None;self.home_busy=False;self.home_done=False;self.previous_home=False
        self.active=False;self.time_ms=0;self.active_ms=0;self.stable_ms=0;self.result_age_ms=0
        self.result_started=False;self.success=False;self.tick=0;self.events=[];self.seen=set();self.violations=[];self.raw={}
        scene=deepcopy(package.plant['scene'])
        for d in scene['devices']:
            if self.mode=='dock' and d['id'].startswith('DOCK_'):d['pos'][0]+=self.targets['s']/1000
        self.geometry=InterferenceGeometry(scene,package.plant['interactions'][0].get('collision_pairs',[]))
        self.min_gap=None;self.collision_details=[]

    def emit(self,name,**data):
        if name in self.seen:return
        self.seen.add(name);e=dict(type=name,scan=self.tick,**data);self.events.append(e)
        if name in VIOLATIONS:self.violations.append(e)

    def normalized(self):
        return {a:(.5+d.x/2050 if a in ('s','u') else d.x/(864 if a=='v' else 180)) for a,d in self.drives.items()}

    def good(self):
        return self.ref and all(abs(d.x-self.targets[a])<=self.c['position_window_mm'] and abs(d.v)<=1 for a,d in self.drives.items())

    def feedback(self):
        d=self.drives['s'];values=dict(referenced=int(self.ref),home_busy=int(self.home_busy),home_done=int(self.home_done),
          cam=int(0<=d.x<=20),fork_retracted=int('f' in self.drives and self.drives['f'].x<=.2 and abs(self.drives['f'].v)<=1),
          fork_inserted=int('f' in self.drives and abs(self.drives['f'].x-180)<=.2 and abs(self.drives['f'].v)<=1))
        for a,d in self.drives.items():
            values[a+'_position']=round(d.x*100);values[a+'_velocity']=round(d.v*100);values['target_'+a]=round(self.targets[a]*100)
        return {address:values[key] for key,address in self.binding['feedback'].items()}

    def read_commands(self,memory):
        values={k:memory.read_word(parse_operand(a)) if a.startswith('D') else memory.read_bit(parse_operand(a)) for k,a in self.binding['commands'].items()}
        values['request']=memory.read_bit(parse_operand(self.binding['external']['request']))
        values['result']=memory.read_bit(parse_operand(self.binding['result']['completion']))
        return values

    def apply_commands(self,commands):
        self.raw=dict(commands)
        if commands['request'] and not self.active:
            self.active=True;self.emit('request_accepted')
        if any(v for k,v in commands.items() if k.endswith('_enable') or k in ('home','extend','retract')) and not self.active:
            self.emit('motion_without_request')
        if self.mode=='reference':
            home=bool(commands['home'])
            if home and not self.previous_home:
                self.home_busy=True;self.home_done=False;self.capture=None;self.ref=False;self.emit('home_started')
            if not home and self.home_busy:self.home_busy=False
            self.previous_home=home
            if commands['s_enable'] and home:self.emit('conflicting_commands')
            if commands['s_enable'] and not self.ref:self.emit('reference_not_established')
        if self.mode=='dock' and commands['extend'] and commands['retract']:self.emit('conflicting_commands')
        for a,d in self.drives.items():
            if a=='f':
                en=commands['extend'] or commands['retract'];target=0 if commands['retract'] else 180
            else:en=commands[a+'_enable'];target=commands[a+'_target']/100
            low,high=self.c['ranges'][a]
            if en and not low<=target<=high:self.emit('command_out_of_range')
            if self.mode=='reference' and (not self.ref or commands['home']):en=False
            d.command(en,False,clamp(target,low,high))

    def step_devices(self,dt_ms):
        count=ceil(dt_ms/self.c['physics_step_ms']);dt=dt_ms/count/1000
        for _ in range(count):
            before=self.normalized()
            for a,d in self.drives.items():
                if self.mode=='reference' and a=='s' and self.home_busy:
                    old_x,old_v=d.x,d.v
                    desired=-self.c['home_speed_mm_s'] if self.capture is None else 0
                    d.v+=clamp(desired-d.v,-d.c['acceleration_mm_s2']*dt,d.c['acceleration_mm_s2']*dt)
                    d.x+=(old_v+d.v)*dt/2
                    if old_x>=0>d.x and self.capture is None:
                        self.capture=self.offset;self.emit('reference_captured',count=self.capture,position_mm=0)
                    if self.capture is not None and abs(d.v)<1e-9:
                        self.ref=True;self.home_busy=False;self.home_done=True;self.emit('reference_established',count=self.capture)
                else:d.step(dt)
                lo,hi=self.c['ranges'][a]
                if not lo-2<=d.x<=hi+2:self.emit('travel_limit',axis=a,position=d.x)
            if self.geometry.pairs:
                # Bound acceleration curvature between microstep endpoints.
                error=sum(d.c['acceleration_mm_s2'] for d in self.drives.values())*dt*dt/8000
                hits,gap=self.geometry.check(before,self.normalized(),error)
                self.min_gap=gap if self.min_gap is None else min(self.min_gap,gap)
                if hits:
                    self.collision_details=hits
                    self.emit('docking_interference' if self.mode=='dock' else 'head_collision',contacts=hits)
            self.time_ms+=dt*1000
            if self.active:self.active_ms+=dt*1000
            good=self.good();self.stable_ms=self.stable_ms+dt*1000 if good and self.active else 0
            if self.result_started:
                if not good:self.emit('result_not_held')
                self.result_age_ms=self.result_age_ms+dt*1000 if good and self.raw['result'] else 0
                if self.result_age_ms>=self.c['observation_ms']-1e-7 and not self.success:
                    self.success=True;self.emit('motion_medium_complete')

    def resolve_interactions(self,scan):
        if self.active_ms>self.c['ready_deadline_ms'] and not self.result_started:self.emit('completion_deadline_missed')
        events=self.events;self.events=[];self.tick=scan+1;return events

    def snapshot(self):
        n=self.normalized();axes={a:dict(position=n[a],actual_mm=d.x,velocity_mm_s=d.v,target_mm=self.targets[a]) for a,d in self.drives.items()}
        meta=dict(mode=self.mode,axes=axes,referenced=self.ref,home_busy=self.home_busy,home_done=self.home_done,
          raw_count=round(self.drives['s'].x*100)+self.offset,captured_count=self.capture,stable_ms=self.stable_ms,
          result_age_ms=self.result_age_ms,result_asserted=self.result_started,success=self.success,
          min_gap_mm=self.min_gap,violations=[e['type'] for e in self.violations])
        return dict(axes=axes,position=self.drives['s'].x,home_cam=int(0<=self.drives['s'].x<=20),
          dock_x=self.targets['s']/1000,motion_medium=meta,violations=deepcopy(self.violations))

    def check_completion_after_step(self):
        commands = self.raw
        if not self.result_started and self.active_ms > self.c['ready_deadline_ms'] + 1e-7: self.emit('completion_deadline_missed')
        if commands['result']:
            if not self.active or not self.good() or self.stable_ms<30-1e-7:
                self.emit('result_not_held' if self.result_started else 'premature_completion')
            elif not self.result_started:self.result_started=True;self.emit('result_asserted')
        elif self.result_started:self.emit('result_not_held')


