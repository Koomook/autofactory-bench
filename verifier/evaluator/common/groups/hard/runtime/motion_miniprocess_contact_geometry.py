"""H09 start-pose separation and H11 scissor guide contact geometry.

Keep the four reused mechanisms, controlled axes, jig coordinates and programs.
These contact models apply to H09 and H11.
"""
from math import sqrt
from motion_medium_mechanisms import pose, link
from motion_miniprocess_robot_installation import revise_layout as previous_layout, cell_state as previous_cell_state, mounts


def revise_layout(c):
    previous_layout(c)
    layout = c['layout']
    layout['clearance_revision'] = 8
    if c['task_slug'] == 'pocket_lease':
        # Open the folded home poses. Tool tips stay behind the front pockets,
        # visibly clear of their own columns before a request is admitted.
        layout['cells']['3']['pocket_homes'] = [[-.40, -.40], [0, -.25], [.40, -.40]]
    else:
        assert c['task_slug'] == 'deadline_pipeline'
        layout['source']['position'][2] += .25
    return layout


def source_state(cell):
    if cell['mode'] != 'level':
        return
    cell['clearance_revision'] = 8
    # A raised bearing seat leaves the sloped common beam clear of the plate.
    cell['poses']['beam']['pos'][1] += .10
    for mechanism in cell['mechanisms'].values():
        p = mechanism['poses']
        h = p['table']['pos'][1]
        # Preserve 1.5 m pivot spacing, with endpoint rollers inside open tracks.
        bottom, top = .24, h - .05
        reach = sqrt(1.5**2 - (top - bottom)**2)
        for side in (-1, 1):
            z = side * .42
            p[f'leg{side}a'] = link([-reach/2, bottom, z-.06], [reach/2, top, z-.06], .09)
            p[f'leg{side}b'] = link([reach/2, bottom, z+.06], [-reach/2, top, z+.06], .09)
            p[f'joint{side}'] = pose([0, (bottom+top)/2, z])
            for end in (-1, 1):
                p[f'lower_roller_{side}_{end}'] = pose([end*reach/2, bottom, z])
                p[f'upper_roller_{side}_{end}'] = pose([end*reach/2, top, z])
        mechanism['clearance_revision'] = 8


def cell_state(plant, station, cell):
    previous_cell_state(plant, station, cell)
    cell['clearance_revision'] = 8
    for mechanism in cell.get('mechanisms', {}).values():
        mechanism['clearance_revision'] = 8
    return cell
