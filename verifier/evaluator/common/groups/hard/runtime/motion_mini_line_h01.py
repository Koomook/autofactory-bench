"""Three reused Motion cells, six finite axes and two circulating setting jigs.

Station coupling is provided hardware: it can engage only at measured matching
poses. PLC owns all axis motion and admission; no unsafe drive is inhibited.
"""
from math import sin, cos, hypot
from copy import deepcopy
from motion_hard15 import MotionHardPlant, VIOLATIONS as BASE_VIOLATIONS
from motion_table_slide import TableSlidePlant, RAD
from motion_precision_geometry import InterferenceGeometry
from motion_medium_mechanisms import pose

EXTRA = ('shuttle_moved_with_fork_out','lift_moved_during_dock','unaligned_station_entry',
 'table_rotated_with_access','slide_approached_before_pose','line_geometry_collision',
 'coupling_misaligned','station_capacity_conflict','invalid_jig_route','premature_table_pickup')
VIOLATIONS = (*BASE_VIOLATIONS,*EXTRA)
PORT_X = {1:-900.,2:-350.,3:150.,4:850.}
LIFT_HEIGHT=732.5

class MiniLinePlant(MotionHardPlant):
    def __init__(self,package,scenario):
        super().__init__(package,scenario)
        self.locations={0:1,1:2}  # 0 shuttle, 1/2 lift, 3 waiting dock, 4 table
        self.sequence=0;self.table_age=0.;self.couplings=[]
        for j in self.jobs:j.update(returned=False,visited_table=False,phase='Waiting')

    def emit(self,name,**data):
        if name in EXTRA and (name,data.get('request')) not in self.seen:
            self.violations.append(dict(type=name,scan=self.tick,**data))
        super().emit(name,**data)

    def fixture_at(self,station):
        return next((lane for lane,location in self.locations.items() if location==station),None)

    def job_at(self,station):
        lane=self.fixture_at(station)
        return None if lane is None else self.pending(lane)

    def id_at(self,station):
        j=self.job_at(station)
        return j['id'] if j else 0

    def table_access_clear(self):
        return self.x('b')<=40 or abs(self.x('a')-PORT_X[4])>=150

    def slide_clear(self):
        return self.x('f')<=500 and abs(self.v('f'))<=1

    def port_ready(self,station):
        if station in (1,2):return self.at('cd'[station-1],LIFT_HEIGHT)
        if station==4:return self.at('e',0) and self.slide_clear()
        return station==3

    def table_ready(self):
        j=self.job_at(4)
        return bool(j and self.at('e',j['target']) and self.table_age>=30-1e-7)

    def feedback(self):
        self.issue();values={}
        for a in self.drives:
            values[a+'_position']=round(self.x(a)*100);values[a+'_velocity']=round(self.v(a)*100)
        for lane in (0,1):
            j=self.pending(lane)
            values.update({f'r{lane}_id':j['id'] if j else 0,f'r{lane}_served':int(bool(j and j['served'])),
                f'r{lane}_returned':int(bool(j and j['returned'])),f'r{lane}_location':self.locations[lane],
                f'r{lane}_due':round(j['arrival_ms']+j['deadline_ms']-self.time_ms) if j else 999999})
        table=self.job_at(4)
        values.update(all_done=int(self.all_done()),holding=self.id_at(0),table_id=self.id_at(4),buffer_id=self.id_at(3),
            table_lane=table['lane']+1 if table else 0,table_target=round(table['target']*100) if table else 0,
            table_depth=round(table['aux']*100) if table else 0,table_served=int(bool(table and table['served'])),
            table_ready=int(self.table_ready()),table_clear=int(self.table_access_clear() and self.slide_clear()),
            source0_ready=int(self.port_ready(1)),source1_ready=int(self.port_ready(2)),table_port_ready=int(self.port_ready(4)),
            home0=round(self.i['c']*100),home1=round(self.i['d']*100),sequence=self.sequence)
        return {address:values[k] for k,address in self.binding['feedback'].items()}

    def coupling(self,r):
        seq=r['couple_seq']
        if seq==self.sequence:return
        self.sequence=seq
        station,action=r['station'],r['action']
        if station not in PORT_X or action not in (1,2):
            self.emit('command_out_of_range');return
        if not self.at('a',PORT_X[station]) or not self.at('b',180) or not self.port_ready(station):
            self.emit('coupling_misaligned',station=station);return
        lane=self.fixture_at(station if action==1 else 0)
        if lane is None or self.fixture_at(0 if action==1 else station) is not None:
            self.emit('station_capacity_conflict',station=station);return
        j=self.pending(lane)
        if not j:
            self.emit('invalid_jig_route');return
        if action==1 and station==4 and not j['served']:
            self.emit('premature_table_pickup',request=j['id']);return
        if action==2 and station in (1,2) and (station!=lane+1 or not j['served']):
            self.emit('invalid_jig_route',request=j['id']);return
        if action==2 and station==4 and (j['served'] or j['visited_table']):
            self.emit('invalid_jig_route',request=j['id']);return
        before=self.fixture_pose(lane)['pos']
        old=self.locations[lane];self.locations[lane]=0 if action==1 else station
        after=self.fixture_pose(lane)['pos']
        gap=sum((a-b)**2 for a,b in zip(before,after))**.5
        # Never teleport a carried fixture between mismatched machine poses.
        if gap>.0003:
            self.locations[lane]=old;self.emit('coupling_misaligned',request=j['id'],gap_mm=gap*1000);return
        self.couplings.append(dict(scan=self.tick,request=j['id'],source=old,destination=self.locations[lane],gap_mm=gap*1000))
        # These can occur several times for one request; retain every transition.
        self.events.append(dict(type='jig_station_changed',scan=self.tick,request=j['id'],source=old,destination=self.locations[lane],gap_mm=gap*1000))
        if action==2 and station==4:
            j['visited_table']=True;self.table_age=0.;self.emit('request_reached_table',request=j['id'])
        if action==2 and station in (1,2):
            j['returned']=True;self.emit('request_returned',request=j['id'])

    def apply_commands(self,r):
        super().apply_commands(r)
        self.coupling(r)

    def service_position(self,j):
        return self.locations[j['lane']]==4 and j['visited_table'] and self.table_ready() and self.at('f',j['aux']) and self.table_access_clear()

    def receipt_ready(self,j):
        return j['served'] and j['returned'] and self.locations[j['lane']]==j['lane']+1 and self.at('cd'[j['lane']],self.i['cd'[j['lane']]])

    def safe_finish(self):
        targets=dict(a=0,b=0,c=self.i['c'],d=self.i['d'],e=0,f=50)
        return self.locations=={0:1,1:2} and all(self.at(a,t) for a,t in targets.items())

    @staticmethod
    def box(name,center,half):
        return dict(name=name,c=center,half=half,axes=[[1,0,0],[0,1,0],[0,0,1]])

    @classmethod
    def geometry(cls,values):
        a,b,c,d,e,f=(values[k] for k in 'abcdef')
        slide,jaws=TableSlidePlant.boxes(e,f)
        for item in slide+jaws:
            item['c'][0]+=.85;item['c'][2]+=1.06
        for i in range(4):
            theta=(e+90*i)*RAD
            for sign in (-1,1):
                jaws.append(dict(name=f'table_seat{i}_{sign}',c=[.85+cos(theta)*.55-sin(theta)*sign*.05,.9275,1.06+sin(theta)*.55+cos(theta)*sign*.05],half=[.06,.045,.005],axes=[[cos(theta),0,sin(theta)],[0,1,0],[-sin(theta),0,cos(theta)]]))
        fork=cls.box('shuttle_fork',[a/1000,.94,.18+b/1000],[.04,.0225,.18])
        ports=[]
        for station in (1,2,3):
            height=([c,d][station-1]/1000+.24) if station<3 else .9725
            for side in (-1,1):
                ports.append(cls.box(f'port{station}_side{side}',[PORT_X[station]/1000+side*.0725,height+.055,.51],[.02,.055,.12]))
        return slide,jaws,[fork],ports

    def physics_obligations(self,dt,before):
        if self.x('b')>40 and abs(self.v('a'))>1:self.emit('shuttle_moved_with_fork_out')
        if self.x('b')>40:
            near=next((s for s,x in PORT_X.items() if abs(self.x('a')-x)<120),None)
            if near in (1,2) and abs(self.v('cd'[near-1]))>1:self.emit('lift_moved_during_dock')
            if self.v('b')>1 and (near is None or not self.at('a',PORT_X[near]) or not self.port_ready(near)):
                self.emit('unaligned_station_entry')
        if abs(self.v('e'))>1 and (not self.table_access_clear() or self.x('f')>500):
            self.emit('table_rotated_with_access')
        if self.v('f')>1 and self.raw['f_target']/100>500 and not self.table_ready():
            self.emit('slide_approached_before_pose')
        j=self.job_at(4)
        self.table_age=self.table_age+dt*1000 if j and self.at('e',j['target']) else 0.
        old=self.geometry({a:before[a][0] for a in 'abcdef'})
        new=self.geometry({a:self.x(a) for a in 'abcdef'})
        for ga,gb in ((0,1),(2,1),(2,3)):
            for ia,ba in enumerate(old[ga]):
                for ib,bb in enumerate(old[gb]):
                    na,nb=new[ga][ia],new[gb][ib]
                    # Cheap swept AABB rejection; yaw-only boxes are bounded by
                    # horizontal radii. It never excludes overlapping pairs.
                    ra=hypot(ba['half'][0],ba['half'][2]);rb=hypot(bb['half'][0],bb['half'][2])
                    if any(min(ba['c'][k],na['c'][k])-ra>max(bb['c'][k],nb['c'][k])+rb or min(bb['c'][k],nb['c'][k])-rb>max(ba['c'][k],na['c'][k])+ra for k in (0,2)):continue
                    if min(ba['c'][1],na['c'][1])-ba['half'][1]>max(bb['c'][1],nb['c'][1])+bb['half'][1] or min(bb['c'][1],nb['c'][1])-bb['half'][1]>max(ba['c'][1],na['c'][1])+ba['half'][1]:continue
                    hit,gap=InterferenceGeometry.swept(ba,bb,na,nb,error=1e-5)
                    self.minimum_gap=min(self.minimum_gap,gap)
                    if hit:self.emit('line_geometry_collision',components=[ba['name'],bb['name']],gap_mm=gap*1000)

    def fixture_pose(self,lane):
        s=self.locations[lane]
        if s==0:return pose([self.x('a')/1000,.9825,.33+self.x('b')/1000])
        if s in (1,2):return pose([PORT_X[s]/1000,self.x('cd'[s-1])/1000+.25,.51])
        if s==3:return pose([.15,.9825,.51])
        angle=self.x('e')*RAD
        return pose([.85+.55*sin(angle),.9825,1.06-.55*cos(angle)],[0,-sin(angle/2),0,cos(angle/2)])

    def mechanisms(self):
        e,f=self.x('e'),self.x('f')
        return dict(table=dict(mode='table_slide',initial={},axis_labels={},poses=dict(
            table=dict(pos=[0,.85,0],quaternion=[0,-sin(e*RAD/2),0,cos(e*RAD/2)]),
            tongue=pose([1.25-f/1000,1.0412,0]),cantilever=pose([1.475-f/1000,1.0412,0]))))

    def poses(self):
        p=dict(shuttle=pose([self.x('a')/1000,.94,0]),fork=pose([self.x('a')/1000,.94,.18+self.x('b')/1000]))
        for lane,a in enumerate('cd'):
            p['lift'+str(lane)]=pose([PORT_X[lane+1]/1000,self.x(a)/1000+.08,.51])
            p['jig'+str(lane)]=self.fixture_pose(lane)
        e=self.x('e')*RAD
        p['table_seats']=pose([.85,0,1.06],[0,-sin(e/2),0,cos(e/2)])
        return p

    def snapshot(self):
        out=super().snapshot();m=out['motion_hard']
        for j in m['requests']:
            loc=self.locations[j['lane']]
            j['location']=loc
            j['phase']='Not arrived' if j['status']=='future' else 'Return complete' if j['status']=='done' else 'Descending and returning' if j['returned'] else 'Rotation and approach complete' if j['served'] else 'Shuttle travel' if loc==0 else 'Shared waiting station' if loc==3 else 'Rotary precision approach' if loc==4 else 'Lift alignment and waiting'
        m['shared'].update(holding_id=self.id_at(0),table_id=self.id_at(4),buffer_id=self.id_at(3),table_served=int(bool(self.job_at(4) and self.job_at(4)['served'])),table_ready=int(self.table_ready()))
        m['line']=dict(locations=dict(self.locations),stations=[dict(id=1,label='Lift preparation A',source='MOT-M18'),dict(id=2,label='Lift preparation B',source='MOT-M18'),dict(id=3,label='Shared waiting station',source='MOT-M07'),dict(id=4,label='Rotary precision approach',source='MOT-M14')],couplings=deepcopy(self.couplings[-1:]))
        return out
