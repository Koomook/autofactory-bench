"""Synthetic datum-referenced contact gauge. No force or accuracy claims.

Measurement derives only from tip/workpiece geometry, not locator bits, PLC
program state, elapsed-work timers, or the expected result. A fixed machine
datum of .685 m is valid only when the pallet rests on the locating support.
"""
HOME_TIP = 1.02
BOTTOM_TIP = .77
DATUM = .685
NOMINAL_HEIGHT = .16
HEIGHT_TOLERANCE = .002

class ContactHeightProbe:
    def __init__(self, speed=.5, settle_ms=80):
        self.speed=speed;self.settle_ms=settle_ms
        self.tip=HOME_TIP;self.phase='idle';self.hold_ms=0
        self.busy=False;self.done=False;self.good=False;self.bad=False
        self.contact=False;self.measured_height=None;self.completed_count=0
        self.last_request=False;self.contact_count=0

    def tick(self, request, allowed, dt_ms, part):
        faults=[];request=bool(request)
        if request and not self.last_request and self.phase=='idle':
            if not allowed:faults.append('work_without_location')
            else:
                self.phase='approach';self.busy=True;self.done=False
                self.good=False;self.bad=False;self.measured_height=None;self.hold_ms=0
        if self.busy and (not request or not allowed):
            faults.append('work_request_aborted' if not request else 'location_lost_during_work')
            self.phase='abort_return';self.good=False;self.bad=True;self.contact=False
        aligned=abs(part['x'])<=.08 and abs(part['z'])<=.08
        top=part['y']+.08
        if self.phase=='approach':
            target=max(BOTTOM_TIP,self.tip-self.speed*dt_ms/1000)
            if aligned and target<=top<=self.tip+1e-8:
                self.tip=top;self.contact=True;self.contact_count+=1
                self.measured_height=top-DATUM
                self.good=abs(self.measured_height-NOMINAL_HEIGHT)<=HEIGHT_TOLERANCE
                self.bad=not self.good;self.phase='contact'
            else:
                self.tip=target
                if self.tip<=BOTTOM_TIP:
                    self.bad=True;self.phase='return';faults.append('probe_no_contact')
        elif self.phase=='contact':
            if not aligned or abs(top-self.tip)>1e-6:
                self.good=False;self.bad=True;faults.append('probe_contact_lost')
                self.phase='abort_return';self.contact=False
            else:
                self.hold_ms+=dt_ms
                if self.hold_ms>=self.settle_ms:self.phase='return';self.contact=False
        elif self.phase in ('return','abort_return'):
            abort=self.phase=='abort_return'
            self.tip=min(HOME_TIP,self.tip+self.speed*dt_ms/1000)
            if self.tip>=HOME_TIP:
                self.busy=False;self.done=True;self.phase='done'
                if not abort:self.completed_count+=1
        elif self.phase=='done' and not request:
            self.phase='idle';self.done=False;self.good=False;self.bad=False
        self.last_request=request
        return faults

    def snapshot(self):
        return dict(tip=self.tip,phase=self.phase,busy=self.busy,done=self.done,
                    good=self.good,bad=self.bad,contact=self.contact,
                    measured_height=self.measured_height,contact_count=self.contact_count)
