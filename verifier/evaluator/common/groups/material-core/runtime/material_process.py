"""Four bounded material-flow episodes; synthetic contact/transport, no PLC-step access.

Lengths are metres. Parts are .16 m cubes. Piece motion is derived from drive
commands and contact geometry. Receiving belts are explicit external equipment,
not silently controlled by a reference program. No force/slip dynamics claimed.
"""
from material_medium_cells import MaterialMediumCellPlant, clamp

FAULTS = ['opposed_drives', 'operation_without_request', 'feed_without_permission',
          'duplicate_supply', 'belt_before_feeder_clear', 'feed_stroke_incomplete',
          'refill_before_zone_clear', 'receiver_not_ready', 'second_piece_released',
          'batch_before_full', 'belt_while_pusher_extended', 'push_without_receiver',
          'gap_too_small', 'transfer_drive_mismatch', 'part_overlap',
          'workpiece_lost', 'false_completion']


class MaterialProcessPlant(MaterialMediumCellPlant):
    def __init__(self, mode, binding, calibration, parameters, factor=1.):
        super().__init__(mode, binding, calibration, parameters, factor)
        self.axes = {'push': 0.}
        self.started = False
        self.fed = False
        self.fully_extended = False
        self.accepted = []
        self.history = []
        self.travel_a = self.travel_b = 0.
        self.travel_receiver = 0.
        self.last_exit_fall = None
        self.last_exit = False
        self.gaps = []
        self.time = 0.
        self.speed_factor = float(parameters.get('speed_factor', 1.))
        if self.speed_factor <= 0: raise ValueError('Positive speed factor required')
        part = lambda x, y=.68, owner='belt': dict(x=x,y=y,z=0.,owner=owner,status='idle')
        offset = float(parameters.get('source_offset', 0.))
        if mode == 'replenish':
            self.parts = [part(-.65, owner='magazine'), part(-.65,.84,'reserve')]
        elif mode == 'zone':
            self.parts = [part(.72,owner='zone_b'), part(-.50+offset,owner='zone_a')]
        elif mode == 'batch':
            self.parts = [part(x+offset) for x in (-.30,-.70,-1.10)]
        elif mode == 'pace':
            self.parts = [part(-.50+offset),part(-.68+offset)]
        else: raise ValueError(mode)

    def step_devices(self, dt_ms):
        self.dt = dt_ms
        self.time += dt_ms / 1000
        self.pending = []
        c = self.commands
        self.started |= bool(c.get('start'))
        if any(c.get(k) for k in self.binding['outputs']) and not self.started:
            self.fault('operation_without_request')
        self.previous_push = self.axes['push']
        if c.get('extend') and c.get('retract'): self.fault('opposed_drives')
        else: self.axes['push'] = clamp(self.axes['push'] + dt_ms/(self.axis_ms*self.factor)*(c.get('extend',0)-c.get('retract',0)))
        self.da = dt_ms/1000*self.belt_speed*self.speed_factor*bool(c.get('belt_a'))
        pace_speed = (1. if c.get('fast') else .4) if self.mode=='pace' else self.belt_speed
        self.db = dt_ms/1000*pace_speed*self.speed_factor*bool(c.get('belt_b'))
        self.travel_a += self.da
        self.travel_b += self.db
        if any(p['owner']=='receiver' and (p['x']<1.90 if self.mode=='zone' else len(self.accepted)<2) for p in self.parts):
            self.travel_receiver += dt_ms/1000*self.speed_factor

    @staticmethod
    def photo(part, x):
        return abs(part['x']-x) <= .08000001 and abs(part['z']) < .08

    def event(self, name, scan, **extra):
        self.history.append(dict(type=name,scan=scan,**extra))

    def resolve_interactions(self, scan):
        c, a = self.commands, self.axes['push']
        before = len(self.history)
        if self.mode == 'replenish':
            p, reserve = self.parts
            if c.get('extend') and not c.get('ready'): self.fault('feed_without_permission')
            if c.get('extend') and self.fed and self.previous_push < .999: self.fault('duplicate_supply')
            # Ejector face touches the cube's left face; its trailing shoe supports
            # the reserve until retracted. No reserve teleports through the rod.
            face = -.73 + .45*a
            if p['owner']=='magazine':
                p['x'] = max(p['x'],face+.08)
                if a >= 1-1e-8:
                    p['owner']='belt';self.fed=True;self.fully_extended=True
                    self.event('single_part_ejected',scan)
            if c.get('retract') and p['x']>-.65+1e-8 and not self.fully_extended:
                self.fault('feed_stroke_incomplete')
            if self.fed and a <= 1e-8:
                reserve['y']=max(.68,reserve['y']-self.dt/1000*.8)
            if c.get('belt_a'):
                if a > 1e-8:self.fault('belt_before_feeder_clear')
                if p['owner']=='belt':p['x'] += self.da
            if p['x'] > 1.22:self.fault('workpiece_lost')
        elif self.mode == 'zone':
            first, second = self.parts
            if c.get('belt_a') and not self.accepted:self.fault('refill_before_zone_clear')
            for i,p in enumerate(self.parts):
                if p['owner']=='receiver':
                    p['x']=min(1.90,p['x']+self.dt/1000*self.speed_factor)
                    continue
                if p['x'] < 0:
                    if p['x']+.08 >= -.02 and c.get('belt_a') and not c.get('belt_b'):
                        self.fault('transfer_drive_mismatch')
                    p['x'] += self.da
                else:p['x'] += self.db
                if p['x']+.08 >= 1.24 and c.get('belt_b') and not c.get('ready'):
                    self.fault('receiver_not_ready')
                if p['x']-.08 >= 1.24:
                    if i==1:self.fault('second_piece_released')
                    p['owner']='receiver';self.accepted.append(i)
                    self.event('receiver_acquired',scan,part=i)
                elif p['x'] >= .02:p['owner']='zone_b'
            if second['x'] > .80:self.fault('second_piece_released')
        elif self.mode == 'batch':
            if c.get('belt_a') and a>1e-8:self.fault('belt_while_pusher_extended')
            for i,p in enumerate(self.parts):
                if abs(p['z'])<.001 and c.get('belt_a'):
                    # The end stop and preceding workpiece stop accumulation.
                    limit=.80 if i==0 else self.parts[i-1]['x']-.16
                    p['x']=min(limit,p['x']+self.da)
            ready=self.batch_present()
            if c.get('extend'):
                if not ready:self.fault('batch_before_full')
                if not c.get('ready'):self.fault('push_without_receiver')
            face=.20-.80*a
            for p in self.parts:
                if .20 <= p['x']-.08 and p['x']+.08 <= 1.00:
                    p['z']=min(p['z'],face-.08) if face <= p['z']+.08 else p['z']
                    if p['z']+.08<=-.30 and p['owner']!='tray':
                        p['owner']='tray';self.event('batch_member_on_tray',scan)
            if any(p['z']<-.80 for p in self.parts):self.fault('workpiece_lost')
        else:
            old=self.last_exit
            for i,p in enumerate(self.parts):
                if p['owner']=='receiver':
                    if len(self.accepted)<2:p['x']+=self.dt/1000*self.speed_factor
                    if p['x']>2.74:self.fault('workpiece_lost')
                    continue
                if c.get('belt_a') and not c.get('ready'):self.fault('receiver_not_ready')
                if p['x'] < 0:
                    if p['x']+.08>=-.02 and c.get('belt_a') and not c.get('belt_b'):
                        self.fault('transfer_drive_mismatch')
                    p['x'] += self.da
                else:p['x'] += self.db
                if p['x']-.08>=1.42:
                    if not c.get('ready'):self.fault('receiver_not_ready')
                    p['owner']='receiver';self.accepted.append(i)
                    self.event('paced_part_received',scan,part=i)
            active=any(self.photo(p,1.40) for p in self.parts)
            if old and not active:self.last_exit_fall=self.time
            if active and not old and self.last_exit_fall is not None:
                gap=(self.time-self.last_exit_fall)*self.speed_factor
                self.gaps.append(gap)
                if gap < .20-1e-8:self.fault('gap_too_small')
                self.event('gap_observed',scan,gap_m=gap)
            self.last_exit=active
        # Explicit overlap audit; expected contact at an accumulation stop is OK.
        for i,p in enumerate(self.parts):
            for q in self.parts[i+1:]:
                if all(abs(p[k]-q[k])<.16-1e-7 for k in 'xyz'):self.fault('part_overlap')
        for code in set(self.pending)-self.emitted:
            self.emitted.add(code);e=dict(type=code,scan=scan);self.violations.append(e);self.history.append(e)
        if c.get('complete') and not self.goal() and 'false_completion' not in self.emitted:
            self.emitted.add('false_completion');e=dict(type='false_completion',scan=scan)
            self.violations.append(e);self.history.append(e)
        return self.history[before:]

    def batch_present(self):
        # Three spatially disjoint photoeye planes, not a hidden PLC counter.
        return all(any(abs(p['x']-x)<=.08+1e-8 for p in self.parts) for x in (.42,.62,.82))

    def feedback(self):
        p=self.parts[0];a=self.axes['push']
        s={'home':a<=1e-8,'end':a>=1-1e-8}
        if self.mode=='replenish':s.update(pickup=self.photo(p,.85),stock=any(
          abs(q['x']+.65)<=.08000001 and abs(q['y']-.73)<=.08000001 and abs(q['z'])<.08
          for q in self.parts))
        elif self.mode=='zone':s.update(front=any(self.photo(q,.80) for q in self.parts),
          entry=any(self.photo(q,-.42) for q in self.parts),exit=any(self.photo(q,1.40) for q in self.parts),
          received=self.photo(p,1.95))
        elif self.mode=='batch':s.update(count=any(self.photo(q,0.) for q in self.parts),
          **{f'nest_{i+1}':any(abs(q['x']-x)<=.08000001 and -.85<q['z']<.08 for q in self.parts) for i,x in enumerate((.42,.62,.82))},
          tray=all(q['z']<=-.60 for q in self.parts))
        else:s.update(entry=any(self.photo(q,-.10) for q in self.parts),exit=any(self.photo(q,1.40) for q in self.parts),
          received=len(self.accepted)==2)
        return {addr:int(s[key]) for key,addr in self.binding['inputs'].items()}

    def goal(self):
        if not self.started or any(self.commands.get(k) for k in self.binding['outputs']):return False
        p=self.parts[0];a=self.axes['push']
        if self.mode=='replenish':return self.fed and self.photo(p,.85) and a<=1e-8 and self.parts[1]['y']<=.680001
        if self.mode=='zone':return self.accepted==[0] and self.photo(p,1.95) and self.photo(self.parts[1],.80)
        if self.mode=='batch':return all(q['owner']=='tray' and q['z']<=-.60 for q in self.parts) and a<=1e-8
        return len(self.accepted)==2 and len(self.gaps)==1 and self.gaps[0]>=.20-1e-8

    def snapshot(self):
        lengths={'replenish':(1.6,1),'zone':(1.2,1.2),'batch':(2.6,1),'pace':(1.4,1.4)}[self.mode]
        return dict(parts={f'PART_{i+1:02}':p.copy() for i,p in enumerate(self.parts)},
          visual=dict(push=self.axes['push'],belt_a=self.travel_a/lengths[0],belt_b=self.travel_b/lengths[1],receiver=self.travel_receiver/1.4),
          velocity=int(bool(self.commands.get('belt_a') or self.commands.get('belt_b'))),
          goal=int(self.goal()),violations=self.violations.copy(),history=self.history.copy(),
          accepted=self.accepted.copy(),measured_gaps=self.gaps.copy(),time_s=self.time)
