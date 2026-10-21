"""Select transport classes for the common runtime, observations and judge."""
from dataclasses import replace
import importlib,json
from plant_spec import PlantPackage

def replace_transport(root,task,built,index):
    package=PlantPackage.load(root/task['package'])
    scenario=json.loads((root/task['package']/package.task['scenarios'][index]).read_text())
    if scenario!=built.scenario or package.binding!=built.package.binding:
        raise ValueError('Scenario or I/O drift during transport selection')
    if task['id']=='MAT-M15':
        from material_m15_transport import NetBatchPlant
        plant=NetBatchPlant(package,scenario)
    else:
        code=task['id'][4:]
        if code in ('H10','H12'):
            from material_corner_plants import PLANTS
            cls=PLANTS[code]
        elif code in ('H09','H14'):
            mod=importlib.import_module('material_'+code.lower()+'_transport')
            cls=getattr(mod,'LiquidStations' if code=='H09' else 'WeighStations')
        else:cls=importlib.import_module('material_'+code.lower()+'_transport').PLANT
        plant=cls(package.binding,package.calibration,scenario.get('parameters',{}))
    return replace(built,plant=plant,package=package,scenario=scenario,profile_label='synthetic-material-belt-contact-v17')
