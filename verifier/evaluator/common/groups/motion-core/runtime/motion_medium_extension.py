"""Seven opt-in Motion L2 prototypes. Public synthetic drive and contact models.

Normal completion and violations depend on actual state, never PLC stage names.
"""
from copy import deepcopy
from math import ceil, pi, atan2
from motion_precision_drive import PrecisionDrive, clamp
from motion_precision_geometry import InterferenceGeometry
from scan_runtime import parse_operand

MODES={'registration','brake','gantry','velocity_capture','gear','flying','stop_relative'}
VIOLATIONS=('motion_without_request','conflicting_commands','command_out_of_range','travel_limit',
 'hard_stop_impact','premature_completion','result_not_held','completion_deadline_missed','registration_not_captured',
 'gravity_drop','drive_against_brake','brake_applied_while_moving','gantry_racking',
 'window_speed_violation','end_limit_crossed','wrong_gear_ratio','gear_tracking_lost',
 'uncoupled_before_span','position_while_geared','docking_interference','head_collision')

def angular_error(x,target):return (x-target+180)%360-180

class MotionMediumExtensionPlant:
    def __init__(self,package,scenario):
        self.mode=package.plant['interactions'][0]['mode'];assert self.mode in MODES
        self.binding=package.binding;self.c=deepcopy(package.calibration);self.c.update(scenario.get('parameters',{}));self.initial=scenario['initial']
        self.drives={}
        for a,c in self.c['axes'].items():
            cfg=deepcopy(c);factor=self.c.get(a+'_response',1)
            cfg['speed_mm_s']*=factor;cfg['acceleration_mm_s2']*=factor
            d=PrecisionDrive(self.initial[a],cfg);d.v=float(self.initial.get(a+'_velocity',0));self.drives[a]=d
        self.active=False;self.active_ms=0.;self.time_ms=0.;self.tick=0;self.events=[];self.seen=set();self.violations=[];self.raw={}
        self.stable_ms=0.;self.result_age_ms=0.;self.result_started=False;self.success=False
        self.capture=None;self.arm_previous=False;self.capture_word=self.initial.get('stale_capture',0)
        self.power_age=0.;self.power_ready=False;self.brake_closed=True;self.brake_age=0.;self.release_previous=False;self.brake_anchor=self.initial.get('v',0)
        self.window_entered=False;self.window_complete=False;self.window_samples=0
        self.geared=False;self.gear_in_previous=False;self.gear_out_previous=False;self.gear_ratio=1.;self.gear_s0=0.;self.gear_u0=0.;self.gear_age=0.;self.in_gear=False;self.gear_span=0.;self.gear_tracking_started=False;self.gear_cycle_complete=False
        self.leader_stopped=False;self.leader_stop_x=None
        self.min_gap=None;self.peak_skew=0.
        self.geometry=InterferenceGeometry(package.plant['scene'],package.plant['interactions'][0].get('collision_pairs',[]))

    def emit(self,name,**data):
        if name in self.seen:return
        self.seen.add(name);e=dict(type=name,scan=self.tick,**data);self.events.append(e)
        if name in VIOLATIONS:self.violations.append(e)

    def targets(self):
        i=self.initial;d=self.drives;m=self.mode
        if m=='registration':return dict(s=i['mark']+i['offset'])
        if m=='brake':return dict(v=i['target'])
        if m=='gantry':return dict(s=i['target'],u=i['target'])
        if m=='velocity_capture':return dict(s=i['target'])
        if m=='gear':return dict(s=i['park'],u=None)
        if m=='flying':return dict(s=d['u'].x,u=None,f=180)
        return dict(s=None,u=None if self.leader_stop_x is None else self.leader_stop_x-i['gap'])

    def normalized(self):
        if self.mode=='gear':return {a:d.x*pi/180 for a,d in self.drives.items()}
        return {a:(d.x/864 if a=='v' else d.x/180 if a=='f' else .5+d.x/2050) for a,d in self.drives.items()}

    def good(self):
        d=self.drives;i=self.initial;m=self.mode;t=self.targets()
        at=lambda a:abs(d[a].x-t[a])<=.2 and abs(d[a].v)<=1
        if m=='registration':return self.capture is not None and at('s')
        if m=='brake':return at('v') and self.brake_closed and not self.power_ready
        if m=='gantry':return at('s') and at('u')
        if m=='velocity_capture':return at('s') and self.window_complete
        if m=='gear':return self.gear_cycle_complete and not self.geared and abs(angular_error(d['s'].x,i['park']))<=.2 and abs(d['s'].v)<=1
        if m=='flying':return abs(d['s'].x-d['u'].x)<=.2 and abs(d['s'].v-d['u'].v)<=1 and at('f')
        return self.leader_stopped and abs(d['s'].v)<=1 and at('u')

    def feedback(self):
        i=self.initial;d=self.drives;v={}
        for a,axis in d.items():v[a+'_position']=round(axis.x*100);v[a+'_velocity']=round(axis.v*100)
        v.update(target=round(i.get('target',0)*100),offset=round(i.get('offset',0)*100),capture_valid=int(self.capture is not None),captured=round(self.capture_word*100),
          mark=int(self.mode=='registration' and i['mark']<=d['s'].x<=i['mark']+20),power_ready=int(self.power_ready),brake_closed=int(self.brake_closed),
          window_start=round(i.get('window_start',0)*100),window_end=round(i.get('window_end',0)*100),request_speed=round(i.get('speed',0)*100),
          park=round(i.get('park',0)*100),ratio=round(i.get('ratio',1)*1000),span=round(i.get('span',0)*100),in_gear=int(self.in_gear),coupled=int(self.geared),
          fork_inserted=int('f' in d and abs(d['f'].x-180)<=.2 and abs(d['f'].v)<=1),fork_retracted=int('f' in d and abs(d['f'].x)<=.2 and abs(d['f'].v)<=1),
          gap=round(i.get('gap',0)*100),leader_standstill=int(self.leader_stopped and abs(d['s'].v)<=1))
        return {a:v[k] for k,a in self.binding['feedback'].items()}

    def read_commands(self,memory):
        raw={k:memory.read_word(parse_operand(a)) if a.startswith('D') else memory.read_bit(parse_operand(a)) for k,a in self.binding['commands'].items()}
        raw['request']=memory.read_bit(parse_operand(self.binding['external']['request']));raw['result']=memory.read_bit(parse_operand(self.binding['result']['completion']));return raw

    def apply_commands(self,raw):
        self.raw=dict(raw);m=self.mode
        if raw['request'] and not self.active:self.active=True;self.emit('request_accepted')
        for k,(lo,hi) in self.c['command_ranges'].items():
            if self.mode=='gear' and k=='gear_ratio' and not raw['gear_in']: continue  # value is latched only by gear-in
            if not lo<=raw[k]<=hi:self.emit('command_out_of_range',command=k,value=raw[k])
        movement=any(raw.get(k,0) for k in self.c['request_commands'])
        if movement and not self.active:self.emit('motion_without_request')
        if m=='registration':
            arm=bool(raw['arm'])
            if arm and not self.arm_previous:self.capture=None
            self.arm_previous=arm
            if raw['mode']==2 and self.capture is None:self.emit('registration_not_captured')
        if m=='gear':
            gin,gout=bool(raw['gear_in']),bool(raw['gear_out'])
            if gin and not self.gear_in_previous and gout and not self.gear_out_previous:self.emit('conflicting_commands')
            if gin and not self.gear_in_previous:
                self.geared=True;self.in_gear=False;self.gear_age=0;self.gear_span=0;self.gear_tracking_started=False;self.gear_cycle_complete=False
                self.gear_ratio=raw['gear_ratio']/1000;self.gear_s0=self.drives['s'].x;self.gear_u0=self.drives['u'].x
                self.emit('gear_engagement_started')
                if abs(self.gear_ratio-self.initial['ratio'])>1e-9:self.emit('wrong_gear_ratio')
            if gout and not self.gear_out_previous and self.geared:
                if self.gear_span+1e-7<self.initial['span']:self.emit('uncoupled_before_span',master_span_deg=self.gear_span)
                else:self.gear_cycle_complete=True
                self.geared=False;self.in_gear=False;self.emit('gear_disengaged',follower_velocity=self.drives['s'].v)
            self.gear_in_previous=gin;self.gear_out_previous=gout
            if self.geared and raw['park_enable']:self.emit('position_while_geared')

    def integrate(self,a,acceleration,dt):
        d=self.drives[a];old=d.v;d.v+=acceleration*dt;d.x+=(old+d.v)*dt/2

    def velocity(self,a,target,dt,rate=None):
        d=self.drives[a];rate=rate or d.c['acceleration_mm_s2'];self.integrate(a,clamp((target-d.v)/dt,-rate,rate),dt)

    def position(self,a,target,enabled,dt,ff=None):
        d=self.drives[a]
        if ff is None:d.command(enabled,False,target);d.step(dt);return
        c=d.c;accel=clamp(c['natural_frequency_rad_s']**2*(target-d.x)+2*c['damping_ratio']*c['natural_frequency_rad_s']*(ff-d.v),-c['acceleration_mm_s2'],c['acceleration_mm_s2'])
        desired=clamp(d.v+accel*dt,-c['speed_mm_s'],c['speed_mm_s']);self.integrate(a,(desired-d.v)/dt,dt)

    def step_devices(self,dt_ms):
        count=ceil(dt_ms/self.c['physics_step_ms']);dt=dt_ms/count/1000;m=self.mode;r=self.raw;i=self.initial;d=self.drives
        for j in range(count):
            before=self.normalized()
            if m=='registration':
                old=d['s'].x
                if r['mode']==1:self.velocity('s',clamp(r['speed']/100,0,300),dt)
                else:self.position('s',clamp(r['target']/100,-1000,1000),r['mode']==2,dt)
                if old<i['mark']<=d['s'].x and r['arm'] and self.capture is None:
                    self.capture=i['mark'];self.capture_word=self.capture;self.emit('position_registered',position_mm=self.capture)
            elif m=='brake':
                self.power_age=self.power_age+dt*1000 if r['power'] else 0;self.power_ready=self.power_age>=self.c['power_delay_ms']-1e-7
                release=bool(r['release'])
                if release!=self.release_previous:self.brake_age=0;self.release_previous=release
                self.brake_age+=dt*1000
                delay=self.c['brake_open_ms'] if release else self.c['brake_close_ms']
                if self.brake_age>=delay-1e-7 and self.brake_closed==release:
                    self.brake_closed=not release
                    if self.brake_closed and abs(d['v'].v)>1:self.emit('brake_applied_while_moving',velocity=d['v'].v)
                    self.emit('brake_released' if release else 'brake_engaged')
                if self.brake_closed:
                    if self.power_ready and r['move'] and abs(r['target']/100-d['v'].x)>.2:self.emit('drive_against_brake')
                    self.velocity('v',0,dt,self.c['brake_deceleration'])
                elif self.power_ready:self.position('v',r['target']/100,r['move'],dt)
                else:
                    self.integrate('v',-self.c['gravity_mm_s2'],dt)
                    if abs(d['v'].v)>1:self.emit('gravity_drop',position_mm=d['v'].x,velocity_mm_s=d['v'].v)
            elif m=='gantry':
                for a in ('s','u'):self.position(a,r[a+'_target']/100,r['move'],dt)
                skew=abs(d['s'].x-d['u'].x);self.peak_skew=max(self.peak_skew,skew)
                if skew>self.c['skew_limit_mm']:self.emit('gantry_racking',skew_mm=skew)
            elif m=='velocity_capture':
                old=d['s'].x
                if r['mode']==1:self.velocity('s',clamp(r['speed']/100,0,self.c['command_ranges']['speed'][1]/100),dt,self.c['velocity_acceleration'])
                else:self.position('s',r['target']/100,r['mode']==2,dt)
                if max(old,d['s'].x)>=i['window_start'] and min(old,d['s'].x)<=i['window_end']:
                    self.window_entered=True;self.window_samples+=1
                    if abs(d['s'].v-i['speed'])>3:self.emit('window_speed_violation',position_mm=d['s'].x,velocity_mm_s=d['s'].v)
                if old<=i['window_end']<d['s'].x and self.window_entered:self.window_complete=True;self.emit('rate_window_completed')
                if d['s'].x>i['limit']:self.emit('end_limit_crossed',position_mm=d['s'].x)
            elif m=='gear':
                master_before=d['u'].x;self.integrate('u',0,dt)
                if self.geared:
                    target=self.gear_s0+self.gear_ratio*(master_before-self.gear_u0)
                    self.position('s',target,True,dt,ff=self.gear_ratio*d['u'].v)
                    error=d['s'].x-(self.gear_s0+self.gear_ratio*(d['u'].x-self.gear_u0));good=abs(error)<=.4 and abs(d['s'].v-self.gear_ratio*d['u'].v)<=2
                    self.gear_age=self.gear_age+dt*1000 if good else 0
                    self.in_gear=self.gear_age>=30-1e-7
                    if self.in_gear and not self.gear_tracking_started:self.gear_tracking_started=True;self.emit('gear_synchronized')
                    if self.gear_tracking_started:
                        if not good:self.emit('gear_tracking_lost')
                        if good:self.gear_span+=d['u'].x-master_before
                elif r['park_enable']:self.position('s',r['park_target']/100,True,dt)
                else:self.integrate('s',0,dt)  # GearOut does not stop a moving follower.
            elif m=='flying':
                self.integrate('u',0,dt)
                if r['follow']:self.position('s',r['follow_target']/100+r['feedforward']/100*j*dt,True,dt,ff=r['feedforward']/100)
                else:self.velocity('s',0,dt,d['s'].c['braking_mm_s2'])
                self.position('f',180 if r['extend'] else 0,True,dt)
                if d['f'].x>before['f']*180+1e-9 and (abs(d['s'].x-d['u'].x)>.2+1e-7 or abs(d['s'].v-d['u'].v)>1+1e-7):self.emit('insertion_alignment_missing')
            else:
                if r['leader_stop']:self.velocity('s',0,dt,self.c['leader_deceleration'])
                else:self.integrate('s',0,dt)
                if r['rear_mode']==1:self.velocity('u',0,dt,self.c['rear_deceleration'])
                elif r['rear_mode']==2:self.position('u',r['rear_target']/100,True,dt)
                else:self.integrate('u',0,dt)
                if self.active and abs(d['s'].v)<1e-7 and not self.leader_stopped:
                    self.leader_stopped=True;self.leader_stop_x=d['s'].x;self.emit('leader_stopped',position_mm=self.leader_stop_x)
                if d['s'].x>i['limit']:self.emit('end_limit_crossed',axis='s',position_mm=d['s'].x)
            if self.geometry.pairs:
                error=sum(a.c['acceleration_mm_s2'] for a in d.values())*dt*dt/8000
                hits,gap=self.geometry.check(before,self.normalized(),error)
                self.min_gap=gap if self.min_gap is None else min(self.min_gap,gap)
                if hits:self.emit('docking_interference' if m=='flying' else 'head_collision',contacts=hits)
            for a,axis in d.items():
                if m!='gear':
                    low,high=self.c['travel_ranges'][a]
                    if not low<=axis.x<=high:
                        self.emit('travel_limit',axis=a,position_mm=axis.x)
                        self.emit('hard_stop_impact',axis=a,velocity=axis.v)
                        axis.x=clamp(axis.x,low,high);axis.v=0
            self.time_ms+=dt*1000
            if self.active:self.active_ms+=dt*1000
            good=self.good();self.stable_ms=self.stable_ms+dt*1000 if good and self.active else 0
            if self.result_started:
                if not good:self.emit('result_not_held')
                self.result_age_ms=self.result_age_ms+dt*1000 if good and r['result'] else 0
                if self.result_age_ms>=100-1e-7 and not self.success:self.success=True;self.emit('motion_medium_complete')

    def resolve_interactions(self,scan):
        if self.active_ms>self.c['ready_deadline_ms'] and not self.result_started:self.emit('completion_deadline_missed')
        events=self.events;self.events=[];self.tick=scan+1;return events

    def snapshot(self):
        n=self.normalized();targets=self.targets();d=self.drives;m=self.mode;i=self.initial
        axes={a:dict(position=n[a],**({'actual_deg':axis.x,'velocity_deg_s':axis.v,'target_deg':targets[a]} if m=='gear' else {'actual_mm':axis.x,'velocity_mm_s':axis.v,'target_mm':targets[a]})) for a,axis in d.items()}
        diagnostics={
          'registration':dict(capture_mm=self.capture,capture_valid=self.capture is not None),
          'brake':dict(power_ready=self.power_ready,brake_closed=self.brake_closed),
          'gantry':dict(skew_mm=d['s'].x-d['u'].x,peak_skew_mm=self.peak_skew) if m=='gantry' else {},
          'velocity_capture':dict(window_complete=self.window_complete,window_start=i.get('window_start'),window_end=i.get('window_end'),request_speed=i.get('speed')),
          'gear':dict(geared=self.geared,in_gear=self.in_gear,master_span_deg=self.gear_span,requested_span_deg=i.get('span'),ratio=i.get('ratio')),
          'flying':dict(relative_error_mm=d['s'].x-d['u'].x,relative_velocity_mm_s=d['s'].v-d['u'].v) if m=='flying' else {},
          'stop_relative':dict(leader_stopped=self.leader_stopped,leader_stop_mm=self.leader_stop_x,gap_mm=d['s'].x-d['u'].x) if m=='stop_relative' else {}}
        meta=dict(mode=m,axes=axes,referenced=True,home_busy=False,home_done=False,raw_count=0,captured_count=None,stable_ms=self.stable_ms,result_age_ms=self.result_age_ms,
          result_asserted=self.result_started,success=self.success,min_gap_mm=self.min_gap,violations=[e['type'] for e in self.violations],diagnostics=diagnostics[m])
        return dict(axes=axes,motion_medium=meta,position=d.get('s',d.get('v')).x,mark_x=i.get('mark',0)/1000,
          beam_x=(d['s'].x+d['u'].x)/2000 if m=='gantry' else 0,beam_yaw=atan2((d['u'].x-d['s'].x)/1000,1.2) if m=='gantry' else 0,
          window_start_x=i.get('window_start',0)/1000,window_end_x=i.get('window_end',0)/1000,limit_x=i.get('limit',0)/1000,brake=int(self.brake_closed),power=int(self.power_ready),violations=deepcopy(self.violations))

    def check_completion_after_step(self):
        raw = self.raw
        if not self.result_started and self.active_ms > self.c['ready_deadline_ms'] + 1e-7: self.emit('completion_deadline_missed')
        if raw['result']:
            if not self.active or not self.good() or self.stable_ms<30-1e-7:self.emit('result_not_held' if self.result_started else 'premature_completion')
            elif not self.result_started:self.result_started=True;self.emit('result_asserted')
        elif self.result_started:self.emit('result_not_held')


