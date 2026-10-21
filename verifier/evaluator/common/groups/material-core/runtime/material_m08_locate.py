"""One pallet lift-and-locate station; explicit support geometry and local I/O.

Fixed twin belts support a pallet. Only the locating plate/pallet lifts, by 35 mm
above transport level. V2 performs datum-referenced geometric contact gauging;
V1 retains its abstract work interface. Neither claims full dynamics or actual
metrology accuracy. The gauge's result is scoped to the current request.
"""
from material_medium_cells import MaterialMediumCellPlant, clamp
from request_module import RequestModule
from contact_height_probe import ContactHeightProbe, HOME_TIP

BELT_TOP = .6
PALLET_THICKNESS = .05
LOCATOR_HOME_TOP = .575
LOCATOR_TRAVEL = .06
PIN_HEIGHT = .015
PART_HALF = .08
FAULTS = ['opposed_drives', 'lift_without_docked_pallet', 'belt_before_locator_home',
          'work_without_location', 'work_request_aborted', 'location_lost_during_work',
          'lower_before_work_done', 'release_before_work_done', 'release_with_locator_engaged',
          'stopper_into_pallet', 'unprocessed_departure', 'workpiece_lost', 'false_completion',
          'probe_no_contact','probe_contact_lost','height_check_failed','transport_with_probe_down']


