
# my modules imports
from modules.collisions_handler import CollisionHandler
from modules.particules import Particule
from modules.utils import segment
from modules.vector import MyVector
from modules.grid import Grid
from modules.utils import get_mass_part

# imports
from dolfin import Point
from random import random
import numpy as np
from scipy.stats import maxwell, norm

def get_particles(types, numbers, speed_init_types, speed_init_params, effective_diameter, zone, offsets, space_size, verbose = False, debug = False):
    available_types = ['I','I-']
    list_particles=[]
    e = 1.6e-19
    for k in range(len(numbers)):
        type_ = types[k]
        number_ = numbers[k]
        speed_init_type = speed_init_types[k] # uniform or maxwellian
        m, M = speed_init_params[k]

        if(debug): 
            print('Creating {} particles of type {}.'.format(number_, type_))
            print('Speed type init is {} with params {}, {}.'.format(speed_init_type, m, M))

        if(type_ == 'I'):
            charge = 0
            radius = effective_diameter/2.0
            mass = get_mass_part(53, 53, 88)
        elif(type_ == 'I-'):
            charge = -e
            radius = effective_diameter/2.0
            mass = get_mass_part(52, 53, 88) # one less electron

        # parameters of the maxwellian distribution
        # https://stackoverflow.com/questions/63300833/maxwellian-distribution-in-python-scipy
        if(speed_init_type == 'maxwellian'):
            σ = m
            μ = M
            a = σ * np.sqrt(np.pi/(3.0*np.pi - 8.0))
            m = 2.0*a*np.sqrt(2.0/np.pi)
            loc = μ - m
        elif(speed_init_type == 'uniform'):
            # uniform distribution parameters
            min_speed_uniform_distribution = m
            max_speed_uniform_distribution = M
        else :
            print("/!\\ Unknown speed init type /!\\")
            return

        if(debug) : mean = 0
        for k in range(number_):
            my_speed = 0

            if(speed_init_type=='maxwellian'):
                norm_speed = float(maxwell.rvs(loc, a))
            elif(speed_init_type=='uniform'):
                norm_speed = min_speed_uniform_distribution+random()*\
                    (max_speed_uniform_distribution-min_speed_uniform_distribution)
                # direction of the speed

            theta = random()*2*np.pi
            cTheta = float(np.cos(theta))
            sTheta = float(np.sin(theta))

            my_speed = MyVector(norm_speed*cTheta,norm_speed*sTheta,0)

            x, y = get_correct_initial_positions(zone, offsets, space_size) # TODO
            list_particles.append(Particule(charge = charge, radius = radius, 
                    mass = mass, part_type = type_, \
                        speed=my_speed, \
                            pos=MyVector(x,y,0), \
                                verbose = verbose))
            if(debug): 
                print(my_speed)
                mean += my_speed.norm()

        if(debug): print("Mean speed init : {} m/s".format(round(mean/number_,2)))

    return np.array(list_particles) # we don't shuffle right now

def get_correct_initial_positions(zone, offsets, space_size):
    # same trouble as creating a grid for the space
    # how do we do that best
    offset_x, offset_y = offsets[0], offsets[1]
    lx, ly = space_size[0],space_size[1]
    
    x=random()*lx - offset_x
    y=random()*ly - offset_y
    if(zone!=None):
        while(not zone.inside(Point(x,y))):
            x=random()*lx - offset_x
            y=random()*ly - offset_y
    return x,y