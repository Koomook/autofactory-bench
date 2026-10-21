"""Reduced-order Material cells: reusable actuators, geometric feedback and ownership.

No reference-program step counter is read by the plant. Not rigid-body dynamics.
"""
import math
from request_module import RequestModule
from plants import parse_operand


def clamp(x, a=0., b=1.):
    return max(a, min(b, x))


class MaterialMediumCellPlant:
    def __init__(self, mode, binding, calibration, parameters, factor=1.):
        self.mode, self.binding, self.parameters = mode, binding, parameters
        self.factor = factor
        self.axis_ms = float(calibration.get('axis_ms', 500))
        self.belt_speed = float(calibration.get('belt_units_per_second', 1))
        if min(self.axis_ms, self.belt_speed, factor) <= 0:
            raise ValueError('Material cell calibration must be positive')
        self.axes = dict(u=0., z=0., v=0., grip=0., clamp=0., push=0., gate=0., rear=1.)
        self.commands = {}
        self.operands = {k: parse_operand(v) for section in ('outputs', 'external') for k,v in binding[section].items()}
        self.operands['complete'] = parse_operand(binding['result']['completion'])
        self.parts = [dict(x=-.9,y=.68,z=0.,owner='source',status='idle')]
        self.flags = dict(acquired=False, clamped=False, inspected=False, delivered=False)
        self.inspect_ms = 0.
        self.pending, self.violations, self.emitted = [], [], set()
        self.travel = 0.
        self.request = bool(parameters.get('select_b', False))
        self.inspection = RequestModule(float(calibration.get('inspection_ms', 350))*factor, self.request)
        self.occupied = int(parameters.get('occupied_slot', 0))
        if mode == 'meter':
            self.parts = [dict(x=x,y=.68,z=0.,owner='belt',status='idle') for x in (-.12,-.55)]
        if mode in ('handoff','tray','storage','swivel'):
            self.parts[0].update(x=-.75)
            self.axes['z'] = 1.
            if mode == 'handoff':
                self.axes['grip']=1.;self.parts[0].update(y=1.28,owner='tool',status='held');self.flags['acquired']=True
            if mode == 'tray':
                self.parts.append(dict(x=-.75,y=.68,z=.38,owner='source',status='idle'))
            if mode == 'storage':
                self.parts.append(dict(x=.75 if self.occupied==0 else 1.15,y=.68,z=0.,owner='occupied',status='idle'))
            if mode == 'swivel':
                self.parts[0].update(x=.7,z=0.)
        self.active_part = None
        self.dt = 0.

    def read_commands(self, memory):
        return {k:int(memory.read_bit(op)) for k,op in self.operands.items()}

    def apply_commands(self, commands):
        self.commands = commands.copy()

    def fault(self, code):
        self.pending.append(code)

    def step_devices(self, dt_ms):
        self.dt = dt_ms
        self.pending = []
        c, a = self.commands, self.axes
        rate = dt_ms / (self.axis_ms * self.factor)
        old_u = a['u']
        for axis, fwd, back in [('u','right','left'),('z','up','down'),('grip','close','open'),
                                ('clamp','clamp_close','clamp_open'),('push','push','retract'),
                                ('gate','gate_open','gate_close'),('rear','rear_open','rear_close')]:
            if c.get(fwd) and c.get(back):
                self.fault('opposed_drives')
            else:
                a[axis] = clamp(a[axis] + rate * (c.get(fwd,0)-c.get(back,0)))
        if self.mode in ('tray','storage'):
            # An explicitly selected second point, not a different actuator per phase.
            target = 1. if c.get('slot_b') else .8
            if c.get('right'): a['u'] = max(old_u, min(a['u'], target))
        if self.mode=='tray':a['v']=clamp(a['v']+rate*(1 if c.get('source_b') else -1))
        if c.get('belt'): self.travel += dt_ms*self.belt_speed / (1000*self.factor)

    def tool_pose(self):
        a=self.axes
        if self.mode=='swivel':
            angle=-a['u']*math.pi/3
            return [.7*math.cos(angle),.68+.6*a['z'],-.7*math.sin(angle)]
        x=-.75+(1.9 if self.mode in ('tray','storage') else 1.5)*a['u']
        if self.mode in ('tray','storage'):
            # .8 is the first target at +.77; the second is at +1.15.
            x=-.75+1.9*a['u']
        return [x,.68+.6*a['z'], .38*a['v']]

    def resolve_interactions(self, scan):
        c,a,p=self.commands,self.axes,self.parts[0]
        delta=self.dt*self.belt_speed/(1000*self.factor)
        if self.mode in ('route','inspect'):
            if c.get('belt') and a['clamp']>.02: self.fault('belt_while_clamped')
            if c.get('belt') and a['push']>.02: self.fault('belt_while_pusher_extended')
            if c.get('belt') and abs(p['z'])<.02:
                p['x'] += delta
            if a['clamp']>=1-1e-8:
                if abs(p['x'])>.09: self.fault('clamp_without_workpiece')
                else:self.flags['clamped']=True
            if self.mode=='inspect':
                allowed=abs(p['x'])<=.09 and abs(p['z'])<.02 and a['clamp']>=1-1e-8 and not c.get('belt') and not c.get('push')
                for code in self.inspection.tick(c.get('inspect'),allowed,self.dt):
                    self.fault('inspection_without_fixture' if code=='request_without_fixture' else 'inspection_'+code)
                self.flags['inspected']=self.inspection.completed_count>0
            if a['push']>0:
                if abs(p['x'])>.09 and p['owner']!='side': self.fault('push_before_station')
                if not self.request:self.fault('wrong_route')
                if self.mode=='inspect' and not self.flags['inspected']:self.fault('route_before_result')
                if a['clamp']>.02:self.fault('push_while_clamped')
                if abs(p['x'])<=.09:
                    p['z']=min(p['z'],-.62*a['push']);p['owner']='side'
            if p['x']>.15 and abs(p['z'])<.02:
                if self.request:self.fault('wrong_route')
                if self.mode=='inspect' and not self.flags['inspected']:self.fault('route_before_result')
            if p['x']>1.4 or p['z']<-.8:self.fault('workpiece_lost')
        elif self.mode=='meter':
            if c.get('gate_open') and a['rear']>.01:self.fault('front_open_before_rear_closed')
            if c.get('gate_open') and not c.get('downstream_ready',True):self.fault('front_open_before_downstream_ready')
            if c.get('belt'):
                for i,part in enumerate(self.parts):
                    target=part['x']+delta
                    if a['gate']<1-1e-8 and part['x']<=-.08+1e-8:target=min(target,-.08)
                    if a['rear']<1-1e-8 and part['x']<=-.48+1e-8:target=min(target,-.48)
                    part['x']=target
            if self.parts[1]['x']>-.08:self.fault('second_piece_released')
            if self.parts[0]['x']>1.3:self.fault('workpiece_lost')
        elif self.mode=='cross':
            if c.get('belt'):
                if a['z']>.01:self.fault('infeed_at_wrong_height')
                p['x']+=delta
            if c.get('up') and abs(p['x'])>.06:self.fault('lift_before_centered')
            if abs(p['x'])<=.06:p['y']=.68+.12*a['z']
            if c.get('cross'):
                if a['z']<1-1e-8:self.fault('cross_before_lift')
                p['z']-=delta
            if abs(p['z'])>.9:self.fault('workpiece_lost')
        else:
            tool=self.tool_pose()
            # Moving source selector is a pneumatic side slide with its own endpoint.
            if self.mode=='tray':
                if bool(c.get('source_b')) != getattr(self,'source_b',False) and a['z']<.99:self.fault('source_shift_below_clearance')
                self.source_b=bool(c.get('source_b'))
            if (c.get('right') or c.get('left')) and a['z']<1-1e-8:self.fault('travel_below_clearance')
            for i,part in enumerate(self.parts):
                if part['owner']=='occupied':continue
                if part['owner']=='tool':
                    part.update(x=tool[0],y=tool[1],z=tool[2],status='held')
                    if a['grip']<.98:
                        supported=a['z']<=.01 and self.at_destination(part)
                        if self.mode=='handoff':supported=supported and a['clamp']>=1-1e-8
                        if supported:
                            if self.mode=='storage' and ((part['x']<.9)==(self.occupied==0)):self.fault('occupied_slot_overwrite')
                            part.update(owner='target',status='idle');self.flags['delivered']=True
                        else:
                            part.update(owner='floor',status='dropped');self.fault('unsupported_release')
                elif part['owner']=='source' and a['grip']>=1-1e-8:
                    if math.dist([part['x'],part['y'],part['z']],tool)<.035:
                        part.update(owner='tool',status='held');self.flags['acquired']=True
            if c.get('clamp_close'):
                if abs(tool[0]-.75)>.04 or a['z']>.02:self.fault('clamp_before_docking')
                elif a['clamp']>=1-1e-8:self.flags['clamped']=True
            for part in self.parts:
                if part['owner']=='floor':part['y']=max(.08,part['y']-2*delta)
            # Explicit occupied-slot and repeated-placement collision checking.
            for i,left in enumerate(self.parts):
                for right in self.parts[i+1:]:
                    if all(abs(left[k]-right[k])<.159 for k in ('x','y','z')):self.fault('workpiece_collision')
        events=[]
        for code in set(self.pending)-self.emitted:
            self.emitted.add(code);e=dict(type=code,scan=scan);events.append(e);self.violations.append(e)
        if c.get('complete') and not self.goal():
            if 'false_completion' not in self.emitted:
                self.emitted.add('false_completion');e=dict(type='false_completion',scan=scan);events.append(e);self.violations.append(e)
        return events

    def at_destination(self,part):
        if self.mode=='swivel':return abs(part['x']-.35)<.035 and abs(part['z']-.6062177826)<.035
        return abs(part['z'])<.035 and (abs(part['x']-.75)<.035 or (self.mode in ('tray','storage') and abs(part['x']-1.15)<.035))

    def goal(self):
        p,a=self.parts[0],self.axes
        off=not any(self.commands.get(k) for k in self.binding['outputs'] if k not in ('slot_b','source_b'))
        if not off:return False
        if self.mode in ('route','inspect'):
            return (self.mode!='inspect' or self.flags['inspected']) and a['push']<.01 and a['clamp']<.01 and (abs(p['z']+.62)<.02 if self.request else abs(p['x']-1.05)<.06)
        if self.mode=='meter':return self.parts[0]['x']>=.7 and self.parts[1]['x']<=-.48+1e-8 and a['gate']<.01 and a['rear']<.01
        if self.mode=='cross':return abs(p['z']+.75)<.05 and a['z']>.99
        movable=[p for p in self.parts if p['owner']!='occupied']
        return all(p['owner']=='target' for p in movable) and a['z']>.99 and a['grip']<.01

    def feedback(self):
        a,p=self.axes,self.parts[0]
        def occupied_at(x):
            return any(abs(part['x']-x)<.04 and abs(part['y']-.68)<.04 and abs(part['z'])<.04 for part in self.parts)
        states={**{f'{k}_home':v<=1e-8 for k,v in a.items()},**{f'{k}_end':v>=1-1e-8 for k,v in a.items()},
          'station':abs(p['x'])<=.025 and abs(p['z'])<.04,
          'exit':abs(p['x']-1.05)<.025,'side':p['z']<=-.615,
          'meter_exit':self.parts[0]['x']>=.7,'cross_exit':p['z']<=-.75,
          'inspection_done':self.inspection.done,'inspection_busy':self.inspection.busy,
          'select_b':self.inspection.result if self.mode=='inspect' else self.request,
          'slot_a':abs(a['u']-.8)<1e-8,'slot_b':a['u']>=1-1e-8,
          'slot_a_occupied':occupied_at(.77),'slot_b_occupied':occupied_at(1.15),
          'target_a':occupied_at(.77),'target_b':occupied_at(1.15),
          'loaded':any(p['owner']=='tool' for p in self.parts),
          'placed':any(self.at_destination(p) and abs(p['y']-.68)<.04 for p in self.parts)}
        return {address:int(states[key]) for key,address in self.binding['inputs'].items()}

    def snapshot(self):
        a=self.axes;tool=self.tool_pose()
        yaw=-a['u']*math.pi/3 if self.mode=='swivel' else 0
        def offset(x,z):
            return tool[0]+math.cos(yaw)*x+math.sin(yaw)*z, tool[2]-math.sin(yaw)*x+math.cos(yaw)*z
        sx,sz=offset(0,-.2);gx,gz=offset(-.04,.077);zx,zz=offset(.155,-.2)
        visual={**a,'belt':self.travel/2.6,'gate_display':1-a['gate'],'rear_display':1-a['rear'],
                'tool_x':tool[0],'tool_y':tool[1]+.23,'tool_z':tool[2],
                'swivel_arm_x':tool[0]/2-.14*math.sin(yaw),'swivel_arm_z':tool[2]/2-.14*math.cos(yaw),'swivel_angle':yaw,
                'turn':a['u'],'grip_sensor_x':gx,'grip_sensor_z':gz,'z_sensor_x':zx,'z_sensor_z':zz,
                'slide_x':sx,'slide_z':sz,'deck_y':.5+.12*a['z'],
                'source_shift':.38*a['v']}
        parts={f'PART_{i+1:02}':p.copy() for i,p in enumerate(self.parts)}
        return dict(visual=visual,parts=parts,velocity=int(bool(self.commands.get('belt'))),
                    goal=int(self.goal()),violations=self.violations.copy(), flags=self.flags.copy(),
                    inspection=dict(busy=int(self.inspection.busy),done=int(self.inspection.done),accepted=self.inspection.accepted))