class PalletLocatePlant(MaterialMediumCellPlant):
    def __init__(self, mode, binding, calibration, parameters, factor=1.):
        super().__init__(mode, binding, calibration, parameters, factor)
        self.axes = dict(lift=0., gate=1.)
        self.parts = [dict(x=float(parameters.get('initial_x', -1.)), y=.73, z=0.,
                           owner='pallet', status='idle')]
        if not -1.1 <= self.parts[0]['x'] <= -.6:
            raise ValueError('initial pallet must fit the infeed')
        self.work = RequestModule(float(parameters.get('work_ms', calibration['work_ms'])), False)
        self.gauge_enabled='probe_speed' in calibration
        if self.gauge_enabled:self.work=ContactHeightProbe(calibration['probe_speed']/self.factor,parameters.get('settle_ms',80))
        self.exit_x=float(calibration.get('exit_x',1.03))
        self.conveyor_length=float(calibration.get('conveyor_length',2.8))
        self.processed = False
        self.support = 'belts'
        self.history = []
        self.old_support = self.support

    @property
    def plate_top(self):
        return LOCATOR_HOME_TOP + LOCATOR_TRAVEL*self.axes['lift']

    @property
    def pallet_bottom(self):
        return max(BELT_TOP, self.plate_top) if abs(self.parts[0]['x']) <= 1e-8 else BELT_TOP

    def step_devices(self, dt_ms):
        self.dt, self.pending = dt_ms, []
        c, a = self.commands, self.axes
        if c.get('up') and (abs(self.parts[0]['x']) > 1e-8 or a['gate'] < 1-1e-8):
            self.fault('lift_without_docked_pallet')
        if c.get('belt') and a['lift'] > 1e-8:
            self.fault('belt_before_locator_home')
        if self.gauge_enabled and (c.get('belt') or c.get('down')) and self.work.tip<HOME_TIP-1e-8:
            self.fault('transport_with_probe_down')
        if c.get('down') and a['lift'] > 0 and (not self.processed or self.work.busy):
            self.fault('lower_before_work_done')
        if c.get('gate_down'):
            if not self.processed: self.fault('release_before_work_done')
            if a['lift'] > 1e-8: self.fault('release_with_locator_engaged')
        if c.get('gate_up') and 0 < self.parts[0]['x'] < .4:
            self.fault('stopper_into_pallet')
        rate = dt_ms/(self.axis_ms*self.factor)
        for key, up, down in [('lift','up','down'),('gate','gate_up','gate_down')]:
            if c.get(up) and c.get(down): self.fault('opposed_drives')
            else: a[key] = clamp(a[key]+rate*(c.get(up,0)-c.get(down,0)))

    def resolve_interactions(self, scan):
        c,a,p = self.commands,self.axes,self.parts[0]
        docked = abs(p['x']) <= 1e-8
        # A locating pin in the pallet bore prevents horizontal motion, even if
        # an incorrect PLC command energizes the slipping transport belt.
        pins_engaged = docked and self.plate_top + PIN_HEIGHT > BELT_TOP
        if c.get('belt'):
            self.travel += self.dt*self.belt_speed/1000/self.factor
            if a['lift'] > 1e-8: self.fault('belt_before_locator_home')
            if not pins_engaged:
                target = p['x'] + self.dt*self.belt_speed/1000/self.factor
                if a['gate'] > 1e-8 and p['x'] <= 0: target = min(0.,target)
                p['x'] = target
        docked = abs(p['x']) <= 1e-8
        self.support = 'locator' if docked and self.plate_top > BELT_TOP+1e-8 else 'belts'
        if self.support != self.old_support:
            self.history.append(dict(type='support_'+self.support,scan=scan))
            self.old_support = self.support
        p['y'] = self.pallet_bottom + PALLET_THICKNESS + PART_HALF
        located = docked and a['lift'] >= 1-1e-8 and a['gate'] >= 1-1e-8 and not c.get('belt')
        mapping = {'request_without_fixture':'work_without_location', 'request_aborted':'work_request_aborted',
                   'fixture_lost_during_request':'location_lost_during_work'}
        if self.gauge_enabled:
            previous_contacts=self.work.contact_count
            # PLC is responsible for location interlocks. Do not invisibly
            # prevent an erroneous request: the independent gauge will measure
            # the actual surface at the wrong datum and return a bad result.
            if c.get('work') and not located:self.fault('work_without_location')
            if self.work.busy and not located:self.fault('location_lost_during_work')
            for code in self.work.tick(c.get('work'),bool(c.get('work_ready')),self.dt,p):self.fault(code)
            if self.work.contact_count>previous_contacts:self.history.append(dict(type='height_probe_contact',scan=scan))
            if self.work.contact and self.work.bad:self.fault('height_check_failed')
        else:
            for code in self.work.tick(c.get('work'), located and bool(c.get('work_ready')), self.dt):self.fault(mapping[code])
        if self.work.completed_count and not self.processed and (not self.gauge_enabled or self.work.good):
            self.processed=True
            self.history.append(dict(type='height_inspection_completed' if self.gauge_enabled else 'work_completed',scan=scan))
        if p['x'] > .01 and not self.processed: self.fault('unprocessed_departure')
        if p['x'] > 1.25: self.fault('workpiece_lost')
        if c.get('complete') and not self.goal(): self.fault('false_completion')
        events=[]
        for code in sorted(set(self.pending)-self.emitted):
            self.emitted.add(code);e=dict(type=code,scan=scan);events.append(e);self.violations.append(e)
        events.extend(e for e in self.history if e['scan']==scan)
        return events

    def feedback(self):
        a,p=self.axes,self.parts[0]
        states=dict(station=abs(p['x'])<=1e-8, lift_home=a['lift']<=1e-8,lift_up=a['lift']>=1-1e-8,
                    gate_home=a['gate']<=1e-8,gate_up=a['gate']>=1-1e-8,
                    work_busy=self.work.busy,work_done=self.work.done,
                    exit=abs(p['x']-self.exit_x)<=PART_HALF)
        if self.gauge_enabled:states.update(probe_home=self.work.tip>=HOME_TIP-1e-8,
                    probe_contact=self.work.contact,inspection_ok=self.work.done and self.work.good)
        return {addr:int(states[key]) for key,addr in self.binding['inputs'].items()}

    def goal(self):
        p,a=self.parts[0],self.axes
        return bool(self.processed and self.exit_x-.08-1e-8<=p['x']<=self.exit_x+.08 and a['lift']<=1e-8 and a['gate']>=1-1e-8
                    and (not self.gauge_enabled or self.work.tip>=HOME_TIP-1e-8)
                    and self.support=='belts' and not any(self.commands.get(k) for k in self.binding['outputs']))

    def snapshot(self):
        p=self.parts[0]
        result=dict(parts={'PART_01':p.copy()}, visual={**self.axes,'belt':self.travel/self.conveyor_length,'belt_reverse':-self.travel/self.conveyor_length,
                    'pallet_x':p['x'],'pallet_y':self.pallet_bottom+PALLET_THICKNESS/2,
                    'work_active':int(self.work.busy),'work_done':int(self.work.done)},
                    goal=int(self.goal()),velocity=int(bool(self.commands.get('belt'))),
                    violations=self.violations.copy(),support=self.support,pallet_bottom=self.pallet_bottom,
                    locator_top=self.plate_top,processed=int(self.processed),history=self.history.copy())
        if self.gauge_enabled:
            result['probe']=self.work.snapshot()
            result['visual'].update(probe_extension=(HOME_TIP-self.work.tip)/.25,probe_tip=self.work.tip)
        return result
