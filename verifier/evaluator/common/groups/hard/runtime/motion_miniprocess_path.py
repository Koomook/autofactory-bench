"""Arc-length transport guide and rigid installation frames for H02–H05.

PLC axis A measures actual distance along the guide. Native station mechanisms
are rigidly relocated; their controlled coordinates and task obligations remain.
"""
from copy import deepcopy
from math import sin,cos,pi,ceil,hypot
from motion_medium_mechanisms import pose,yaw

def path_pose(path,s,y=0,offset=0):
    segment=next((v for v in path['segments'] if s<=v['end']+1e-10),path['segments'][-1])
    u=s-segment['start'];theta=segment['heading'];x,z=segment['position'];curvature=segment['curvature']
    if curvature:
        angle=theta+u*curvature
        x+=(sin(angle)-sin(theta))/curvature;z+=(cos(theta)-cos(angle))/curvature;theta=angle
    else:x+=u*cos(theta);z+=u*sin(theta)
    return pose([x-offset*sin(theta),y,z+offset*cos(theta)],yaw(-theta))

def transform(p,frame):
    from motion_miniprocess_clearance import rotated
    q=p['quaternion'];a=frame['quaternion'];ax,ay,az,aw=a;bx,by,bz,bw=q
    quaternion=[aw*bx+ax*bw+ay*bz-az*by,aw*by-ax*bz+ay*bw+az*bx,aw*bz+ax*by-ay*bx+az*bw,aw*bw-ax*bx-ay*by-az*bz]
    return pose(rotated(frame,p['pos']),quaternion,p.get('scale'))

def guide_frame(path,s,old_x):
    frame=path_pose(path,s);q=frame['quaternion'];theta=-2*__import__('math').atan2(q[1],q[3])
    frame['pos'][0]-=old_x*cos(theta);frame['pos'][2]-=old_x*sin(theta)
    return frame

def revise(c,number):
    l=c['layout'];original=deepcopy(c['port_x']);segments=[];s=-4.7;x,z=-4.7,0.;heading=0.
    radius=.8
    def add(length,k=0):
        nonlocal s,x,z,heading
        part=dict(start=s,end=s+length,position=[x,z],heading=heading,curvature=k);segments.append(part)
        p=path_pose({'segments':[part]},s+length);x,_,z=p['pos'];heading+=length*k;s+=length
    if number in (2,4):
        corner=1.8 if number==2 else 2.1
        add(corner-s);add(radius*pi/2,-1/radius);add(5.3-s)
        shape='L';ports=original.copy();ports['4']=4700
    else:
        add(-1.0-s);add(radius*pi/2,-1/radius);add(6.5-s);add(radius*pi/2,1/radius);add(11.5-s)
        shape='step';ports={**original,'3':2300,'4':9900}
    path=dict(revision=1,shape=shape,radius=radius,segments=segments,original_ports=original,station_frames={})
    for station in ('source','3','4'):
        key='1' if station=='source' else station
        path['station_frames'][station]=guide_frame(path,ports[key]/1000,original[key]/1000)
    c['port_x']=ports;c['travel_ranges']['a']=[-4500,round((s-.2)*1000)];c['command_ranges']['a']=c['travel_ranges']['a'][:]
    # Store a sufficiently fine guide cross-section mesh path once per layout.
    samples=[]
    for segment in segments:
        count=max(1,ceil((segment['end']-segment['start'])/(.045 if segment['curvature'] else .35)))
        for i in range(count):
            distance=segment['start']+(segment['end']-segment['start'])*i/count
            p=path_pose(path,distance);samples.append(dict(s=distance,pos=p['pos'],quaternion=p['quaternion']))
    p=path_pose(path,s);samples.append(dict(s=s,pos=p['pos'],quaternion=p['quaternion']))
    path['samples']=samples
    path['supports']=[path_pose(path,-4.3+i*(s+.0+4.3)/ceil((s+4.3)/1.4)) for i in range(ceil((s+4.3)/1.4)+1)]
    l['transport_path']=path
    return l

def fixture(plant,station,p):
    path=plant.layout['transport_path']
    if station==0:frame=guide_frame(path,plant.x('a')/1000,plant.x('a')/1000)
    else:frame=path['station_frames']['source' if station<3 else str(station)]
    return transform(p,frame)

def project(plant,poses):
    path=plant.layout['transport_path'];out={}
    for key,p in poses.items():
        if key in ('shuttle','fork'):station=0
        elif key.startswith('jig'):station=plant.locations[int(key[-1])]
        elif key.startswith('receiver'):station=int(key[8])
        elif key.startswith('connector'):station=int(key[9])
        else:out[key]=p;continue
        out[key]=fixture(plant,station,p)
    out['path_carriage']=path_pose(path,plant.x('a')/1000,plant.layout['rail_y'])
    for i,delta in enumerate((-.12,.12)):
        out['path_bogie'+str(i)]=path_pose(path,plant.x('a')/1000+delta,plant.layout['rail_y'])
    return out
